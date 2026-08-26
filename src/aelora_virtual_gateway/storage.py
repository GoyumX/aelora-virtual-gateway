from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import PlantState


@dataclass(frozen=True)
class GatewayIdentity:
    gateway_id: str
    credential: str
    telemetry_path: str
    heartbeat_path: str = ""


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_batches (
                    batch_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def _get(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def load_plant(self) -> PlantState:
        raw = self._get("plant")
        return PlantState.model_validate_json(raw) if raw else PlantState.default()

    def save_plant(self, plant: PlantState) -> None:
        self._set("plant", plant.model_dump_json(by_alias=True))

    def load_identity(self) -> GatewayIdentity | None:
        raw = self._get("identity")
        if not raw:
            return None
        data = json.loads(raw)
        data.setdefault("heartbeat_path", f"/api/v1/gateways/{data['gateway_id']}/heartbeats")
        return GatewayIdentity(**data)

    def save_identity(
        self,
        gateway_id: str,
        credential: str,
        telemetry_path: str,
        heartbeat_path: str | None = None,
    ) -> None:
        self._set(
            "identity",
            json.dumps(
                {
                    "gateway_id": gateway_id,
                    "credential": credential,
                    "telemetry_path": telemetry_path,
                    "heartbeat_path": heartbeat_path
                    or f"/api/v1/gateways/{gateway_id}/heartbeats",
                }
            ),
        )

    def update_credential(self, credential: str) -> bool:
        identity = self.load_identity()
        if not identity:
            return False
        self.save_identity(
            identity.gateway_id,
            credential,
            identity.telemetry_path,
            identity.heartbeat_path,
        )
        return True

    def next_sequence(self) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT value FROM settings WHERE key = 'sequence'").fetchone()
            sequence = int(row["value"]) + 1 if row else 1
            connection.execute(
                "INSERT INTO settings(key, value) VALUES ('sequence', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(sequence),),
            )
        return sequence

    def enqueue(self, batch: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO pending_batches(batch_id, sequence, payload) VALUES (?, ?, ?)",
                (batch["batchId"], batch["sequence"], json.dumps(batch)),
            )

    def pending(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM pending_batches ORDER BY sequence").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_pending(self, batch_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM pending_batches WHERE batch_id = ?", (batch_id,))

    def pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM pending_batches").fetchone()
        return int(row["count"])

    def reset(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM settings WHERE key = 'plant'")
