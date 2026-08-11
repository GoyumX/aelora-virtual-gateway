from __future__ import annotations

import math
from datetime import UTC, datetime

from .models import DeviceObservation, PlantState, SimulationTick, SiteSnapshot

WEATHER_FACTOR = {
    "SUNNY": 1.0,
    "PARTLY_CLOUDY": 0.72,
    "CLOUDY": 0.43,
    "RAINY": 0.24,
    "STORM": 0.08,
}


class SimulationEngine:
    def __init__(self, state: PlantState) -> None:
        self.state = state
        self._last_telemetry: dict[str, datetime] = {}
        self._energy_today_wh = 0.0

    def tick(self, observed_at: datetime | None = None) -> SimulationTick:
        now = observed_at or datetime.now(UTC)
        environment = self.state.environment
        daylight = max(0.0, math.sin(((environment.hour_of_day - 6) / 12) * math.pi))
        irradiance = (
            environment.manual_irradiance_wm2
            if environment.manual_irradiance_wm2 is not None
            else round(1_000 * daylight * WEATHER_FACTOR[environment.weather])
        )

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

        demand = float(self.state.load_power_w)
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

        hours = self.state.publish_interval_sec / 3_600
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
            grid_voltage_v=self.state.grid.voltage_v if self.state.grid.available else 0,
            frequency_hz=self.state.grid.frequency_hz if self.state.grid.available else 0,
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
                    metrics={"powerW": snapshot.load_power_w},
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
                    },
                ),
            ]
        )
        return observations
