"""Notifications — messages component code publishes about something that happened.

An ``Event`` (see ``opendataframework.events``) records a protocol call the
framework made; a ``Notification`` is the other half: a component publishes
one — a topic, a payload, an optional human-readable summary — about
something it did or saw (a file arrived, a sensor crossed a threshold, a
training run finished), so that others can react without the publisher
knowing who they are. Only component
code publishes one; the framework never does.

``Notifications`` is the hub, one per ``Context`` — no process-global state,
so multiple ``Project`` instances in the same process never share
subscribers. Like ``Logger``, it is injectable, and contextually so: a
constructor or function parameter annotated ``notifications: Notifications``
receives a view bound to the consuming component's own key, so its
``publish()`` needs no key. Code holding the ``Context`` reaches the unbound
hub as ``context.notifications``.

Unrelated to ``Events.notify()``, which emits ``Event``\\ s around a protocol
call.
"""

import copy
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, get_args, runtime_checkable
from uuid import uuid4

from opendataframework.function import Function
from opendataframework.logger import LogManager, _current_call_id, _no_current_call
from opendataframework.namespace import ExecutionType, describe

Level = Literal["info", "success", "warning", "error"]
_LEVELS: tuple[str, ...] = get_args(Level)
# The log level a notification's publish line is written at.
_LOG_LEVELS: dict[str, str] = {
    "info": "INFO",
    "success": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
}
Delivery = Literal["sync", "background"]
_DELIVERIES: tuple[str, ...] = get_args(Delivery)
# Attributes the decorators below set on what they mark.
_SUBSCRIBER = "__odf_subscriber__"
_PUBLISHER = "__odf_publisher__"
# A subscription: (listener, topic filter(s) — None for every topic —,
# subscriber key, whether a @Subscriber declared it).
type _Entry = tuple[Callable[[Any], None], str | tuple[str, ...] | None, str | None, bool]


@dataclass(frozen=True)
class Notification:
    """One message a component published.

    Attributes:
        key: The ``<namespace>.<name>`` key of the publishing component, as
            ``Context.key()`` returns it.
        topic: Dotted name of what happened — ``"orders.received"``,
            ``"margins.below-cost"``.
        payload: Data for subscribers, read-only all the way down (nested
            lists arrive as tuples); ``{}`` when none was given.
            Keep it JSON-serialisable, so a UI can show it.
        summary: One human-readable line, or ``None``. A UI shows only
            notifications that have one.
        level: ``"info"``, ``"success"``, ``"warning"``, or ``"error"``.
        subject: Key of the component the notification is about — e.g.
            ``"repository.orders"`` — or ``None``.
        record: Id of the record it is about, within ``subject``, or ``None``.
        parent: ``call_id`` of the protocol call in progress in the
            publisher's thread — see ``Event.call_id`` — or ``None`` when
            published outside one.
        ts: ``time.time()`` when published.
        id: Identifies the notification — ``uuid4().hex``, unique per
            publish. A call its listeners make records it as its ``cause``
            (see ``Event.cause``), and its log record carries it as
            ``notification``, so it can be referred to: deduplicated,
            acknowledged, or followed in a trace.
    """

    key: str
    topic: str
    payload: Mapping[str, Any]
    summary: str | None
    level: Level
    subject: str | None
    record: object | None
    parent: str | None
    ts: float
    id: str = field(default_factory=lambda: uuid4().hex)


class Notifications:
    """Delivers the ``Notification``\\ s published in a single ``Context`` to its subscribers.

    Not constructed by user code — declare ``notifications: Notifications``
    to receive a view bound to your component's key, or use
    ``context.notifications`` for the unbound hub. A listener is any callable
    taking a ``Notification``; it runs synchronously, in the publisher's
    thread, so it must be quick and thread-safe — hand slow work off to a
    queue or a ``Service`` instead.

    Args:
        log_manager: Where each publish, and a listener's exception, is
            logged. Defaults to a disabled ``LogManager``.
        key_of: Returns the key of a class or function, for a ``subject``
            given as one. ``None`` accepts key strings only.

    Example:
        >>> @Task
        ... class TakeOrder:
        ...     def __init__(self, orders: Orders, notifications: Notifications) -> None:
        ...         self.orders = orders
        ...         self.notifications = notifications
        ...
        ...     def execute(self, customer: str, item: str) -> None:
        ...         order = self.orders.add(customer, item)
        ...         self.notifications.publish(
        ...             "orders.received",
        ...             {"id": order.id, "item": item},
        ...             summary=f"{customer}: {item}",
        ...             subject=Orders,
        ...             record=order.id,
        ...         )
    """

    def __init__(
        self,
        log_manager: LogManager | None = None,
        key_of: Callable[[Any], str] | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._key_of = key_of
        self._listeners: list[_Entry] = []
        self._lock = threading.Lock()
        self._key: str | None = None
        self._publishes: tuple[str, ...] | None = None

    def bound_to(self, key: str, publishes: tuple[str, ...] | None = None) -> Notifications:
        """Return a view of this hub that publishes and subscribes as ``key``.

        Used by the framework to inject a ``notifications: Notifications``
        parameter; not meant for user code. The view shares this hub's
        subscribers, and enforces the publishing rules — see ``publish()``.

        Args:
            key: The consumer's ``<namespace>.<name>`` key.
            publishes: The topic filters its ``@Publisher`` declares, or
                ``None`` when it isn't one.
        """
        view = copy.copy(self)  # shallow: shares _listeners and _lock
        view._key = key
        view._publishes = publishes
        return view

    def publish(
        self,
        topic: str,
        payload: Mapping[str, Any] | None = None,
        *,
        summary: str | None = None,
        level: Level = "info",
        subject: str | type | Callable[..., object] | None = None,
        record: object | None = None,
        key: str | None = None,
    ) -> Notification:
        """Deliver a notification to every subscriber whose topic filter matches it.

        Through an injected view, three rules apply, so that the framework
        knows every publisher and every notification can be traced: the
        component (or function) must be a ``@Publisher``, ``topic`` must be
        one it declares, and a protocol call must be in progress — inside
        ``execute()``, ``run()``, ``on_start()``, ``on_notification()``, a
        ``@Function`` call, ..., never in ``__init__`` or a thread of its
        own. The unbound ``context.notifications`` is exempt from all three.

        Listeners run before this returns, with no current call; an exception
        from one is logged and never raised here. Each publish is also logged
        on the publisher's key, as a record with ``message``
        ``"notified <topic>: <summary>"`` and ``topic``, ``subject``,
        ``record`` and ``parent`` as fields (never ``payload``), at the log
        level matching ``level`` (``success`` logs as ``INFO``).

        Args:
            topic: Dotted name of what happened. Non-empty, with no ``*``.
            payload: Data for subscribers. Its containers are copied and
                delivered read-only all the way down — nested lists arrive
                as tuples, sets as frozensets; see ``_freeze``.
            summary: One human-readable line, for a UI to show.
            level: ``"info"`` (the default), ``"success"``, ``"warning"``, or
                ``"error"``.
            subject: The component the notification is about — a class or
                function, resolved to its key, or a key string.
            record: Id of the record it is about, within ``subject``.
            key: The publisher's key. Defaults to the key this view is bound
                to; required on the unbound ``context.notifications``.

        Returns:
            The ``Notification`` delivered.

        Raises:
            TypeError: If no ``key`` is given and this view is unbound, or
                this view's component or function is not a ``@Publisher``.
            ValueError: If ``topic`` or ``level`` is invalid, or ``topic`` is
                not one this view's ``@Publisher`` declares.
            RuntimeError: If this is an injected view and no protocol call
                is in progress.
            KeyError: If ``subject`` is a class or function that was not
                resolved.

        Example:
            >>> notifications.publish("orders.received", {"id": 7}, summary="Le Petit: 2 baguettes")
        """
        if not topic or "*" in topic:
            raise ValueError(f"invalid topic {topic!r}: must be non-empty, with no '*'")
        if level not in _LEVELS:
            raise ValueError(f"invalid level {level!r}: must be one of {', '.join(_LEVELS)}")
        if self._key is not None:
            self._require_publishable(topic)
        key = key if key is not None else self._key
        if key is None:
            raise TypeError("publish() needs key= on an unbound Notifications")
        notification = Notification(
            key,
            topic,
            _freeze(payload or {}),
            summary,
            level,
            self._subject_key(subject),
            record,
            _current_call_id(),
            time.time(),
        )
        message = f"notified {topic}: {summary}" if summary is not None else f"notified {topic}"
        self._log_manager.write(
            key,
            _LOG_LEVELS[level],
            message,
            source="notifications",
            extra={
                "notification": notification.id,
                "topic": topic,
                "notification_level": level,
                "subject": notification.subject,
                "record": record,
                "parent": notification.parent,
            },
        )
        self._dispatch(notification)
        return notification

    def subscribe(
        self, listener: Callable[[Notification], None], topic: str | None = None
    ) -> Callable[[], None]:
        """Call ``listener`` with every notification, or only with those of ``topic``.

        Args:
            listener: Called with each matching ``Notification``.
            topic: ``None`` (the default) delivers every notification. A
                topic ending in ``.*`` matches by prefix — ``"orders.*"``
                matches ``"orders.received"`` and ``"orders.received.late"``,
                not ``"orders"``. Any other topic matches exactly.

        Returns:
            A function that unsubscribes ``listener``. Calling it more than
            once is a no-op.

        Raises:
            ValueError: If ``topic`` is empty, or has a ``*`` other than a
                trailing ``.*``.

        Example:
            >>> unsubscribe = notifications.subscribe(print, topic="orders.*")
            >>> unsubscribe()
        """
        if topic is not None:
            _check_filter(topic)
        return self._add([(listener, topic, self._key, False)])

    def _attach(
        self, key: str, handler: Callable[[Notification], None], topics: tuple[str, ...]
    ) -> Callable[[], None]:
        """Subscribe a ``@Subscriber``'s handler to each of ``topics``, as ``key``.

        Used by the ``Context`` while the subscriber runs; not meant for user
        code. A notification matching several of ``topics`` is delivered
        once. An exception from ``handler`` is not logged here: ``handler``
        is an instrumented call, whose ``failed`` record already says so.

        Returns:
            A function that detaches ``handler``.
        """
        return self._add([(handler, topics, key, True)])

    def _add(self, entries: list[_Entry]) -> Callable[[], None]:
        """Add listener ``entries``; return a function that removes them, idempotently."""
        with self._lock:
            self._listeners.extend(entries)

        def unsubscribe() -> None:
            """Stop delivering notifications to these listeners."""
            with self._lock:
                for entry in entries:
                    if entry in self._listeners:
                        self._listeners.remove(entry)

        return unsubscribe

    def _require_publishable(self, topic: str) -> None:
        """Raise unless this injected view may publish ``topic`` now — see ``publish()``."""
        if self._publishes is None:
            raise TypeError(
                f"{self._key} publishes {topic!r} but is not a @Publisher — declare it with "
                f"@Publisher({topic!r}) on top of its execution type (or @Function)"
            )
        if not any(_matches(declared, topic) for declared in self._publishes):
            declared = ", ".join(repr(t) for t in self._publishes)
            raise ValueError(
                f"{self._key} publishes {topic!r}, which its @Publisher doesn't declare "
                f"(it declares {declared}) — add it to @Publisher(...)"
            )
        if _current_call_id() is None:
            raise RuntimeError(
                f"{self._key} publishes {topic!r} outside any protocol call, so the "
                "notification could not be traced — publish from execute(), run(), "
                "on_start(), on_notification(), a @Function call, ..., not from __init__ "
                "or a thread of your own"
            )

    def _subject_key(self, subject: str | type | Callable[..., object] | None) -> str | None:
        """Return the key ``subject`` names, resolving a class or function through ``key_of``."""
        if subject is None or isinstance(subject, str):
            return subject
        try:
            if self._key_of is None:
                raise KeyError(subject)
            return self._key_of(subject)
        except KeyError:
            raise KeyError(
                f"cannot resolve subject {subject!r} to a key: it is not registered, or the "
                "Context is not open yet — pass its key as a string instead"
            ) from None

    def _dispatch(self, notification: Notification) -> None:
        """Call every listener whose topic filter matches, isolating their failures.

        Listeners run with no current call, so a call one of them makes is a
        top-level call rather than a child of the publisher's — linked to
        the notification instead, through its ``cause``. An exception from a
        listener is logged on the subscriber's key — the publisher's, for a
        listener subscribed through the unbound hub — and never reaches the
        publisher.
        """
        with self._lock:
            listeners = [
                (listener, subscriber, declared)
                for listener, topic, subscriber, declared in self._listeners
                if _matches(topic, notification.topic)
            ]
        if not listeners:
            return
        with _no_current_call(cause=notification.id):
            for listener, subscriber, declared in listeners:
                try:
                    listener(notification)
                except Exception as exc:
                    if declared:
                        continue  # its failed record already says so
                    self._log_manager.write(
                        subscriber or notification.key,
                        "WARNING",
                        f"listener of {notification.topic} raised {exc!r}",
                    )


def _freeze(value: Any) -> Any:
    """Return ``value`` with every container rebuilt read-only, recursively.

    A mapping becomes a ``MappingProxyType`` over a new ``dict``, a list or
    tuple a tuple, a set a ``frozenset``. Every container is rebuilt, so the
    result shares none with ``value``. Anything else is returned as is,
    never copied — it may not be copyable.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(v) for v in value)
    return value


def _matches(pattern: str | tuple[str, ...] | None, topic: str) -> bool:
    """Return whether a subscription's topic filter ``pattern`` matches ``topic``.

    ``pattern`` is one filter, several (any of them matching), or ``None``
    for every topic.
    """
    if pattern is None:
        return True
    if isinstance(pattern, tuple):
        return any(_matches(p, topic) for p in pattern)
    if pattern.endswith(".*"):
        return topic.startswith(pattern[:-1])
    return pattern == topic


def _check_filter(topic: object) -> str:
    """Return ``topic`` if it is a valid topic filter: exact, or ending in ``.*``.

    Raises:
        ValueError: If ``topic`` is not a string, is empty, or has a ``*``
            other than a trailing ``.*``.
    """
    stem = topic.removesuffix(".*") if isinstance(topic, str) else None
    if not stem or "*" in stem:
        raise ValueError(f"invalid topic filter {topic!r}")
    return topic


def _registered_as(target: object) -> type | None:
    """Return the execution type (or ``Function``) ``target`` is registered under, if any."""
    for namespace in (*ExecutionType.__subclasses__(), Function):
        if any(target is member for member in namespace._namespace.values()):
            return namespace
    return None


@dataclass(frozen=True)
class _Subscription:
    """What a ``@Subscriber`` declares, stored on its class."""

    topics: tuple[str, ...]
    deliver: Delivery


@runtime_checkable
class SubscriberProtocol(Protocol):
    """Expected interface for classes declared with ``@Subscriber``.

    The ``Context`` calls ``on_notification()`` with every notification
    matching the class's topics, while the component is started. Each call
    is a protocol call, reported to ``Events`` as ``SubscriberProtocol`` /
    ``"on_notification"`` and traced back to the notification by its
    ``cause``.
    """

    def on_notification(self, notification: Notification) -> None:
        """React to one notification of a declared topic."""
        ...


def Subscriber(*topics: str, deliver: Delivery = "sync") -> Callable[[type], type]:
    """Declare that a component reacts to notifications of ``topics``.

    Goes on top of the class's execution type, like a layer. The ``Context``
    subscribes the class's ``on_notification()`` (see ``SubscriberProtocol``)
    right after the component starts — after its ``on_start()``, or its
    ``setup()`` for a ``Service`` — and unsubscribes it right before it
    stops, so a component never receives a notification it isn't running
    for. Each delivery is an instrumented protocol call: it emits Events,
    writes call records, and records the notification as its ``cause``. A
    failure is logged as that call's ``failed`` record and never reaches the
    publisher.

    Keep one reaction per component; put what reactions share in a plain
    component they both depend on.

    Args:
        *topics: One or more topic filters: an exact topic, or ``"x.*"`` for
            every topic under ``x``. A notification matching several is
            delivered once.
        deliver: ``"sync"`` (the default) runs ``on_notification()`` in the
            publisher's thread, before ``publish()`` returns.
            ``"background"`` queues the delivery for a worker thread of the
            component's own — for a slow reaction, such as an agent calling
            a model.

    Raises:
        TypeError: If the decorated class isn't registered under an
            execution type yet, or has no ``on_notification()``.
        ValueError: If no topic is given, a topic filter is invalid, or
            ``deliver`` is unknown.

    Example:
        >>> @Subscriber("messages.received", deliver="background")
        ... @Component
        ... class Drafting:
        ...     def __init__(self, desk: OrderDesk) -> None:
        ...         self.desk = desk
        ...
        ...     def on_notification(self, notification: Notification) -> None:
        ...         self.desk.draft_change(notification.record)
    """
    if not topics:
        raise ValueError("@Subscriber needs at least one topic")
    checked = tuple(_check_filter(topic) for topic in topics)
    if deliver not in _DELIVERIES:
        raise ValueError(
            f"invalid deliver {deliver!r}: must be one of {', '.join(map(repr, _DELIVERIES))}"
        )

    def decorate(cls: type) -> type:
        """Mark ``cls`` as a subscriber of ``topics``."""
        namespace = _registered_as(cls)
        if not isinstance(cls, type) or namespace is None or namespace is Function:
            raise TypeError(
                f"@Subscriber can only declare a class already registered under an "
                f"execution type, got {describe(cls)} — put @Component, @Service, "
                f"@Agent, ... under it, with @Subscriber on top"
            )
        if not callable(getattr(cls, "on_notification", None)):
            raise TypeError(
                f"{cls.__name__} is a @Subscriber, so it must define "
                "on_notification(self, notification)"
            )
        setattr(cls, _SUBSCRIBER, _Subscription(checked, deliver))
        return cls

    return decorate


def Publisher[T](*topics: str) -> Callable[[T], T]:
    """Declare the topics a component (or ``@Function``) publishes.

    Goes on top of the class's execution type, or on top of ``@Function``,
    like a layer. Only a ``@Publisher`` may publish through its injected
    ``notifications``, and only the topics it declares — see
    ``Notifications.publish()``. ``Context.publishers()`` lists every
    declaration, so tooling can draw who publishes what before anything
    has been published.

    There is no protocol method: publishing is started by the component's
    own code, at moments only it knows, so the framework has nothing to
    call.

    Args:
        *topics: One or more topic filters: an exact topic, or ``"x.*"`` to
            allow every topic under ``x``.

    Raises:
        TypeError: If the decorated class or function isn't registered yet.
        ValueError: If no topic is given, or a topic filter is invalid.

    Example:
        >>> @Publisher("orders.received")
        ... @Task
        ... class TakeOrder:
        ...     def __init__(self, notifications: Notifications) -> None:
        ...         self.notifications = notifications
        ...
        ...     def execute(self) -> None:
        ...         self.notifications.publish("orders.received", {"id": 7})
    """
    if not topics:
        raise ValueError("@Publisher needs at least one topic")
    checked = tuple(_check_filter(topic) for topic in topics)

    def decorate(target: T) -> T:
        """Mark ``target`` as a publisher of ``topics``."""
        if _registered_as(target) is None:
            raise TypeError(
                f"@Publisher can only declare a registered class or function, got "
                f"{describe(target)} — put an execution type (@Component, @Task, ...) or "
                "@Function under it, with @Publisher on top"
            )
        setattr(target, _PUBLISHER, checked)
        return target

    return decorate


def subscription_of(target: object) -> _Subscription | None:
    """Return what ``target``'s ``@Subscriber`` declares, or ``None``."""
    return getattr(target, _SUBSCRIBER, None) if isinstance(target, type) else None


def publications_of(target: object) -> tuple[str, ...] | None:
    """Return the topic filters ``target``'s ``@Publisher`` declares, or ``None``."""
    return getattr(target, _PUBLISHER, None)
