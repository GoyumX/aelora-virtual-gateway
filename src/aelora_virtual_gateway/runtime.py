from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from . import __version__
from .engine import SimulationEngine
from .models import PlantState, ScenarioCode, SimulationTick
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
                self.plant.environment.manual_irradiance_wm2 = 350
            elif code == "RAIN_DAY":
                self.plant.environment.weather = "RAINY"
            elif code == "DIRTY_ARRAY":
                self.plant.arrays[0].soiling_pct = 45
            elif code == "PARTIAL_SHADE":
                self.plant.arrays[0].shading_pct = 60
            elif code == "INVERTER_FAULT":
                self.plant.inverter.operating = False
            elif code == "BATTERY_LOW":
                self.plant.battery.state_of_charge_pct = self.plant.battery.min_soc_pct
            elif code == "GRID_OUTAGE":
                self.plant.grid.available = False
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
