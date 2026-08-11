from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import SimulationTick
from .normalization import build_measured_tick


class SunSpecModbusFixtureAdapter:
    """Applies SunSpec-style scale factors to a recorded read-only register fixture."""

    def __init__(self, registers: dict[str, Any]) -> None:
        self.registers = registers

    @classmethod
    def from_path(cls, path: str | Path) -> SunSpecModbusFixtureAdapter:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def _scaled(registers: dict[str, Any], value_key: str, scale_key: str) -> float:
        return float(registers[value_key]) * (10 ** int(registers[scale_key]))

    def poll(self, observed_at: datetime) -> SimulationTick:
        inverter = self.registers["inverter"]
        meter = self.registers["meter"]
        storage = self.registers["storage"]
        weather = self.registers["weather"]
        site = self.registers["site"]
        return build_measured_tick(
            observed_at=observed_at,
            pv_power_w=self._scaled(inverter, "W", "W_SF"),
            pv_energy_today_wh=self._scaled(inverter, "WH", "WH_SF"),
            load_power_w=float(site["loadPowerW"]),
            grid_power_w=self._scaled(meter, "W", "W_SF"),
            battery_power_w=self._scaled(storage, "W", "W_SF"),
            battery_soc_pct=self._scaled(storage, "ChaState", "ChaState_SF"),
            dc_voltage_v=self._scaled(inverter, "DCV", "DCV_SF"),
            dc_current_a=self._scaled(inverter, "DCA", "DCA_SF"),
            ac_voltage_v=self._scaled(inverter, "ACV", "ACV_SF"),
            ac_current_a=self._scaled(inverter, "ACA", "ACA_SF"),
            grid_voltage_v=self._scaled(meter, "PhVphA", "V_SF"),
            frequency_hz=self._scaled(inverter, "Hz", "Hz_SF"),
            inverter_temperature_c=self._scaled(inverter, "TmpCab", "TmpCab_SF"),
            panel_temperature_c=float(weather["panelTemperatureC"]),
            irradiance_wm2=float(weather["irradianceWm2"]),
        )
