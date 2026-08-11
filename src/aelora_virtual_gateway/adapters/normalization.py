from __future__ import annotations

from datetime import datetime

from ..models import DeviceObservation, SimulationTick, SiteSnapshot


def measured_observation(
    *,
    external_id: str,
    kind: str,
    name: str,
    observed_at: datetime,
    metrics: dict[str, float],
) -> DeviceObservation:
    return DeviceObservation(
        external_id=external_id,
        kind=kind,
        name=name,
        reported_at=observed_at,
        last_telemetry_at=observed_at,
        connectivity_status="ONLINE",
        operational_state="RUNNING",
        quality="MEASURED",
        metrics=metrics,
    )


def build_measured_tick(
    *,
    observed_at: datetime,
    pv_power_w: float,
    pv_energy_today_wh: float,
    load_power_w: float,
    grid_power_w: float,
    battery_power_w: float,
    battery_soc_pct: float,
    dc_voltage_v: float,
    dc_current_a: float,
    ac_voltage_v: float,
    ac_current_a: float,
    grid_voltage_v: float,
    frequency_hz: float,
    inverter_temperature_c: float,
    panel_temperature_c: float,
    irradiance_wm2: float,
) -> SimulationTick:
    snapshot = SiteSnapshot(
        observed_at=observed_at,
        pv_power_w=pv_power_w,
        pv_energy_today_wh=pv_energy_today_wh,
        load_power_w=load_power_w,
        grid_power_w=grid_power_w,
        battery_power_w=battery_power_w,
        battery_soc_pct=battery_soc_pct,
        dc_voltage_v=dc_voltage_v,
        dc_current_a=dc_current_a,
        ac_voltage_v=ac_voltage_v,
        ac_current_a=ac_current_a,
        grid_voltage_v=grid_voltage_v,
        frequency_hz=frequency_hz,
        inverter_temperature_c=inverter_temperature_c,
        panel_temperature_c=panel_temperature_c,
        irradiance_wm2=irradiance_wm2,
        device_status="NORMAL",
    )
    devices = [
        measured_observation(
            external_id="inverter-main",
            kind="INVERTER",
            name="Main inverter",
            observed_at=observed_at,
            metrics={
                "acPowerW": pv_power_w,
                "acVoltageV": ac_voltage_v,
                "frequencyHz": frequency_hz,
                "temperatureC": inverter_temperature_c,
            },
        ),
        measured_observation(
            external_id="battery-main",
            kind="BATTERY",
            name="Battery",
            observed_at=observed_at,
            metrics={"powerW": battery_power_w, "socPct": battery_soc_pct},
        ),
        measured_observation(
            external_id="grid-main",
            kind="GRID_METER",
            name="Grid meter",
            observed_at=observed_at,
            metrics={"powerW": grid_power_w, "voltageV": grid_voltage_v},
        ),
    ]
    return SimulationTick(source="HARDWARE", site_snapshot=snapshot, devices=devices)
