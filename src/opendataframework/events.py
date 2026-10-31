"""Protocol events — an Observer over the protocol calls the framework drives.

Every time the ``Context`` calls a lifecycle or execution protocol method on
a component — a ``Service``'s ``setup()``/``run()``/``stop()``, an
``on_start()``/``on_stop()`` hook, a ``Task``'s or ``Pipeline``'s
``execute()``, an ``Agent``'s ``invoke()``, a ``@Function`` call, a
repository's ``open_stream()``/``stream()``/``close_stream()`` — it emits an
``Event`` when the call starts and when it completes or fails. Nothing else
emits one.

Each event is also written to the component's log file as a record —
``started`` and ``completed`` at ``INFO``, ``failed`` at ``ERROR`` — with its
call id and its parent's as fields, so a call can be traced across files.
``build_trace`` turns events, or those records, into a call tree.

``Events`` is the subject, one per ``Context`` — no process-global state, so
multiple ``Project`` instances in the same process never share listeners
(see ``CLAUDE.md``'s "no global mutable state" constraint). Like ``Logger``,
it is injectable: a constructor parameter annotated ``events: Events``
receives the ``Context``'s own instance. Code holding the ``Context`` reaches
it as ``context.events``.
"""

import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from opendataframework.function import FunctionProtocol
from opendataframework.logger import LogManager

# The ``call_id`` of the protocol call in progress in this thread (or task).
# A ``ContextVar`` holds a separate value per thread, so it is not shared state.
_current_call: ContextVar[str | None] = ContextVar("opendataframework_call", default=None)


def _current_call_id() -> str | None:
    """Return the ``call_id`` of the protocol call in progress in this thread, if any.

    Shared with ``opendataframework.notifications``, which records it as a
    notification's ``parent``.
    """
    return _current_call.get()


@contextmanager
def _no_current_call() -> Iterator[None]:
    """Run the block with no current call, so a call made inside it is top-level.

    Used while listeners run — ``Events``' and ``Notifications``' alike — so a
    call a listener makes is not a child of the call that triggered it.
    """
    token = _current_call.set(None)
    try:
        yield
    finally:
        _current_call.reset(token)


@dataclass(frozen=True)
class Event:
    """One state change of a protocol call the framework made.

    Attributes:
        key: The ``<namespace>.<name>`` key of the component called, as
            ``Context.key()`` returns it.
        protocol: The protocol whose method was called — ``ServiceProtocol``,
            ``OnStartProtocol``, ``TaskProtocol``, ``FunctionProtocol``, ...
        method: The method called — ``"setup"``, ``"on_start"``,
            ``"execute"``, ``"__call__"``, ``"stream"``, ...
        state: ``"started"``, ``"completed"``, or ``"failed"``.
        call_id: Identifies the call; shared by its ``started`` and its
            ``completed``/``failed`` event.
        parent: ``call_id`` of the call in progress in this thread when this
            one started — a pipeline for its steps, a task for a function it
            calls — or ``None`` for a top-level call.
        ts: ``time.time()`` when the event was emitted.
        elapsed_ms: Duration of the call, on ``completed``/``failed`` only.
        error: ``repr()`` of the exception raised, on ``failed`` only.
    """

    key: str
    protocol: type
    method: str
    state: str
    call_id: str
    parent: str | None
    ts: float
    elapsed_ms: float | None = None
    error: str | None = None


class Events:
    """Delivers every ``Event`` of a single ``Context`` to its listeners.

    Not constructed by user code — declare ``events: Events`` in a
    constructor to receive the ``Context``'s instance, or use
    ``context.events``. A listener is any callable taking an ``Event``; it
    runs synchronously, in the thread that made the call, so it must be quick
    and thread-safe — hand slow work off to a queue instead.

    Args:
        log_manager: Where a listener's exception is logged, as a ``WARNING``
            on the event's component. Defaults to a disabled ``LogManager``.

    Example:
        >>> @Component
        ... class FailureAlerts:
        ...     def __init__(self, events: Events) -> None:
        ...         self.queue: Queue[Event | None] = Queue()
        ...         self._unsubscribe = events.subscribe(self.queue.put)
        ...
        ...     def on_stop(self) -> None:
        ...         self._unsubscribe()
    """

    def __init__(self, log_manager: LogManager | None = None) -> None:
        """See class docstring for ``Args``."""
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._listeners: list[tuple[Callable[[Event], None], type | None]] = []
        self._lock = threading.Lock()

    def subscribe(
        self, listener: Callable[[Event], None], protocol: type | None = None
    ) -> Callable[[], None]:
        """Call ``listener`` with every event, or only with calls of ``protocol``'s methods.

        Args:
            listener: Called with each matching ``Event``.
            protocol: Deliver only events whose ``protocol`` is exactly this
                one — ``TaskProtocol`` does not match a ``Pipeline``'s
                ``execute()``. ``None`` (the default) delivers every event.

        Returns:
            A function that unsubscribes ``listener``. Calling it more than
            once is a no-op.

        Example:
            >>> unsubscribe = events.subscribe(on_service, protocol=ServiceProtocol)
            >>> unsubscribe()
        """
        entry = (listener, protocol)
        with self._lock:
            self._listeners.append(entry)

        def unsubscribe() -> None:
            """Stop delivering events to ``listener``."""
            with self._lock:
                if entry in self._listeners:
                    self._listeners.remove(entry)

        return unsubscribe

    @contextmanager
    def notify(self, key: str, protocol: type, method: str) -> Iterator[None]:
        """Emit ``started``, then ``completed`` or ``failed``, around one protocol call.

        Used by the framework at each place it calls a protocol method; not
        meant for user code. While the call runs, it is the current call, so
        calls made inside it get it as their ``parent``. An exception from
        the call is re-raised unchanged. Each event is also written to
        ``key``'s log, as a record with ``message`` ``"<method>() started"``
        and the event's ``call``/``parent``/``protocol``/... as fields.

        Example:
            >>> with events.notify("service.postgres", ServiceProtocol, "setup"):
            ...     instance.setup()
        """
        call_id = uuid4().hex
        parent = _current_call.get()
        self._emit(Event(key, protocol, method, "started", call_id, parent, time.time()))
        token = _current_call.set(call_id)
        start = time.monotonic()
        try:
            yield
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._emit(
                Event(
                    key,
                    protocol,
                    method,
                    "failed",
                    call_id,
                    parent,
                    time.time(),
                    elapsed_ms,
                    repr(exc),
                )
            )
            raise
        else:
            elapsed_ms = (time.monotonic() - start) * 1000
            self._emit(
                Event(key, protocol, method, "completed", call_id, parent, time.time(), elapsed_ms)
            )
        finally:
            _current_call.reset(token)

    def _emit(self, event: Event) -> None:
        """Write ``event`` to its component's log, then deliver it to listeners."""
        label = "call" if event.protocol is FunctionProtocol else f"{event.method}()"
        if event.state == "started":
            message = f"{label} started"
        else:
            message = f"{label} {event.state} in {event.elapsed_ms:.1f}ms"
            if event.error is not None:
                message += f": {event.error}"
        extra: dict[str, object] = {
            "call": event.call_id,
            "parent": event.parent,
            "protocol": event.protocol.__name__,
            "method": event.method,
            "state": event.state,
        }
        if event.elapsed_ms is not None:
            extra["elapsed_ms"] = round(event.elapsed_ms, 3)
        if event.error is not None:
            extra["error"] = event.error
        level = "ERROR" if event.state == "failed" else "INFO"
        self._log_manager.write(event.key, level, message, source="events", extra=extra)
        self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        """Call every listener subscribed to ``event``'s protocol, isolating their failures.

        Listeners run with no current call, so a call one of them makes is a
        top-level call rather than a child of the call that emitted
        ``event``. An exception from a listener is logged and never reaches
        the call.
        """
        with self._lock:
            listeners = [
                listener
                for listener, protocol in self._listeners
                if protocol is None or protocol is event.protocol
            ]
        if not listeners:
            return
        with _no_current_call():
            for listener in listeners:
                try:
                    listener(event)
                except Exception as exc:
                    self._log_manager.write(event.key, "WARNING", f"listener raised {exc!r}")


def build_trace(items: Iterable[Event | Mapping[str, object]], call_id: str) -> dict:
    """Return the call tree rooted at ``call_id``, built from events or log records.

    ``items`` may be live ``Event``\\ s — as a listener receives them — or
    log records, as ``LogManager.records()`` reads them back, in any order
    and mixed. A call's ``started`` and ``completed``/``failed`` are merged
    into one node; a call with no end yet is ``"running"``. Notification
    records attach to the call they were published during, by ``parent``.

    Args:
        items: Events and/or log records. Records that are neither an
            event's nor a notification's are ignored.
        call_id: The root call's id, in full or as a unique prefix — the
            8 characters the ``text`` log format shows.

    Returns:
        A JSON-ready tree. Each node has ``call``, ``parent``, ``key``,
        ``protocol`` (its name), ``method``, ``state``, ``started`` and
        ``ended`` (ISO 8601, or ``None`` when that record isn't there),
        ``elapsed_ms``, ``error``, ``notifications`` (each with ``key``,
        ``topic``, ``level``, ``message``, ``subject``, ``record``, ``ts``)
        and ``children``, ordered by when they started.

    Raises:
        KeyError: If no call matches ``call_id``.
        ValueError: If ``call_id`` is a prefix of more than one call.

    Example:
        >>> received: list[Event] = []
        >>> context.events.subscribe(received.append)
        >>> context.execute("pipeline.nightly-orders")
        >>> build_trace(received, received[0].call_id)["children"][0]["key"]
        'task.price-orders'
    """
    calls: dict[str, dict] = {}
    notifications: dict[str, list[dict]] = {}
    for item in items:
        record = _as_record(item) if isinstance(item, Event) else item
        if record.get("source") == "notifications" and record.get("parent"):
            notifications.setdefault(str(record["parent"]), []).append(
                {
                    "key": record.get("key"),
                    "topic": record.get("topic"),
                    "level": record.get("notification_level"),
                    "message": record.get("message"),
                    "subject": record.get("subject"),
                    "record": record.get("record"),
                    "ts": record.get("ts"),
                }
            )
            continue
        if not record.get("call") or not record.get("state"):
            continue
        node = calls.setdefault(
            str(record["call"]),
            {
                "call": record["call"],
                "parent": record.get("parent"),
                "key": record.get("key"),
                "protocol": record.get("protocol"),
                "method": record.get("method"),
                "state": "running",
                "started": None,
                "ended": None,
                "elapsed_ms": None,
                "error": None,
            },
        )
        if record["state"] == "started":
            node["started"] = record.get("ts")
        else:
            node.update(
                state=record["state"],
                ended=record.get("ts"),
                elapsed_ms=record.get("elapsed_ms"),
                error=record.get("error"),
            )
    root = _match(calls, call_id)
    children: dict[str, list[dict]] = {}
    for node in calls.values():
        if node["parent"]:
            children.setdefault(str(node["parent"]), []).append(node)

    def tree(node: dict) -> dict:
        kids = sorted(children.get(node["call"], []), key=lambda n: str(n["started"] or n["ended"]))
        return {
            **node,
            "notifications": notifications.get(node["call"], []),
            "children": [tree(kid) for kid in kids],
        }

    return tree(root)


def _as_record(event: Event) -> dict:
    """Return ``event`` shaped like the log record ``Events`` writes for it."""
    return {
        "key": event.key,
        "source": "events",
        "call": event.call_id,
        "parent": event.parent,
        "protocol": event.protocol.__name__,
        "method": event.method,
        "state": event.state,
        "ts": datetime.fromtimestamp(event.ts).astimezone().isoformat(timespec="milliseconds"),
        "elapsed_ms": event.elapsed_ms,
        "error": event.error,
    }


def _match(calls: Mapping[str, dict], call_id: str) -> dict:
    """Return the call ``call_id`` names, in full or as a unique prefix."""
    if call_id in calls:
        return calls[call_id]
    matches = [call for call in calls if call.startswith(call_id)] if call_id else []
    if not matches:
        raise KeyError(f"no call {call_id!r} in the trace")
    if len(matches) > 1:
        raise ValueError(f"call id {call_id!r} is ambiguous: it starts {len(matches)} calls")
    return calls[matches[0]]
