from datetime import UTC, datetime, timedelta, timezone

import pytest

from aelora_virtual_gateway.engine import SimulationEngine
from aelora_virtual_gateway.models import PanelArray, PlantState

NOW = datetime(2026, 8, 11, 6, 30, tzinfo=UTC)


def manual_state(hour: float = 12) -> PlantState:
    data = PlantState.default().model_dump()
    data["environment"].update({"clock_mode": "MANUAL", "hour_of_day": hour})
    return PlantState.model_validate(data)


def test_rain_reduces_output_and_inverter_clips_total_power() -> None:
    state = manual_state()
    state.inverter.max_ac_power_w = 3_000
    engine = SimulationEngine(state)

    sunny = engine.tick(NOW)
    state.environment.weather = "RAINY"
    rainy = engine.tick(NOW)

    assert sunny.site_snapshot.pv_power_w == 3_000
    assert rainy.site_snapshot.pv_power_w < sunny.site_snapshot.pv_power_w


def test_adding_an_array_increases_available_generation() -> None:
    state = manual_state()
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


def test_system_clock_uses_the_computer_local_hour_and_real_timestamp() -> None:
    state = PlantState.default()
    colombo = timezone(timedelta(hours=5, minutes=30))
    observed_at = datetime(2026, 8, 16, 14, 30, tzinfo=UTC)

    result = SimulationEngine(state, local_timezone=colombo).tick(observed_at).site_snapshot

    assert result.observed_at == observed_at
    assert result.irradiance_wm2 == 0
    assert state.environment.hour_of_day == 12


def test_dynamic_load_and_clouds_vary_by_interval_without_breaking_power_balance() -> None:
    data = manual_state().model_dump()
    data.update(
        {
            "load_mode": "DYNAMIC",
            "load_min_power_w": 2_200,
            "load_max_power_w": 3_000,
            "publish_interval_sec": 30,
        }
    )
    data["environment"].update({"cloud_variability_pct": 35, "variation_seed": 417})
    data["battery"]["operating"] = False
    data["inverter"]["max_ac_power_w"] = 20_000
    state = PlantState.model_validate(data)
    engine = SimulationEngine(state, local_timezone=UTC)

    first = engine.tick(datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)).site_snapshot
    second = engine.tick(datetime(2026, 8, 16, 12, 0, 30, tzinfo=UTC)).site_snapshot

    assert 2_200 <= first.load_power_w <= 3_000
    assert 2_200 <= second.load_power_w <= 3_000
    assert first.load_power_w != second.load_power_w
    assert 650 <= first.irradiance_wm2 <= 1_000
    assert 650 <= second.irradiance_wm2 <= 1_000
    assert first.irradiance_wm2 != second.irradiance_wm2
    assert first.grid_power_w != second.grid_power_w
    for snapshot in (first, second):
        assert snapshot.pv_power_w + snapshot.battery_power_w + snapshot.grid_power_w == pytest.approx(
            snapshot.load_power_w, abs=1
        )


def test_seeded_variation_is_reproducible_for_the_same_interval() -> None:
    data = manual_state().model_dump()
    data.update({"load_mode": "DYNAMIC", "load_min_power_w": 1_800, "load_max_power_w": 3_200})
    data["environment"].update({"cloud_variability_pct": 45, "variation_seed": 99})
    data["battery"]["operating"] = False
    observed_at = datetime(2026, 8, 16, 12, 0, 30, tzinfo=UTC)

    first = SimulationEngine(PlantState.model_validate(data), local_timezone=UTC).tick(observed_at)
    second = SimulationEngine(PlantState.model_validate(data), local_timezone=UTC).tick(observed_at)

    assert first.site_snapshot.load_power_w == second.site_snapshot.load_power_w
    assert first.site_snapshot.irradiance_wm2 == second.site_snapshot.irradiance_wm2
    assert first.site_snapshot.grid_power_w == second.site_snapshot.grid_power_w


def test_dynamic_signals_change_smoothly_instead_of_jumping_each_publish_interval() -> None:
    data = manual_state().model_dump()
    data.update(
        {
            "load_mode": "DYNAMIC",
            "load_min_power_w": 1_200,
            "load_max_power_w": 5_000,
            "publish_interval_sec": 30,
        }
    )
    data["environment"].update({"cloud_variability_pct": 45, "variation_seed": 812})
    data["battery"]["operating"] = False
    data["inverter"]["max_ac_power_w"] = 20_000
    engine = SimulationEngine(PlantState.model_validate(data), local_timezone=UTC)

    snapshots = [
        engine.tick(datetime(2026, 8, 16, 12, 0, tzinfo=UTC) + timedelta(seconds=30 * index)).site_snapshot
        for index in range(21)
    ]

    adjacent = zip(snapshots, snapshots[1:], strict=False)
    load_steps = [
        abs(current.load_power_w - previous.load_power_w)
        for previous, current in adjacent
    ]
    adjacent = zip(snapshots, snapshots[1:], strict=False)
    irradiance_steps = [
        abs(current.irradiance_wm2 - previous.irradiance_wm2)
        for previous, current in adjacent
    ]
    assert max(load_steps) < 350
    assert max(irradiance_steps) < 90
    assert len({snapshot.load_power_w for snapshot in snapshots}) > 5
    assert len({snapshot.irradiance_wm2 for snapshot in snapshots}) > 5
