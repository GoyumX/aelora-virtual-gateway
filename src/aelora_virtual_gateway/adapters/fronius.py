from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import SimulationTick
from .normalization import build_measured_tick


class FroniusJsonAdapter:
    """Normalizes a recorded Fronius Solar API JSON response without writing controls."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    @classmethod
    def from_path(cls, path: str | Path) -> FroniusJsonAdapter:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def _value(data: dict[str, Any], key: str) -> float:
        values = data[key]["Values"]
        return float(next(iter(values.values())))

    def poll(self, observed_at: datetime) -> SimulationTick:
        inverter = self.payload["inverter"]["Body"]["Data"]
        meter = self.payload["meter"]["Body"]["Data"]
        battery = self.payload["battery"]["Body"]["Data"]["Controller"]
        weather = self.payload["weather"]
        site = self.payload["site"]
        return build_measured_tick(
            observed_at=observed_at,
            pv_power_w=self._value(inverter, "PAC"),
            pv_energy_today_wh=self._value(inverter, "DAY_ENERGY"),
            load_power_w=float(site["loadPowerW"]),
            grid_power_w=float(meter["PowerReal_P_Sum"]),
            battery_power_w=float(battery["PowerReal_PAC_Sum"]),
            battery_soc_pct=float(battery["StateOfCharge_Relative"]),
            dc_voltage_v=self._value(inverter, "UDC"),
            dc_current_a=self._value(inverter, "IDC"),
            ac_voltage_v=self._value(inverter, "UAC"),
            ac_current_a=self._value(inverter, "IAC"),
            grid_voltage_v=float(meter["Voltage_AC_Phase_1"]),
            frequency_hz=self._value(inverter, "FAC"),
            inverter_temperature_c=self._value(inverter, "TEMPERATURE"),
            panel_temperature_c=float(weather["panelTemperatureC"]),
            irradiance_wm2=float(weather["irradianceWm2"]),
        )
