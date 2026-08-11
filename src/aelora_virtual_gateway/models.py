from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(word.capitalize() for word in tail)


class GatewayModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PanelArray(GatewayModel):
    external_id: str
    name: str
    panel_count: int = Field(ge=1, le=500)
    rated_power_w: int = Field(ge=50, le=2_000)
    efficiency_pct: float = Field(default=94, ge=0, le=100)
    shading_pct: float = Field(default=0, ge=0, le=100)
    soiling_pct: float = Field(default=0, ge=0, le=100)
    communications_enabled: bool = True
    operating: bool = True


class Inverter(GatewayModel):
    external_id: str = "inverter-main"
    name: str = "Main inverter"
    max_ac_power_w: int = Field(default=5_000, ge=100, le=1_000_000)
    efficiency_pct: float = Field(default=97.5, ge=50, le=100)
    communications_enabled: bool = True
    operating: bool = True


class Battery(GatewayModel):
    external_id: str = "battery-main"
    name: str = "Home battery"
    capacity_wh: int = Field(default=7_680, ge=100)
    state_of_charge_pct: float = Field(default=68, ge=0, le=100)
    min_soc_pct: float = Field(default=10, ge=0, le=100)
    max_soc_pct: float = Field(default=95, ge=0, le=100)
    max_charge_power_w: int = Field(default=3_000, ge=0)
    max_discharge_power_w: int = Field(default=3_000, ge=0)
    communications_enabled: bool = True
    operating: bool = True


class Grid(GatewayModel):
    external_id: str = "grid-main"
    name: str = "Utility grid"
    available: bool = True
    communications_enabled: bool = True
    voltage_v: float = Field(default=230, ge=0, le=500)
    frequency_hz: float = Field(default=50, ge=0, le=100)


Weather = Literal["SUNNY", "PARTLY_CLOUDY", "CLOUDY", "RAINY", "STORM"]


class Environment(GatewayModel):
    weather: Weather = "SUNNY"
    hour_of_day: float = Field(default=12, ge=0, le=23.99)
    ambient_temperature_c: float = Field(default=29, ge=-50, le=80)
    manual_irradiance_wm2: int | None = Field(default=None, ge=0, le=1_500)


class PlantState(GatewayModel):
    arrays: list[PanelArray]
    inverter: Inverter = Field(default_factory=Inverter)
    battery: Battery = Field(default_factory=Battery)
    grid: Grid = Field(default_factory=Grid)
    environment: Environment = Field(default_factory=Environment)
    load_power_w: int = Field(default=2_200, ge=0, le=1_000_000)
    publishing_enabled: bool = True
    publish_interval_sec: int = Field(default=30, ge=10, le=3_600)

    @classmethod
    def default(cls) -> PlantState:
        return cls(
            arrays=[
                PanelArray(external_id="array-east", name="East roof", panel_count=8, rated_power_w=440),
                PanelArray(external_id="array-west", name="West roof", panel_count=8, rated_power_w=440),
            ]
        )


class SiteSnapshot(GatewayModel):
    observed_at: datetime
    pv_power_w: float
    pv_energy_today_wh: float
    load_power_w: float
    grid_power_w: float
    battery_power_w: float
    battery_soc_pct: float
    dc_voltage_v: float
    dc_current_a: float
    ac_voltage_v: float
    ac_current_a: float
    grid_voltage_v: float
    frequency_hz: float
    inverter_temperature_c: float
    panel_temperature_c: float
    irradiance_wm2: float
    device_status: str


class DeviceObservation(GatewayModel):
    external_id: str
    kind: Literal["PV_ARRAY", "INVERTER", "BATTERY", "GRID_METER", "LOAD_METER", "WEATHER_SENSOR"]
    name: str
    reported_at: datetime
    last_telemetry_at: datetime | None
    connectivity_status: Literal["NEVER_SEEN", "ONLINE", "STALE", "OFFLINE"]
    operational_state: Literal["UNKNOWN", "RUNNING", "STANDBY", "STOPPED", "FAULT"]
    quality: Literal["SIMULATED", "MEASURED", "ESTIMATED", "STALE", "MISSING"]
    metrics: dict[str, Any]


class SimulationTick(GatewayModel):
    site_snapshot: SiteSnapshot
    devices: list[DeviceObservation]

    def device(self, external_id: str) -> DeviceObservation:
        return next(device for device in self.devices if device.external_id == external_id)

    def to_batch(self, gateway_id: str, sequence: int, batch_id: str) -> dict[str, Any]:
        return {
            "schemaVersion": "1.0",
            "batchId": batch_id,
            "gatewayId": gateway_id,
            "sequence": sequence,
            "sentAt": self.site_snapshot.observed_at.isoformat(),
            "source": "VIRTUAL",
            "siteSnapshot": self.site_snapshot.model_dump(mode="json", by_alias=True),
            "devices": [device.model_dump(mode="json", by_alias=True) for device in self.devices],
        }


class PanelArrayCreate(GatewayModel):
    external_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    panel_count: int = Field(ge=1, le=500)
    rated_power_w: int = Field(ge=50, le=2_000)


class EnvironmentUpdate(GatewayModel):
    weather: Weather | None = None
    hour_of_day: float | None = Field(default=None, ge=0, le=23.99)
    ambient_temperature_c: float | None = Field(default=None, ge=-50, le=80)
    manual_irradiance_wm2: int | None = Field(default=None, ge=0, le=1_500)


class DeviceControl(GatewayModel):
    communications_enabled: bool | None = None
    operating: bool | None = None
    efficiency_pct: float | None = Field(default=None, ge=0, le=100)
    shading_pct: float | None = Field(default=None, ge=0, le=100)
    soiling_pct: float | None = Field(default=None, ge=0, le=100)
    available: bool | None = None
    max_ac_power_w: int | None = Field(default=None, ge=100, le=1_000_000)
    state_of_charge_pct: float | None = Field(default=None, ge=0, le=100)


class PublishingUpdate(GatewayModel):
    enabled: bool | None = None
    interval_sec: int | None = Field(default=None, ge=10, le=3_600)


class LoadUpdate(GatewayModel):
    load_power_w: int = Field(ge=0, le=1_000_000)
