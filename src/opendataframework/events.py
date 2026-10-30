"""Protocol events — an Observer over the protocol calls the framework drives.

Every time the ``Context`` calls a lifecycle or execution protocol method on
a component — a ``Service``'s ``setup()``/``run()``/``stop()``, an
``on_start()``/``on_stop()`` hook, a ``Task``'s or ``Pipeline``'s
``execute()``, an ``Agent``'s ``invoke()``, a ``@Function`` call, a
repository's ``open_stream()``/``stream()``/``close_stream()`` — it emits an
``Event`` when the call starts and when it completes or fails. Nothing else
emits one.

``Events`` is the subject, one per ``Context`` — no process-global state, so
multiple ``Project`` instances in the same process never share listeners
(see ``CLAUDE.md``'s "no global mutable state" constraint). Like ``Logger``,
it is injectable: a constructor parameter annotated ``events: Events``
receives the ``Context``'s own instance. Code holding the ``Context`` reaches
it as ``context.events``.
"""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

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
        the call is re-raised unchanged.

        Example:
            >>> with events.notify("service.postgres", ServiceProtocol, "setup"):
            ...     instance.setup()
        """
        call_id = uuid4().hex
        parent = _current_call.get()
        self._dispatch(Event(key, protocol, method, "started", call_id, parent, time.time()))
        token = _current_call.set(call_id)
        start = time.monotonic()
        try:
            yield
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            failed = Event(
                key, protocol, method, "failed", call_id, parent, time.time(), elapsed_ms, repr(exc)
            )
            self._dispatch(failed)
            raise
        else:
            elapsed_ms = (time.monotonic() - start) * 1000
            completed = Event(
                key, protocol, method, "completed", call_id, parent, time.time(), elapsed_ms
            )
            self._dispatch(completed)
        finally:
            _current_call.reset(token)

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
