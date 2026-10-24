import threading
from collections import Counter
from queue import Queue

from opendataframework import Component, Event, Events, FunctionProtocol


@Component
class CallTrace:
    """Records every protocol call, to print them as a tree afterwards."""

    def __init__(self, events: Events) -> None:
        self._lock = threading.Lock()  # listeners are called from several threads
        self._calls: dict[str, Event] = {}  # call_id → its started event, in start order
        self._outcome: dict[str, str] = {}  # call_id → "completed" | "failed"
        # Subscribed in __init__, so the startup calls are recorded too.
        self._unsubscribe = events.subscribe(self._record)

    def _record(self, event: Event) -> None:
        with self._lock:
            if event.state == "started":
                self._calls[event.call_id] = event
            else:
                self._outcome[event.call_id] = event.state

    def tree(self, key: str) -> list[str]:
        """Return the calls of ``key`` and everything they called, indented by depth."""
        with self._lock:
            calls = list(self._calls.values())
            outcome = dict(self._outcome)
        lines: list[str] = []

        def walk(call: Event, depth: int) -> None:
            state = outcome.get(call.call_id, "running")
            name = f"{call.key} {call.method}()"
            lines.append(
                f"{'  ' * depth}{name:<{40 - 2 * depth}} {call.protocol.__name__:<17} {state}"
            )
            for child in calls:
                if child.parent == call.call_id:
                    walk(child, depth + 1)

        for call in calls:
            if call.key == key and call.parent is None:
                walk(call, 0)
        return lines

    def seen(self) -> list[str]:
        """Return every distinct call recorded, as ``key method()``, sorted."""
        with self._lock:
            return sorted({f"{call.key} {call.method}()" for call in self._calls.values()})

    def on_stop(self) -> None:
        self._unsubscribe()


@Component
class FailureAlerts:
    """Puts every failed call on a queue, for AlertSender to send."""

    def __init__(self, events: Events) -> None:
        self.queue: Queue[Event | None] = Queue()
        self._unsubscribe = events.subscribe(self._on_event)

    def _on_event(self, event: Event) -> None:
        # Only enqueue: a listener runs inside the call, so slow work here
        # would hold the call up.
        if event.state == "failed":
            self.queue.put(event)

    def on_stop(self) -> None:
        self._unsubscribe()


@Component
class FunctionCalls:
    """Counts calls of registered functions, using a protocol filter."""

    def __init__(self, events: Events) -> None:
        self.counts: Counter[str] = Counter()
        self._lock = threading.Lock()
        self._unsubscribe = events.subscribe(self._count, protocol=FunctionProtocol)

    def _count(self, event: Event) -> None:
        if event.state == "completed":
            with self._lock:
                self.counts[event.key] += 1

    def on_stop(self) -> None:
        self._unsubscribe()
