from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from . import __version__
from .engine import SimulationEngine
from .models import PlantState, SimulationTick
from .publisher import AeloraPublisher
from .storage import StateStore


class GatewayRuntime:
    def __init__(
        self, store: StateStore, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.store = store
        self.plant = store.load_plant()
        self.engine = SimulationEngine(self.plant)
        self.publisher = AeloraPublisher(store, base_url, transport=transport)
        self.latest: SimulationTick | None = None
        self.lock = threading.RLock()

    def save(self) -> None:
        self.store.save_plant(self.plant)

    def tick(self, observed_at: datetime | None = None) -> SimulationTick:
        with self.lock:
            self.latest = self.engine.tick(observed_at or datetime.now(UTC))
            self.save()
            return self.latest

    def enroll(self, token: str) -> None:
        self.publisher.enroll(token, __version__)

    def publish_once(self) -> bool:
        identity = self.store.load_identity()
        if not identity:
            return False
        self.publisher.flush_pending()
        tick = self.tick()
        sequence = self.store.next_sequence()
        batch = tick.to_batch(identity.gateway_id, sequence, str(uuid4()))
        return self.publisher.publish(batch)

    def reset(self) -> PlantState:
        with self.lock:
            self.store.reset()
            self.plant = PlantState.default()
            self.engine = SimulationEngine(self.plant)
            self.latest = None
            self.save()
            return self.plant

    def close(self) -> None:
        self.publisher.close()
