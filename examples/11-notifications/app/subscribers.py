import threading
from collections import Counter
from collections.abc import Callable
from typing import Annotated

from app.functions import schedule_bake
from opendataframework import Component, Notification, Subscriber


@Subscriber("orders.received")
@Component
class Kitchen:
    """Reacts to every received order by scheduling a bake."""

    def __init__(self, schedule: Annotated[Callable[..., str], schedule_bake]) -> None:
        self.schedule = schedule
        self.bakes: list[tuple[Notification, str]] = []
        self._lock = threading.Lock()

    def on_notification(self, notification: Notification) -> None:
        # Called by the Context, as a traced call caused by the notification:
        # it is top-level (no parent), and schedule_bake() is its child.
        bake = self.schedule(order_id=notification.record)
        with self._lock:
            self.bakes.append((notification, bake))


@Subscriber("orders.*", deliver="background")
@Component
class OrderCounter:
    """Counts every orders.* notification, by topic, off the publisher's thread."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self._lock = threading.Lock()

    def on_notification(self, notification: Notification) -> None:
        with self._lock:
            self.counts[notification.topic] += 1
