from datetime import UTC, datetime

import pytest

from aelora_virtual_gateway.engine import SimulationEngine
from aelora_virtual_gateway.models import PanelArray, PlantState

NOW = datetime(2026, 8, 11, 6, 30, tzinfo=UTC)


def test_rain_reduces_output_and_inverter_clips_total_power() -> None:
    state = PlantState.default()
    state.environment.hour_of_day = 12
    state.inverter.max_ac_power_w = 3_000
    engine = SimulationEngine(state)

    sunny = engine.tick(NOW)
    state.environment.weather = "RAINY"
    rainy = engine.tick(NOW)

    assert sunny.site_snapshot.pv_power_w == 3_000
    assert rainy.site_snapshot.pv_power_w < sunny.site_snapshot.pv_power_w


def test_adding_an_array_increases_available_generation() -> None:
    state = PlantState.default()
    state.environment.hour_of_day = 12
    state.inverter.max_ac_power_w = 20_000
    engine = SimulationEngine(state)
    before = engine.tick(NOW).site_snapshot.pv_power_w

    state.arrays.append(PanelArray(external_id="garage", name="Garage", panel_count=8, rated_power_w=450))
    after = engine.tick(NOW).site_snapshot.pv_power_w

    assert after > before


def test_communications_and_operation_are_independent() -> None:
    state = PlantState.default()
    panel = state.arrays[0]
    panel.communications_enabled = True
    panel.operating = False

    observation = SimulationEngine(state).tick(NOW).device("array-east")

    assert observation.connectivity_status == "ONLINE"
    assert observation.operational_state == "STOPPED"
    assert observation.metrics["powerW"] == 0


def test_offline_communications_retains_last_telemetry_time() -> None:
    state = PlantState.default()
    engine = SimulationEngine(state)
    first = engine.tick(NOW).device("array-east")
    state.arrays[0].communications_enabled = False

    second = engine.tick(datetime(2026, 8, 11, 6, 31, tzinfo=UTC)).device("array-east")

    assert second.connectivity_status == "OFFLINE"
    assert second.last_telemetry_at == first.last_telemetry_at
    assert second.metrics == {}


def test_every_snapshot_obeys_aelora_power_sign_convention() -> None:
    result = SimulationEngine(PlantState.default()).tick(NOW).site_snapshot

    assert result.pv_power_w + result.battery_power_w + result.grid_power_w == pytest.approx(
        result.load_power_w, abs=1
    )
