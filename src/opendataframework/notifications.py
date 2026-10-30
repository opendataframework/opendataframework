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
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, get_args

from opendataframework.events import _current_call_id, _no_current_call
from opendataframework.logger import LogManager

Level = Literal["info", "success", "warning", "error"]
_LEVELS: tuple[str, ...] = get_args(Level)


@dataclass(frozen=True)
class Notification:
    """One message a component published.

    Attributes:
        key: The ``<namespace>.<name>`` key of the publishing component, as
            ``Context.key()`` returns it.
        topic: Dotted name of what happened — ``"orders.received"``,
            ``"margins.below-cost"``.
        payload: Data for subscribers, read-only; ``{}`` when none was given.
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
        self._listeners: list[tuple[Callable[[Notification], None], str | None, str | None]] = []
        self._lock = threading.Lock()
        self._key: str | None = None

    def bound_to(self, key: str) -> Notifications:
        """Return a view of this hub that publishes and subscribes as ``key``.

        Used by the framework to inject a ``notifications: Notifications``
        parameter; not meant for user code. The view shares this hub's
        subscribers.
        """
        view = copy.copy(self)  # shallow: shares _listeners and _lock
        view._key = key
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

        Listeners run before this returns, with no current call; an exception
        from one is logged and never raised here. Each publish is also logged
        at ``INFO`` on the publisher's key, as ``notified <topic>: <summary>``.

        Args:
            topic: Dotted name of what happened. Non-empty, with no ``*``.
            payload: Data for subscribers; copied, and delivered read-only.
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
            TypeError: If no ``key`` is given and this view is unbound.
            ValueError: If ``topic`` or ``level`` is invalid.
            KeyError: If ``subject`` is a class or function that was not
                resolved.

        Example:
            >>> notifications.publish("orders.received", {"id": 7}, summary="Le Petit: 2 baguettes")
        """
        key = key if key is not None else self._key
        if key is None:
            raise TypeError("publish() needs key= on an unbound Notifications")
        if not topic or "*" in topic:
            raise ValueError(f"invalid topic {topic!r}: must be non-empty, with no '*'")
        if level not in _LEVELS:
            raise ValueError(f"invalid level {level!r}: must be one of {', '.join(_LEVELS)}")
        notification = Notification(
            key,
            topic,
            MappingProxyType(dict(payload or {})),
            summary,
            level,
            self._subject_key(subject),
            record,
            _current_call_id(),
            time.time(),
        )
        message = f"notified {topic}: {summary}" if summary is not None else f"notified {topic}"
        self._log_manager.write(key, "INFO", message)
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
            stem = topic.removesuffix(".*")
            if not stem or "*" in stem:
                raise ValueError(f"invalid topic filter {topic!r}")
        entry = (listener, topic, self._key)
        with self._lock:
            self._listeners.append(entry)

        def unsubscribe() -> None:
            """Stop delivering notifications to ``listener``."""
            with self._lock:
                if entry in self._listeners:
                    self._listeners.remove(entry)

        return unsubscribe

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
        top-level call rather than a child of the publisher's. An exception
        from a listener is logged on the subscriber's key — the publisher's,
        for a listener subscribed through the unbound hub — and never
        reaches the publisher.
        """
        with self._lock:
            listeners = [
                (listener, subscriber)
                for listener, topic, subscriber in self._listeners
                if _matches(topic, notification.topic)
            ]
        if not listeners:
            return
        with _no_current_call():
            for listener, subscriber in listeners:
                try:
                    listener(notification)
                except Exception as exc:
                    self._log_manager.write(
                        subscriber or notification.key,
                        "WARNING",
                        f"listener of {notification.topic} raised {exc!r}",
                    )


def _matches(pattern: str | None, topic: str) -> bool:
    """Return whether a subscription's topic filter ``pattern`` matches ``topic``."""
    if pattern is None:
        return True
    if pattern.endswith(".*"):
        return topic.startswith(pattern[:-1])
    return pattern == topic
