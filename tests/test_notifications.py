from collections.abc import Callable
from typing import Annotated

import pytest

from opendataframework.component import Component
from opendataframework.context import Context
from opendataframework.events import Event
from opendataframework.function import Function, FunctionProtocol
from opendataframework.namespace import Namespace
from opendataframework.notifications import Notification, Notifications
from opendataframework.task import Task, TaskProtocol

# --- helpers -----------------------------------------------------------------


def make_ns():
    """Return a fresh isolated Namespace subclass for each test."""

    class Scope(Namespace): ...

    return Scope


def collect(ctx: Context, topic: str | None = None) -> list[Notification]:
    """Subscribe a list to ``ctx``'s notifications and return it."""
    received: list[Notification] = []
    ctx.notifications.subscribe(received.append, topic)
    return received


def publishing_task(NS, topic="orders.received", **kwargs):
    """Register a task that publishes ``topic`` from ``execute()``."""

    @NS
    @Task
    class TakeOrder:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def execute(self) -> Notification:
            return self.notifications.publish(topic, {"id": 7}, **kwargs)

    return TakeOrder


# --- publishing --------------------------------------------------------------


def test_publish_delivers_every_field_and_the_view_fills_in_the_key():
    NS = make_ns()

    @NS
    @Component
    class OrderBook: ...

    publishing_task(
        NS, summary="Le Petit: 2 baguettes", level="success", subject=OrderBook, record=7
    )
    ctx = Context(namespaces={NS})
    received = collect(ctx)
    with ctx:
        returned = ctx.execute("scope.take-order")

    (notification,) = received
    assert notification is returned
    assert notification.key == "scope.take-order"
    assert notification.topic == "orders.received"
    assert dict(notification.payload) == {"id": 7}
    assert notification.summary == "Le Petit: 2 baguettes"
    assert notification.level == "success"
    assert notification.subject == "scope.order-book"
    assert notification.record == 7
    assert notification.ts > 0


def test_defaults_when_only_a_topic_is_given():
    ctx = Context(namespaces={make_ns()})
    notification = ctx.notifications.publish("orders.received", key="scope.x")
    assert dict(notification.payload) == {}
    assert notification.summary is None
    assert notification.level == "info"
    assert notification.subject is None
    assert notification.record is None
    assert notification.parent is None


def test_payload_is_a_read_only_copy():
    ctx = Context(namespaces={make_ns()})
    payload = {"id": 7}
    notification = ctx.notifications.publish("orders.received", payload, key="scope.x")
    payload["id"] = 8
    assert notification.payload["id"] == 7
    with pytest.raises(TypeError):
        notification.payload["id"] = 9  # type: ignore[index]


def test_unbound_hub_needs_a_key():
    ctx = Context(namespaces={make_ns()})
    with pytest.raises(TypeError, match="key="):
        ctx.notifications.publish("orders.received")


@pytest.mark.parametrize("topic", ["", "orders.*", "*"])
def test_invalid_topic_raises(topic):
    ctx = Context(namespaces={make_ns()})
    with pytest.raises(ValueError, match="invalid topic"):
        ctx.notifications.publish(topic, key="scope.x")


def test_invalid_level_raises():
    ctx = Context(namespaces={make_ns()})
    with pytest.raises(ValueError, match="invalid level"):
        ctx.notifications.publish("orders.received", key="scope.x", level="fatal")  # type: ignore[arg-type]


def test_subject_as_a_string_works_before_open():
    ctx = Context(namespaces={make_ns()})
    notification = ctx.notifications.publish(
        "orders.received", key="scope.x", subject="repository.orders"
    )
    assert notification.subject == "repository.orders"


def test_subject_as_a_class_before_open_raises():
    NS = make_ns()

    @NS
    @Component
    class OrderLedger: ...

    ctx = Context(namespaces={NS})
    with pytest.raises(KeyError, match="cannot resolve subject"):
        ctx.notifications.publish("orders.received", key="scope.x", subject=OrderLedger)


def test_subject_as_a_function_resolves_to_its_key():
    NS = make_ns()

    @NS
    @Function
    def list_price() -> float:
        return 1.0

    with Context(namespaces={NS}) as ctx:
        notification = ctx.notifications.publish("orders.priced", key="scope.x", subject=list_price)
    assert notification.subject == "scope.list-price"


def test_publish_is_logged_on_the_publishers_key(tmp_path):
    NS = make_ns()
    publishing_task(NS, summary="Le Petit: 2 baguettes")
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.take-order")
        messages = [entry["message"] for entry in ctx.tail_logs("scope.take-order")]
    assert any(
        m.startswith("notified orders.received: Le Petit: 2 baguettes [parent=") for m in messages
    )


def test_works_with_file_logging_off():
    NS = make_ns()
    publishing_task(NS, summary="Le Petit: 2 baguettes")
    ctx = Context(namespaces={NS})
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")
    assert len(received) == 1


# --- parent ------------------------------------------------------------------


def test_parent_is_the_protocol_call_in_progress():
    NS = make_ns()
    publishing_task(NS)
    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append, protocol=TaskProtocol)
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")

    started = events[0]
    assert received[0].parent == started.call_id


def test_function_parameter_receives_a_view_bound_to_the_function():
    NS = make_ns()

    @NS
    @Function
    def quote(notifications: Notifications, order_id: int) -> float:
        notifications.publish("orders.priced", {"id": order_id})
        return 1.0

    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append, protocol=FunctionProtocol)
    received = collect(ctx)
    with ctx:
        ctx.call("scope.quote", order_id=7)

    (notification,) = received
    assert notification.key == "scope.quote"
    assert notification.parent == events[0].call_id


# --- subscribing -------------------------------------------------------------


def test_topic_filters():
    ctx = Context(namespaces={make_ns()})
    everything = collect(ctx)
    exact = collect(ctx, "orders.received")
    prefix = collect(ctx, "orders.*")
    for topic in ["orders", "orders.received", "orders.received.late", "invoices.received"]:
        ctx.notifications.publish(topic, key="scope.x")

    assert [n.topic for n in everything] == [
        "orders",
        "orders.received",
        "orders.received.late",
        "invoices.received",
    ]
    assert [n.topic for n in exact] == ["orders.received"]
    assert [n.topic for n in prefix] == ["orders.received", "orders.received.late"]


@pytest.mark.parametrize("topic", ["", ".*", "*", "orders*", "*.received"])
def test_invalid_topic_filter_raises(topic):
    ctx = Context(namespaces={make_ns()})
    with pytest.raises(ValueError, match="invalid topic filter"):
        ctx.notifications.subscribe(print, topic)


def test_unsubscribe_stops_delivery_and_is_idempotent():
    ctx = Context(namespaces={make_ns()})
    received: list[Notification] = []
    unsubscribe = ctx.notifications.subscribe(received.append)
    ctx.notifications.publish("orders.received", key="scope.x")
    unsubscribe()
    unsubscribe()
    ctx.notifications.publish("orders.received", key="scope.x")
    assert len(received) == 1


def test_component_subscribes_through_its_injected_view():
    NS = make_ns()

    @NS
    @Component
    class PrepStation:
        def __init__(self, notifications: Notifications) -> None:
            self.orders: list[Notification] = []
            self._unsubscribe = notifications.subscribe(self.orders.append, "orders.*")

        def on_stop(self) -> None:
            self._unsubscribe()

    publishing_task(NS)
    with Context(namespaces={NS}) as ctx:
        ctx.execute("scope.take-order")
        station = ctx.get(PrepStation)
        assert [n.topic for n in station.orders] == ["orders.received"]
    ctx.notifications.publish("orders.received", key="scope.x")
    assert len(station.orders) == 1


# --- delivery ----------------------------------------------------------------


def test_raising_listener_is_logged_on_the_subscriber_and_others_still_run(tmp_path):
    NS = make_ns()

    @NS
    @Component
    class Broken:
        def __init__(self, notifications: Notifications) -> None:
            notifications.subscribe(self._on)

        def _on(self, notification: Notification) -> None:
            raise RuntimeError("boom")

    publishing_task(NS)
    ctx = Context(namespaces={NS}, log_dir=tmp_path)
    received = collect(ctx)
    with ctx:
        assert ctx.execute("scope.take-order").topic == "orders.received"
        broken_log = [entry["message"] for entry in ctx.tail_logs("scope.broken")]

    assert len(received) == 1
    assert any("listener of orders.received raised RuntimeError('boom')" in m for m in broken_log)


def test_raising_unbound_listener_is_logged_on_the_publisher(tmp_path):
    NS = make_ns()
    publishing_task(NS)
    ctx = Context(namespaces={NS}, log_dir=tmp_path)

    def broken(notification: Notification) -> None:
        raise RuntimeError("boom")

    ctx.notifications.subscribe(broken)
    with ctx:
        ctx.execute("scope.take-order")
        messages = [entry["message"] for entry in ctx.tail_logs("scope.take-order")]
    assert any("raised RuntimeError('boom')" in m for m in messages)


def test_call_made_by_a_listener_is_top_level():
    NS = make_ns()

    @NS
    @Function
    def cook_order(order_id: int) -> None: ...

    @NS
    @Component
    class LineCook:
        def __init__(
            self, notifications: Notifications, cook: Annotated[Callable[..., None], cook_order]
        ) -> None:
            notifications.subscribe(lambda n: cook(order_id=n.payload["id"]), "orders.*")

    publishing_task(NS)
    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")

    cook_started = next(e for e in events if e.key == "scope.cook-order" and e.state == "started")
    assert cook_started.parent is None
    assert received[0].parent is not None


def test_listener_may_publish():
    ctx = Context(namespaces={make_ns()})
    ctx.notifications.subscribe(
        lambda n: ctx.notifications.publish("orders.cooked", key="scope.station"),
        "orders.received",
    )
    received = collect(ctx)
    ctx.notifications.publish("orders.received", key="scope.x")
    assert [n.topic for n in received] == ["orders.cooked", "orders.received"]


# --- isolation ---------------------------------------------------------------


def test_two_contexts_are_isolated():
    a, b = Context(namespaces={make_ns()}), Context(namespaces={make_ns()})
    received_a, received_b = collect(a), collect(b)
    a.notifications.publish("orders.received", key="scope.x")
    assert len(received_a) == 1
    assert received_b == []


def test_events_listeners_receive_no_notifications():
    NS = make_ns()
    publishing_task(NS)
    ctx = Context(namespaces={NS})
    events: list[object] = []
    ctx.events.subscribe(events.append)
    with ctx:
        ctx.execute("scope.take-order")
    assert events and all(isinstance(e, Event) for e in events)


# --- log lines ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "log_level"),
    [("info", "INFO"), ("success", "INFO"), ("warning", "WARNING"), ("error", "ERROR")],
)
def test_publish_is_logged_at_the_matching_level(tmp_path, level, log_level):
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path)
    ctx.notifications.publish("orders.received", key="scope.x", level=level)
    (entry,) = ctx.tail_logs("scope.x")
    assert entry["level"] == log_level
    assert entry["message"] == "notified orders.received [parent=-]"


def test_notifications_level_filters_publish_lines(tmp_path):
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path, log_levels={"notifications": "ERROR"})
    ctx.notifications.publish("orders.received", key="scope.x")
    ctx.notifications.publish("orders.lost", key="scope.x", level="error")
    assert [e["message"] for e in ctx.tail_logs("scope.x")] == ["notified orders.lost [parent=-]"]


def test_publish_line_parent_is_the_publishing_call(tmp_path):
    NS = make_ns()
    publishing_task(NS)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.take-order")
        messages = [e["message"] for e in ctx.tail_logs("scope.take-order")]

    started = next(m for m in messages if m.startswith("execute() started"))
    call = started.split("[call=")[1][:8]
    assert f"notified orders.received [parent={call}]" in messages
