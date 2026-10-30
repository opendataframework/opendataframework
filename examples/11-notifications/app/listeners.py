import threading
from collections import Counter
from collections.abc import Callable
from typing import Annotated

from app.functions import schedule_bake
from opendataframework import Component, Notification, Notifications


@Component
class Kitchen:
    """Reacts to every received order by scheduling a bake."""

    def __init__(
        self,
        notifications: Notifications,
        schedule: Annotated[Callable[..., str], schedule_bake],
    ) -> None:
        self.schedule = schedule
        self.bakes: list[tuple[Notification, str]] = []
        self._lock = threading.Lock()
        self._unsubscribe = notifications.subscribe(self._on_order, topic="orders.received")

    def _on_order(self, notification: Notification) -> None:
        # A listener runs with no current call, so this call is top-level —
        # it relates to TakeOrders' execute() through notification.parent,
        # not by being nested under it.
        bake = self.schedule(order_id=notification.record)
        with self._lock:
            self.bakes.append((notification, bake))

    def on_stop(self) -> None:
        self._unsubscribe()


@Component
class OrderCounter:
    """Counts every orders.* notification, by topic."""

    def __init__(self, notifications: Notifications) -> None:
        self.counts: Counter[str] = Counter()
        self._lock = threading.Lock()
        self._unsubscribe = notifications.subscribe(self._count, topic="orders.*")

    def _count(self, notification: Notification) -> None:
        with self._lock:
            self.counts[notification.topic] += 1

    def on_stop(self) -> None:
        self._unsubscribe()
