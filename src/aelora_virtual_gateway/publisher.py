from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from . import __version__
from .storage import GatewayIdentity, StateStore


class AeloraPublisher:
    def __init__(
        self,
        store: StateStore,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=10, transport=transport)
        self.outbound_preview: dict[str, Any] | None = None

    def close(self) -> None:
        self.client.close()

    def enroll(self, token: str, software_version: str) -> GatewayIdentity:
        response = self.client.post(
            "/api/v1/gateway-enrollments",
            json={
                "enrollmentToken": token,
                "softwareVersion": software_version,
            },
        )
        response.raise_for_status()
        data = response.json()["data"]
        self.store.save_identity(
            data["gatewayId"],
            data["credential"],
            data["telemetryPath"],
            data.get("heartbeatPath"),
        )
        return self.store.load_identity()  # type: ignore[return-value]

    def _send(self, path: str, payload: dict[str, Any], identity: GatewayIdentity) -> bool:
        sent_at = datetime.now(UTC).isoformat()
        self.outbound_preview = {
            "request": {
                "method": "POST",
                "path": path,
                "headers": {
                    "Authorization": "Bearer <redacted>",
                    "Content-Type": "application/json",
                },
                "body": payload,
            },
            "result": {"ok": False, "statusCode": None, "sentAt": sent_at},
        }
        try:
            response = self.client.post(
                path,
                json=payload,
                headers={"Authorization": f"Bearer {identity.credential}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            self.outbound_preview["result"] = {
                "ok": False,
                "statusCode": error.response.status_code,
                "sentAt": sent_at,
            }
            return False
        except httpx.HTTPError:
            return False
        self.outbound_preview["result"] = {
            "ok": True,
            "statusCode": response.status_code,
            "sentAt": sent_at,
        }
        return True

    def publish(self, batch: dict[str, Any]) -> bool:
        identity = self.store.load_identity()
        if not identity or not self._send(identity.telemetry_path, batch, identity):
            self.store.enqueue(batch)
            return False
        return True

    def heartbeat(
        self,
        *,
        publishing_enabled: bool,
        publish_interval_sec: int,
        queue_depth: int,
        device_count: int,
        heartbeat_id: str | None = None,
        sent_at: datetime | None = None,
    ) -> bool:
        identity = self.store.load_identity()
        if not identity:
            return False
        timestamp = sent_at or datetime.now(UTC)
        payload = {
            "schemaVersion": "1.0",
            "heartbeatId": heartbeat_id or str(uuid4()),
            "gatewayId": identity.gateway_id,
            "sentAt": timestamp.isoformat(),
            "softwareVersion": __version__,
            "publishingEnabled": publishing_enabled,
            "publishIntervalSec": publish_interval_sec,
            "queueDepth": queue_depth,
            "deviceCount": device_count,
        }
        return self._send(identity.heartbeat_path, payload, identity)

    def flush_pending(self) -> int:
        identity = self.store.load_identity()
        if not identity:
            return 0
        sent = 0
        for batch in self.store.pending():
            if not self._send(identity.telemetry_path, batch, identity):
                break
            self.store.delete_pending(batch["batchId"])
            sent += 1
        return sent
