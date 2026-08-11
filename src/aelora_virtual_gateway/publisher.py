from __future__ import annotations

from typing import Any

import httpx

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
        self.store.save_identity(data["gatewayId"], data["credential"], data["telemetryPath"])
        return self.store.load_identity()  # type: ignore[return-value]

    def _send(self, batch: dict[str, Any], identity: GatewayIdentity) -> bool:
        try:
            response = self.client.post(
                identity.telemetry_path,
                json=batch,
                headers={"Authorization": f"Bearer {identity.credential}"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    def publish(self, batch: dict[str, Any]) -> bool:
        identity = self.store.load_identity()
        if not identity or not self._send(batch, identity):
            self.store.enqueue(batch)
            return False
        return True

    def flush_pending(self) -> int:
        identity = self.store.load_identity()
        if not identity:
            return 0
        sent = 0
        for batch in self.store.pending():
            if not self._send(batch, identity):
                break
            self.store.delete_pending(batch["batchId"])
            sent += 1
        return sent
