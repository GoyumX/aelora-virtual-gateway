from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .models import (
    BatteryUpdate,
    CredentialUpdate,
    DeviceControl,
    EnvironmentUpdate,
    LoadUpdate,
    PanelArray,
    PanelArrayCreate,
    PublishingUpdate,
    ScenarioRequest,
)
from .runtime import GatewayRuntime
from .storage import StateStore

STATIC_DIR = Path(__file__).parent / "static"


class EnrollmentRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class ReplayHourRequest(BaseModel):
    start_at: datetime = Field(alias="startAt")


async def publisher_loop(runtime: GatewayRuntime) -> None:
    while True:
        await asyncio.to_thread(runtime.heartbeat_once)
        if runtime.plant.publishing_enabled:
            await asyncio.to_thread(runtime.publish_once)
        await asyncio.sleep(runtime.plant.publish_interval_sec)


def create_app(
    store: StateStore | None = None,
    *,
    start_publisher: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    database_path = os.getenv("AELORA_GATEWAY_DB", "data/gateway.db")
    runtime = GatewayRuntime(
        store or StateStore(database_path),
        os.getenv("AELORA_BASE_URL", "http://localhost:3000"),
        transport=transport,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime
        runtime.tick()
        task = asyncio.create_task(publisher_loop(runtime)) if start_publisher else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        runtime.close()

    app = FastAPI(title="Aelora Virtual Gateway", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def prevent_console_version_mismatch(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    def get_state() -> dict:
        identity = runtime.store.load_identity()
        return {
            "plant": runtime.plant.model_dump(mode="json", by_alias=True),
            "clock": runtime.clock_state(),
            "gateway": {
                "enrolled": identity is not None,
                "gatewayId": identity.gateway_id if identity else None,
                "aeloraBaseUrl": runtime.publisher.base_url,
                "pendingBatches": runtime.store.pending_count(),
            },
            "latest": runtime.latest.model_dump(mode="json", by_alias=True) if runtime.latest else None,
            "scenario": runtime.scenario_state(),
            "outbound": runtime.publisher.outbound_preview,
        }

    @app.post("/api/tick")
    def tick() -> dict:
        return runtime.tick().model_dump(mode="json", by_alias=True)

    @app.post("/api/arrays", status_code=status.HTTP_201_CREATED)
    def add_array(payload: PanelArrayCreate) -> dict:
        if any(array.external_id == payload.external_id for array in runtime.plant.arrays):
            raise HTTPException(status_code=409, detail="A device already uses this external ID.")
        array = PanelArray(**payload.model_dump())
        runtime.plant.arrays.append(array)
        runtime.save()
        runtime.tick()
        return array.model_dump(mode="json", by_alias=True)

    @app.delete("/api/arrays/{external_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_array(external_id: str) -> None:
        before = len(runtime.plant.arrays)
        runtime.plant.arrays = [array for array in runtime.plant.arrays if array.external_id != external_id]
        if len(runtime.plant.arrays) == before:
            raise HTTPException(status_code=404, detail="Array not found.")
        runtime.save()

    @app.patch("/api/environment")
    def update_environment(payload: EnvironmentUpdate) -> dict:
        try:
            environment = runtime.update_environment(payload.model_dump(exclude_unset=True))
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.errors(include_url=False, include_context=False),
            ) from error
        return environment.model_dump(mode="json", by_alias=True)

    @app.patch("/api/devices/{external_id}/control")
    def update_device(external_id: str, payload: DeviceControl) -> dict:
        device = next((array for array in runtime.plant.arrays if array.external_id == external_id), None)
        if device is None and runtime.plant.inverter.external_id == external_id:
            device = runtime.plant.inverter
        if device is None and runtime.plant.battery.external_id == external_id:
            device = runtime.plant.battery
        if device is None and runtime.plant.grid.external_id == external_id:
            device = runtime.plant.grid
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found.")
        for key, value in payload.model_dump(exclude_unset=True).items():
            if value is not None and hasattr(device, key):
                setattr(device, key, value)
        runtime.save()
        runtime.tick()
        return {"updated": True, "externalId": external_id}

    @app.patch("/api/publishing")
    def update_publishing(payload: PublishingUpdate) -> dict:
        if payload.enabled is not None:
            runtime.plant.publishing_enabled = payload.enabled
        if payload.interval_sec is not None:
            runtime.plant.publish_interval_sec = payload.interval_sec
        runtime.save()
        cadence_synchronized = runtime.heartbeat_once()
        return {
            "enabled": runtime.plant.publishing_enabled,
            "intervalSec": runtime.plant.publish_interval_sec,
            "cadenceSynchronized": cadence_synchronized,
        }

    @app.patch("/api/load")
    def update_load(payload: LoadUpdate) -> dict:
        try:
            plant = runtime.update_load(payload.model_dump(exclude_unset=True))
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.errors(include_url=False, include_context=False),
            ) from error
        return {
            "loadMode": plant.load_mode,
            "loadPowerW": plant.load_power_w,
            "loadMinPowerW": plant.load_min_power_w,
            "loadMaxPowerW": plant.load_max_power_w,
        }

    @app.patch("/api/battery")
    def update_battery(payload: BatteryUpdate) -> dict:
        try:
            battery = runtime.update_battery(payload.model_dump(exclude_unset=True))
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.errors(include_url=False, include_context=False),
            ) from error
        return battery.model_dump(mode="json", by_alias=True)

    @app.post("/api/enroll")
    def enroll(payload: EnrollmentRequest) -> dict:
        try:
            runtime.enroll(payload.token)
        except httpx.HTTPStatusError as error:
            detail = error.response.json().get("error", {}).get("message", "Aelora rejected enrollment.")
            raise HTTPException(status_code=502, detail=detail) from error
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail="Aelora could not be reached.") from error
        return {"enrolled": True, "gatewayId": runtime.store.load_identity().gateway_id}

    @app.post("/api/publish-now")
    def publish_now() -> dict:
        if not runtime.store.load_identity():
            raise HTTPException(status_code=409, detail="Enroll this gateway first.")
        return {"published": runtime.publish_once(), "pendingBatches": runtime.store.pending_count()}

    @app.post("/api/development/replay-hour")
    def replay_hour(payload: ReplayHourRequest) -> dict:
        if not runtime.store.load_identity():
            raise HTTPException(status_code=409, detail="Enroll this gateway before replaying data.")
        try:
            return runtime.replay_completed_hour(payload.start_at)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.patch("/api/identity/credential")
    def update_credential(payload: CredentialUpdate) -> dict:
        if not runtime.update_credential(payload.credential):
            raise HTTPException(status_code=409, detail="Enroll this gateway before applying a rotation.")
        return {"updated": True}

    @app.post("/api/scenarios", status_code=status.HTTP_201_CREATED)
    def start_scenario(payload: ScenarioRequest) -> dict:
        return runtime.start_scenario(payload.code, payload.duration_sec)

    @app.delete("/api/scenarios/current")
    def stop_scenario() -> dict:
        runtime.stop_scenario()
        return {"stopped": True}

    @app.post("/api/reset")
    def reset() -> dict:
        return runtime.reset().model_dump(mode="json", by_alias=True)

    return app


app = create_app()
