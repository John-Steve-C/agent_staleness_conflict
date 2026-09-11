from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar


PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True)
class ScheduledNotification(Generic[PayloadT]):
    notification_id: str
    payload: PayloadT
    release_after_write: int | None = None
    release_at: float | None = None


class StalenessScheduler(Generic[PayloadT]):
    """Deterministically delays refusal notifications by writes or wall time."""

    def __init__(self) -> None:
        self.write_count = 0
        self._pending: list[ScheduledNotification[PayloadT]] = []

    def buffer_by_writes(
        self, notification_id: str, payload: PayloadT, intervening_writes: int
    ) -> None:
        if intervening_writes < 0:
            raise ValueError("intervening_writes must be non-negative")
        self._pending.append(
            ScheduledNotification(
                notification_id=notification_id,
                payload=payload,
                release_after_write=self.write_count + intervening_writes,
            )
        )

    def buffer_by_time(
        self,
        notification_id: str,
        payload: PayloadT,
        delay_seconds: float,
        *,
        now: float | None = None,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        current_time = time.monotonic() if now is None else now
        self._pending.append(
            ScheduledNotification(
                notification_id=notification_id,
                payload=payload,
                release_at=current_time + delay_seconds,
            )
        )

    def record_write(self, count: int = 1) -> None:
        if count < 0:
            raise ValueError("count must be non-negative")
        self.write_count += count

    def pop_ready(self, *, now: float | None = None) -> list[ScheduledNotification[PayloadT]]:
        current_time = time.monotonic() if now is None else now
        ready: list[ScheduledNotification[PayloadT]] = []
        waiting: list[ScheduledNotification[PayloadT]] = []
        for item in self._pending:
            write_ready = (
                item.release_after_write is not None
                and self.write_count >= item.release_after_write
            )
            time_ready = item.release_at is not None and current_time >= item.release_at
            (ready if write_ready or time_ready else waiting).append(item)
        self._pending = waiting
        return ready

    @property
    def pending_count(self) -> int:
        return len(self._pending)
