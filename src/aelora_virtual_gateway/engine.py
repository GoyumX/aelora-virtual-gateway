from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, tzinfo

from .models import DeviceObservation, PlantState, SimulationTick, SiteSnapshot

WEATHER_FACTOR = {
    "SUNNY": 1.0,
    "PARTLY_CLOUDY": 0.72,
    "CLOUDY": 0.43,
    "RAINY": 0.24,
    "STORM": 0.08,
}


class SimulationEngine:
    def __init__(self, state: PlantState, *, local_timezone: tzinfo | None = None) -> None:
        self.state = state
        self.local_timezone = local_timezone or datetime.now().astimezone().tzinfo or UTC
        self._last_telemetry: dict[str, datetime] = {}
        self._energy_today_wh = 0.0
        self._energy_date: date | None = None
        self._last_energy_tick_at: datetime | None = None

    def local_time(self, observed_at: datetime) -> datetime:
        return observed_at.astimezone(self.local_timezone)

    def effective_hour(self, observed_at: datetime) -> float:
        if self.state.environment.clock_mode == "MANUAL":
            return self.state.environment.hour_of_day
        local = self.local_time(observed_at)
        return local.hour + local.minute / 60 + local.second / 3_600

    def _anchor_random(self, channel: str, anchor: int) -> random.Random:
        seed = f"{self.state.environment.variation_seed}:{channel}:{anchor}"
        return random.Random(seed)

    def _dynamic_value(
        self,
        observed_at: datetime,
        channel: str,
        minimum: float,
        maximum: float,
        *,
        transition_sec: int = 900,
    ) -> float:
        if minimum == maximum:
            return minimum
        position = observed_at.timestamp() / transition_sec
        lower_anchor = math.floor(position)
        progress = position - lower_anchor
        lower = self._anchor_random(channel, lower_anchor).uniform(minimum, maximum)
        upper = self._anchor_random(channel, lower_anchor + 1).uniform(minimum, maximum)
        return lower + (upper - lower) * progress

    def _integration_hours(self, observed_at: datetime) -> float:
        local_date = self.local_time(observed_at).date()
        if self._energy_date != local_date:
            self._energy_today_wh = 0.0
            self._energy_date = local_date
            self._last_energy_tick_at = None
        if self._last_energy_tick_at is None:
            seconds = self.state.publish_interval_sec
        else:
            elapsed = (observed_at - self._last_energy_tick_at).total_seconds()
            seconds = min(max(0.0, elapsed), self.state.publish_interval_sec * 2)
        if self._last_energy_tick_at is None or observed_at > self._last_energy_tick_at:
            self._last_energy_tick_at = observed_at
        return seconds / 3_600

    def tick(self, observed_at: datetime | None = None) -> SimulationTick:
        now = observed_at or datetime.now(UTC)
        environment = self.state.environment
        effective_hour = self.effective_hour(now)
        daylight = max(0.0, math.sin(((effective_hour - 6) / 12) * math.pi))
        if environment.manual_irradiance_wm2 is not None:
            irradiance = environment.manual_irradiance_wm2
        else:
            clear_irradiance = 1_000 * daylight * WEATHER_FACTOR[environment.weather]
            cloud_floor = max(0.0, 1 - environment.cloud_variability_pct / 100)
            cloud_factor = self._dynamic_value(
                now,
                "cloud",
                cloud_floor,
                1.0,
                transition_sec=480,
            )
            irradiance = round(clear_irradiance * cloud_factor)

        array_power: dict[str, float] = {}
        for array in self.state.arrays:
            derate = (
                (array.efficiency_pct / 100) * (1 - array.shading_pct / 100) * (1 - array.soiling_pct / 100)
            )
            power = (
                array.panel_count * array.rated_power_w * (irradiance / 1_000) * derate
                if array.operating
                else 0
            )
            array_power[array.external_id] = max(0.0, power)

        dc_power = sum(array_power.values())
        pv_power = min(
            dc_power * self.state.inverter.efficiency_pct / 100, self.state.inverter.max_ac_power_w
        )
        if not self.state.inverter.operating:
            pv_power = 0.0

        demand = (
            self._dynamic_value(
                now,
                "household-load",
                self.state.load_min_power_w,
                self.state.load_max_power_w,
                transition_sec=900,
            )
            if self.state.load_mode == "DYNAMIC"
            else float(self.state.load_power_w)
        )
        battery_power = 0.0
        battery = self.state.battery
        if battery.operating:
            if pv_power > demand and battery.state_of_charge_pct < battery.max_soc_pct:
                battery_power = -min(pv_power - demand, battery.max_charge_power_w)
            elif pv_power < demand and battery.state_of_charge_pct > battery.min_soc_pct:
                battery_power = min(demand - pv_power, battery.max_discharge_power_w)

        grid_power = demand - pv_power - battery_power
        served_load = demand
        if not self.state.grid.available:
            grid_power = 0.0
            served_load = max(0.0, pv_power + battery_power)

        hours = self._integration_hours(now)
        self._energy_today_wh += pv_power * hours
        if battery.capacity_wh > 0:
            battery.state_of_charge_pct = min(
                battery.max_soc_pct,
                max(
                    battery.min_soc_pct,
                    battery.state_of_charge_pct - (battery_power * hours / battery.capacity_wh) * 100,
                ),
            )

        dc_voltage = 380.0 if dc_power > 0 else 0.0
        ac_voltage = 230.0 if self.state.inverter.operating else 0.0
        grid_voltage = 0.0
        frequency = 0.0
        if self.state.grid.available:
            voltage_variation = self.state.grid.voltage_v * self.state.grid.voltage_variability_pct / 100
            grid_voltage = self._dynamic_value(
                now,
                "grid-voltage",
                max(0.0, self.state.grid.voltage_v - voltage_variation),
                self.state.grid.voltage_v + voltage_variation,
                transition_sec=120,
            )
            frequency = self._dynamic_value(
                now,
                "grid-frequency",
                max(0.0, self.state.grid.frequency_hz - self.state.grid.frequency_variability_hz),
                self.state.grid.frequency_hz + self.state.grid.frequency_variability_hz,
                transition_sec=120,
            )
        device_status = self._device_status()
        snapshot = SiteSnapshot(
            observed_at=now,
            pv_power_w=round(pv_power, 2),
            pv_energy_today_wh=round(self._energy_today_wh, 2),
            load_power_w=round(served_load, 2),
            grid_power_w=round(grid_power, 2),
            battery_power_w=round(battery_power, 2),
            battery_soc_pct=round(battery.state_of_charge_pct, 2),
            dc_voltage_v=dc_voltage,
            dc_current_a=round(dc_power / dc_voltage, 2) if dc_voltage else 0,
            ac_voltage_v=ac_voltage,
            ac_current_a=round(pv_power / ac_voltage, 2) if ac_voltage else 0,
            grid_voltage_v=round(grid_voltage, 2),
            frequency_hz=round(frequency, 3),
            inverter_temperature_c=round(
                environment.ambient_temperature_c
                + (pv_power / max(1, self.state.inverter.max_ac_power_w)) * 18,
                1,
            ),
            panel_temperature_c=round(environment.ambient_temperature_c + irradiance * 0.025, 1),
            irradiance_wm2=irradiance,
            device_status=device_status,
        )
        devices = self._observations(now, array_power, snapshot)
        return SimulationTick(site_snapshot=snapshot, devices=devices)

    def _device_status(self) -> str:
        if not self.state.grid.available:
            return "GRID_OUTAGE"
        if not self.state.inverter.operating:
            return "INVERTER_FAULT"
        if not self.state.battery.operating:
            return "BATTERY_FAULT"
        if any(array.shading_pct >= 25 or array.soiling_pct >= 25 for array in self.state.arrays):
            return "ARRAY_UNDERPERFORMING"
        return "NORMAL"

    def _observation(
        self,
        *,
        external_id: str,
        kind: str,
        name: str,
        communications_enabled: bool,
        operational_state: str,
        now: datetime,
        metrics: dict,
    ) -> DeviceObservation:
        if communications_enabled:
            self._last_telemetry[external_id] = now
        return DeviceObservation(
            external_id=external_id,
            kind=kind,
            name=name,
            reported_at=now,
            last_telemetry_at=self._last_telemetry.get(external_id),
            connectivity_status="ONLINE" if communications_enabled else "OFFLINE",
            operational_state=operational_state if communications_enabled else "UNKNOWN",
            quality="SIMULATED" if communications_enabled else "STALE",
            metrics=metrics if communications_enabled else {},
        )

    def _observations(
        self, now: datetime, array_power: dict[str, float], snapshot: SiteSnapshot
    ) -> list[DeviceObservation]:
        observations = [
            self._observation(
                external_id=array.external_id,
                kind="PV_ARRAY",
                name=array.name,
                communications_enabled=array.communications_enabled,
                operational_state="RUNNING" if array.operating else "STOPPED",
                now=now,
                metrics={
                    "powerW": round(array_power[array.external_id], 2),
                    "efficiencyPct": array.efficiency_pct,
                },
            )
            for array in self.state.arrays
        ]
        observations.extend(
            [
                self._observation(
                    external_id=self.state.inverter.external_id,
                    kind="INVERTER",
                    name=self.state.inverter.name,
                    communications_enabled=self.state.inverter.communications_enabled,
                    operational_state="RUNNING" if self.state.inverter.operating else "FAULT",
                    now=now,
                    metrics={
                        "acPowerW": snapshot.pv_power_w,
                        "temperatureC": snapshot.inverter_temperature_c,
                    },
                ),
                self._observation(
                    external_id=self.state.battery.external_id,
                    kind="BATTERY",
                    name=self.state.battery.name,
                    communications_enabled=self.state.battery.communications_enabled,
                    operational_state="RUNNING" if self.state.battery.operating else "FAULT",
                    now=now,
                    metrics={"powerW": snapshot.battery_power_w, "socPct": snapshot.battery_soc_pct},
                ),
                self._observation(
                    external_id=self.state.grid.external_id,
                    kind="GRID_METER",
                    name=self.state.grid.name,
                    communications_enabled=self.state.grid.communications_enabled,
                    operational_state="RUNNING" if self.state.grid.available else "FAULT",
                    now=now,
                    metrics={"powerW": snapshot.grid_power_w, "voltageV": snapshot.grid_voltage_v},
                ),
                self._observation(
                    external_id="load-meter",
                    kind="LOAD_METER",
                    name="Household load meter",
                    communications_enabled=True,
                    operational_state="RUNNING",
                    now=now,
                    metrics={
                        "powerW": snapshot.load_power_w,
                        "mode": self.state.load_mode,
                        "minimumPowerW": self.state.load_min_power_w,
                        "maximumPowerW": self.state.load_max_power_w,
                    },
                ),
                self._observation(
                    external_id="weather-sensor",
                    kind="WEATHER_SENSOR",
                    name="Virtual weather sensor",
                    communications_enabled=True,
                    operational_state="RUNNING",
                    now=now,
                    metrics={
                        "irradianceWm2": snapshot.irradiance_wm2,
                        "weather": self.state.environment.weather,
                        "effectiveHour": round(self.effective_hour(now), 3),
                        "cloudVariabilityPct": self.state.environment.cloud_variability_pct,
                    },
                ),
            ]
        )
        return observations
