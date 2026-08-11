from datetime import UTC, datetime
from pathlib import Path

import pytest

from aelora_virtual_gateway.adapters.fronius import FroniusJsonAdapter
from aelora_virtual_gateway.adapters.sunspec import SunSpecModbusFixtureAdapter

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 11, 10, 30, tzinfo=UTC)


def test_fronius_and_sunspec_fixtures_normalize_to_the_same_aelora_units_and_signs() -> None:
    fronius = FroniusJsonAdapter.from_path(FIXTURES / "fronius-site.json").poll(NOW)
    sunspec = SunSpecModbusFixtureAdapter.from_path(FIXTURES / "sunspec-site.json").poll(NOW)

    for tick in (fronius, sunspec):
        snapshot = tick.site_snapshot
        assert snapshot.pv_power_w == pytest.approx(2450)
        assert snapshot.pv_energy_today_wh == pytest.approx(12400)
        assert snapshot.load_power_w == pytest.approx(1650)
        assert snapshot.grid_power_w == pytest.approx(-500)
        assert snapshot.battery_power_w == pytest.approx(-300)
        assert snapshot.pv_power_w + snapshot.battery_power_w + snapshot.grid_power_w == pytest.approx(
            snapshot.load_power_w
        )
        assert all(device.quality == "MEASURED" for device in tick.devices)

    fronius_snapshot = fronius.site_snapshot.model_dump(exclude={"observed_at"})
    sunspec_snapshot = sunspec.site_snapshot.model_dump(exclude={"observed_at"})
    for key, value in fronius_snapshot.items():
        if isinstance(value, (int, float)):
            assert sunspec_snapshot[key] == pytest.approx(value, abs=0.001)
        else:
            assert sunspec_snapshot[key] == value


def test_sunspec_scale_factors_are_applied_before_normalization() -> None:
    tick = SunSpecModbusFixtureAdapter.from_path(FIXTURES / "sunspec-site.json").poll(NOW)

    assert tick.device("inverter-main").metrics["acVoltageV"] == pytest.approx(230.0)
    assert tick.device("inverter-main").metrics["frequencyHz"] == pytest.approx(50.0)
