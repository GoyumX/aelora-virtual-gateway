from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from . import __version__
from .engine import SimulationEngine
from .models import Battery, Environment, PlantState, ScenarioCode, SimulationTick
from .publisher import AeloraPublisher
from .storage import StateStore


class GatewayRuntime:
    def __init__(
        self, store: StateStore, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.store = store
        self.plant = store.load_plant()
        self.engine = SimulationEngine(self.plant)
        self.publisher = AeloraPublisher(store, base_url, transport=transport)
        self.latest: SimulationTick | None = None
        self.lock = threading.RLock()
        self._scenario_baseline: PlantState | None = None
        self.scenario_code: ScenarioCode | None = None
        self.scenario_ends_at: datetime | None = None

    def save(self) -> None:
        self.store.save_plant(self.plant)

    def clock_state(self) -> dict[str, str | float]:
        observed_at = datetime.now(UTC)
        local = self.engine.local_time(observed_at)
        return {
            "mode": self.plant.environment.clock_mode,
            "observedAt": observed_at.isoformat(),
            "localDateTime": local.isoformat(),
            "timezone": local.tzname() or str(local.utcoffset()),
            "effectiveHour": round(self.engine.effective_hour(observed_at), 3),
        }

    def update_environment(self, changes: dict) -> Environment:
        with self.lock:
            data = self.plant.environment.model_dump()
            data.update(changes)
            self.plant.environment = Environment.model_validate(data)
            self.save()
            self.tick()
            return self.plant.environment

    def update_load(self, changes: dict) -> PlantState:
        with self.lock:
            data = self.plant.model_dump()
            data.update(changes)
            candidate = PlantState.model_validate(data)
            for key in changes:
                setattr(self.plant, key, getattr(candidate, key))
            self.save()
            self.tick()
            return self.plant

    def update_battery(self, changes: dict) -> Battery:
        with self.lock:
            data = self.plant.battery.model_dump()
            data.update(changes)
            self.plant.battery = Battery.model_validate(data)
            self.save()
            return self.plant.battery

    def tick(self, observed_at: datetime | None = None) -> SimulationTick:
        with self.lock:
            timestamp = observed_at or datetime.now(UTC)
            if self.scenario_ends_at and timestamp >= self.scenario_ends_at:
                self._restore_scenario()
            self.latest = self.engine.tick(timestamp)
            self.save()
            return self.latest

    def enroll(self, token: str) -> None:
        self.publisher.enroll(token, __version__)

    def publish_once(self) -> bool:
        identity = self.store.load_identity()
        if not identity:
            return False
        self.publisher.flush_pending()
        tick = self.tick()
        sequence = self.store.next_sequence()
        batch = tick.to_batch(identity.gateway_id, sequence, str(uuid4()))
        return self.publisher.publish(batch)

    def heartbeat_once(self) -> bool:
        now = datetime.now(UTC)
        if not self.latest or (self.scenario_ends_at and now >= self.scenario_ends_at):
            self.tick(now)
        return self.publisher.heartbeat(
            publishing_enabled=self.plant.publishing_enabled,
            queue_depth=self.store.pending_count(),
            device_count=len(self.latest.devices) if self.latest else 0,
        )

    def update_credential(self, credential: str) -> bool:
        return self.store.update_credential(credential)

    def start_scenario(
        self,
        code: ScenarioCode,
        duration_sec: int,
        now: datetime | None = None,
    ) -> dict[str, str | int]:
        with self.lock:
            if self._scenario_baseline:
                self._restore_scenario()
            self._scenario_baseline = self.plant.model_copy(deep=True)
            timestamp = now or datetime.now(UTC)
            self.scenario_code = code
            self.scenario_ends_at = timestamp + timedelta(seconds=duration_sec)
            if code == "CLOUD_RAMP":
                self.plant.environment.weather = "PARTLY_CLOUDY"
                self.plant.environment.manual_irradiance_wm2 = None
                self.plant.environment.cloud_variability_pct = 55
            elif code == "PASSING_CLOUDS":
                self.plant.environment.weather = "PARTLY_CLOUDY"
                self.plant.environment.manual_irradiance_wm2 = None
                self.plant.environment.cloud_variability_pct = 70
            elif code == "RAIN_DAY":
                self.plant.environment.weather = "RAINY"
                self.plant.environment.manual_irradiance_wm2 = None
                self.plant.environment.cloud_variability_pct = 35
            elif code == "DIRTY_ARRAY":
                self.plant.arrays[0].soiling_pct = 45
            elif code == "PARTIAL_SHADE":
                self.plant.arrays[0].shading_pct = 60
            elif code == "INVERTER_FAULT":
                self.plant.inverter.operating = False
            elif code == "INVERTER_CLIPPING":
                self.plant.inverter.operating = True
                self.plant.inverter.max_ac_power_w = 2_500
            elif code == "INVERTER_COMMS_LOSS":
                self.plant.inverter.communications_enabled = False
            elif code == "BATTERY_LOW":
                self.plant.battery.state_of_charge_pct = self.plant.battery.min_soc_pct
            elif code == "BATTERY_DRAIN":
                self.plant.battery.operating = True
                self.plant.battery.state_of_charge_pct = min(self.plant.battery.max_soc_pct, 70)
                self.plant.environment.clock_mode = "MANUAL"
                self.plant.environment.hour_of_day = 21
                self.plant.load_mode = "DYNAMIC"
                self.plant.load_min_power_w = 4_000
                self.plant.load_max_power_w = 6_500
            elif code == "GRID_OUTAGE":
                self.plant.grid.available = False
            elif code == "GRID_VOLTAGE_SAG":
                self.plant.grid.available = True
                self.plant.grid.voltage_v = 195
            elif code == "LOAD_SPIKE":
                self.plant.load_mode = "DYNAMIC"
                self.plant.load_min_power_w = 4_500
                self.plant.load_max_power_w = 7_000
            elif code == "LOAD_DROP":
                self.plant.load_mode = "DYNAMIC"
                self.plant.load_min_power_w = 500
                self.plant.load_max_power_w = 1_000
            elif code == "NIGHT_PREVIEW":
                self.plant.environment.clock_mode = "MANUAL"
                self.plant.environment.hour_of_day = 22
            self.save()
            self.tick(timestamp)
            return self.scenario_state()  # type: ignore[return-value]

    def scenario_state(self) -> dict[str, str | int] | None:
        if not self.scenario_code or not self.scenario_ends_at:
            return None
        return {"code": self.scenario_code, "endsAt": self.scenario_ends_at.isoformat()}

    def _restore_scenario(self) -> None:
        if self._scenario_baseline:
            self.plant = self._scenario_baseline
            self.engine = SimulationEngine(self.plant)
        self._scenario_baseline = None
        self.scenario_code = None
        self.scenario_ends_at = None
        self.save()

    def stop_scenario(self) -> PlantState:
        with self.lock:
            self._restore_scenario()
            self.tick()
            return self.plant

    def reset(self) -> PlantState:
        with self.lock:
            self.store.reset()
            self.plant = PlantState.default()
            self.engine = SimulationEngine(self.plant)
            self.latest = None
            self._scenario_baseline = None
            self.scenario_code = None
            self.scenario_ends_at = None
            self.save()
            return self.plant

    def close(self) -> None:
        self.publisher.close()
