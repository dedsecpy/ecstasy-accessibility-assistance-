"""Fan-out of worker events (Postgres LISTEN/NOTIFY) to SSE subscribers, per venue."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import psycopg

from nimbus_core.config import get_settings
from nimbus_core.db import EVENTS_CHANNEL

log = logging.getLogger("api.events")


class Broadcaster:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._task: asyncio.Task | None = None

    def subscribe(self, venue_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.setdefault(venue_id, set()).add(q)
        return q

    def unsubscribe(self, venue_id: str, q: asyncio.Queue) -> None:
        self._subs.get(venue_id, set()).discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(event.get("venue_id", ""), set())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def _listen(self) -> None:
        url = get_settings().database_url
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
                    await conn.execute(f"LISTEN {EVENTS_CHANNEL}")
                    log.info("listening for worker events")
                    async for n in conn.notifies():
                        try:
                            self.publish(json.loads(n.payload))
                        except ValueError:
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("event listener reconnecting: %s", e)
                await asyncio.sleep(2)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


broadcaster = Broadcaster()
