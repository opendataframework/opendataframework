from collections.abc import Callable
from typing import Annotated

import pytest

from opendataframework.component import Component
from opendataframework.context import Context
from opendataframework.events import Event, build_trace
from opendataframework.function import Function, FunctionProtocol
from opendataframework.layer import Messaging
from opendataframework.namespace import Namespace
from opendataframework.notifications import (
    Notification,
    Notifications,
    Publisher,
    Subscriber,
    SubscriberProtocol,
)
from opendataframework.service import Service
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

    @Publisher(topic)
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


def test_payload_is_read_only_all_the_way_down():
    ctx = Context(namespaces={make_ns()})
    items = [{"sku": "baguette", "tags": {"fresh"}}]
    payload = {"order": {"items": items}, "ids": (1, [2, 3])}
    notification = ctx.notifications.publish("orders.received", payload, key="scope.x")
    frozen = notification.payload
    assert frozen["order"]["items"] == ({"sku": "baguette", "tags": frozenset({"fresh"})},)
    assert frozen["ids"] == (1, (2, 3))
    with pytest.raises(TypeError):
        frozen["order"]["items"][0]["sku"] = "croissant"  # type: ignore[index]
    with pytest.raises(AttributeError):
        frozen["order"]["items"].append({})  # type: ignore[attr-defined]
    items[0]["sku"] = "croissant"
    items.append({})
    assert frozen["order"]["items"] == ({"sku": "baguette", "tags": frozenset({"fresh"})},)


def test_payload_leaves_are_not_copied():
    class Handle: ...

    handle = Handle()
    ctx = Context(namespaces={make_ns()})
    notification = ctx.notifications.publish("files.opened", {"h": [handle]}, key="scope.x")
    assert notification.payload["h"][0] is handle


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
    assert "notified orders.received: Le Petit: 2 baguettes" in messages


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

    @Publisher("orders.priced")
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


# --- ids and causes ----------------------------------------------------------


def reacting(NS):
    """Register a line cook that reacts to ``orders.*`` by cooking, which calls ``plate``."""

    @NS
    @Function
    def plate(order_id: int) -> None: ...

    @NS
    @Function
    def cook_dish(order_id: int, plate: Annotated[Callable[..., None], plate]) -> None:
        plate(order_id=order_id)

    @NS
    @Component
    class LineCook:
        def __init__(
            self, notifications: Notifications, cook: Annotated[Callable[..., None], cook_dish]
        ) -> None:
            notifications.subscribe(lambda n: cook(order_id=n.payload["id"]), "orders.*")


def test_notification_ids_are_unique_and_logged(tmp_path):
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path)
    first = ctx.notifications.publish("orders.received", key="scope.x")
    second = ctx.notifications.publish("orders.received", key="scope.x")
    assert first.id != second.id
    assert len(first.id) == 32
    logged = [r["notification"] for r in ctx.tail_logs("scope.x")]
    assert logged == [first.id, second.id]


def test_a_call_made_by_a_listener_records_the_notification_as_its_cause():
    NS = make_ns()
    reacting(NS)
    publishing_task(NS)
    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")

    (notification,) = received
    cook = [e for e in events if e.key == "scope.cook-dish"]
    assert {(e.cause, e.parent) for e in cook} == {(notification.id, None)}
    plate = [e for e in events if e.key == "scope.plate"]
    assert {e.cause for e in plate} == {None}
    assert {e.parent for e in plate} == {cook[0].call_id}
    take = [e for e in events if e.key == "scope.take-order"]
    assert {e.cause for e in take} == {None}


def test_a_call_made_after_the_listener_returns_has_no_cause():
    NS = make_ns()

    @NS
    @Function
    def later() -> None: ...

    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    with ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
        ctx.call("scope.later")
    assert {e.cause for e in events if e.key == "scope.later"} == {None}


def test_an_events_listener_never_inherits_a_cause():
    NS = make_ns()

    @NS
    @Function
    def audit() -> None: ...

    reacting(NS)
    publishing_task(NS)
    ctx = Context(namespaces={NS})
    events: list[Event] = []

    def on_event(event: Event) -> None:
        if event.key == "scope.cook-dish" and event.state == "started":
            ctx.call("scope.audit")

    ctx.events.subscribe(on_event)
    ctx.events.subscribe(events.append)
    with ctx:
        ctx.execute("scope.take-order")
    audited = [e for e in events if e.key == "scope.audit"]
    assert audited and {(e.cause, e.parent) for e in audited} == {(None, None)}


def test_cause_is_written_to_the_event_records(tmp_path):
    NS = make_ns()
    reacting(NS)
    publishing_task(NS)
    ctx = Context(namespaces={NS}, log_dir=tmp_path)
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")
        cook = [r for r in ctx.tail_logs("scope.cook-dish") if r.get("source") == "events"]
        plate = [r for r in ctx.tail_logs("scope.plate") if r.get("source") == "events"]
    assert {r["cause"] for r in cook} == {received[0].id}
    assert all("cause" not in r for r in plate)


def test_trace_follows_a_notification_into_what_it_triggered(tmp_path):
    NS = make_ns()
    reacting(NS)
    publishing_task(NS)
    ctx = Context(namespaces={NS}, log_dir=tmp_path)
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    received = collect(ctx)
    with ctx:
        ctx.execute("scope.take-order")
        take = next(e for e in events if e.key == "scope.take-order")
        trace = ctx.trace(take.call_id)

    (notification,) = trace["notifications"]
    assert notification["id"] == received[0].id
    (cook,) = notification["triggered"]
    assert (cook["key"], cook["cause"], cook["parent"]) == ("scope.cook-dish", received[0].id, None)
    assert [child["key"] for child in cook["children"]] == ["scope.plate"]
    assert trace["children"] == []

    # the same tree from live events plus the notification's record
    (record,) = (r for r in ctx.tail_logs("scope.take-order") if r.get("source") == "notifications")
    live = build_trace([*events, record], take.call_id)
    assert live["notifications"][0]["triggered"][0]["call"] == cook["call"]
    assert live["notifications"][0]["triggered"][0]["children"][0]["key"] == "scope.plate"


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


# --- log records -------------------------------------------------------------


def published(ctx: Context, key: str) -> list[dict]:
    """Return the notification records in ``key``'s log."""
    return [r for r in ctx.tail_logs(key) if r.get("source") == "notifications"]


@pytest.mark.parametrize(
    ("level", "log_level"),
    [("info", "INFO"), ("success", "INFO"), ("warning", "WARNING"), ("error", "ERROR")],
)
def test_publish_is_logged_at_the_matching_level(tmp_path, level, log_level):
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path)
    ctx.notifications.publish("orders.received", {"id": 7}, key="scope.x", level=level)
    (record,) = published(ctx, "scope.x")
    assert record["level"] == log_level
    assert record["notification_level"] == level
    assert record["message"] == "notified orders.received"
    assert record["topic"] == "orders.received"
    assert record["parent"] is None
    assert "payload" not in record


def test_notifications_level_filters_publish_records(tmp_path):
    config = {"notifications": "ERROR"}
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path, log_config=config)
    ctx.notifications.publish("orders.received", key="scope.x")
    ctx.notifications.publish("orders.lost", key="scope.x", level="error")
    assert [r["topic"] for r in published(ctx, "scope.x")] == ["orders.lost"]


def test_publish_record_carries_subject_record_and_the_publishing_call(tmp_path):
    NS = make_ns()
    publishing_task(NS, subject="repository.orders", record=7)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.take-order")
        started = ctx.tail_logs("scope.take-order")[1]
        (record,) = published(ctx, "scope.take-order")

    assert started["state"] == "started"
    assert record["parent"] == started["call"]
    assert (record["subject"], record["record"]) == ("repository.orders", 7)


# --- @Subscriber ---------------------------------------------------------------


def subscriber(NS, *topics, received=None, fail=False, name="Drafting"):
    """Register a @Subscriber component that appends what it receives to ``received``."""
    received = received if received is not None else []

    def on_notification(self, notification: Notification) -> None:
        received.append(notification)
        if fail:
            raise RuntimeError("draft failed")

    cls = type(name, (), {"on_notification": on_notification})
    return Subscriber(*topics)(NS(Component(cls))), received


def test_subscriber_receives_matching_topics_only():
    NS = make_ns()
    _, received = subscriber(NS, "orders.received", "messages.*")
    ctx = Context(namespaces={NS})
    with ctx:
        for topic in ("orders.received", "orders.large", "messages.in.email", "messages"):
            ctx.notifications.publish(topic, key="scope.x")
    assert [n.topic for n in received] == ["orders.received", "messages.in.email"]


def test_a_notification_matching_several_topics_is_delivered_once():
    NS = make_ns()
    _, received = subscriber(NS, "orders.received", "orders.*")
    with Context(namespaces={NS}) as ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
    assert len(received) == 1


def test_subscriber_is_subscribed_only_while_its_component_runs():
    NS = make_ns()
    _, received = subscriber(NS, "orders.received")
    ctx = Context(namespaces={NS})
    ctx.notifications.publish("orders.received", key="scope.x")
    ctx.open()
    ctx.notifications.publish("orders.received", key="scope.x")
    ctx.close()
    ctx.notifications.publish("orders.received", key="scope.x")
    assert len(received) == 1


def test_subscriber_starts_receiving_after_its_own_on_start():
    NS = make_ns()
    seen: list[str] = []

    @Publisher("orders.received")
    @NS
    @Component
    class Till:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def on_start(self) -> None:
            self.notifications.publish("orders.received")

    @Subscriber("orders.received")
    @NS
    @Component
    class Oven:
        def __init__(self, till: Till) -> None: ...

        def on_start(self) -> None:
            seen.append("started")

        def on_notification(self, notification: Notification) -> None:
            seen.append(notification.topic)

        def on_stop(self) -> None:
            seen.append("stopped")

    with Context(namespaces={NS}) as ctx:
        # The till published during its own on_start(), before the oven
        # (which depends on it) had started, so the oven missed it.
        assert seen == ["started"]
        ctx.notifications.publish("orders.received", key="scope.x")
    ctx.notifications.publish("orders.received", key="scope.x")
    assert seen == ["started", "orders.received", "stopped"]


def test_a_stopped_service_receives_nothing_until_it_starts_again():
    NS = make_ns()
    received: list[Notification] = []

    @Subscriber("orders.received")
    @NS
    @Service
    class Mailbox:
        def setup(self) -> None: ...

        def run(self) -> None: ...

        def stop(self) -> None: ...

        def on_notification(self, notification: Notification) -> None:
            received.append(notification)

    with Context(namespaces={NS}) as ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
        ctx.stop("scope.mailbox")
        ctx.notifications.publish("orders.received", key="scope.x")
        ctx.start("scope.mailbox")
        ctx.notifications.publish("orders.received", key="scope.x")
    assert len(received) == 2


def test_each_delivery_is_an_instrumented_call_caused_by_the_notification():
    NS = make_ns()
    subscriber(NS, "orders.received")
    ctx = Context(namespaces={NS})
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    with ctx:
        notification = ctx.notifications.publish("orders.received", key="scope.x")
    calls = [e for e in events if e.key == "scope.drafting"]
    assert [e.state for e in calls] == ["started", "completed"]
    assert {(e.protocol, e.method) for e in calls} == {(SubscriberProtocol, "on_notification")}
    assert {(e.cause, e.parent) for e in calls} == {(notification.id, None)}


def test_a_failing_subscriber_logs_one_failed_call_and_the_publisher_continues(tmp_path):
    NS = make_ns()
    subscriber(NS, "orders.received", fail=True)
    _, others = subscriber(NS, "orders.received", name="Counter")
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
        logged = ctx.tail_logs("scope.drafting")
    assert len(others) == 1
    failed = [r for r in logged if r.get("state") == "failed"]
    assert len(failed) == 1 and failed[0]["error"] == "RuntimeError('draft failed')"
    assert not any("listener of" in r["message"] for r in logged)


def test_subscribers_lists_every_declared_subscriber():
    NS = make_ns()
    subscriber(NS, "orders.received", "messages.*")

    @Subscriber("invoices.*", deliver="background")
    @NS
    @Component
    class Filing:
        def on_notification(self, notification: Notification) -> None: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.subscribers() == [
            {
                "key": "scope.drafting",
                "topics": ["orders.received", "messages.*"],
                "deliver": "sync",
            },
            {"key": "scope.filing", "topics": ["invoices.*"], "deliver": "background"},
        ]


def test_subscriber_works_under_a_layer():
    NS = make_ns()
    received: list[Notification] = []

    @Messaging
    @Subscriber("orders.received")
    @NS
    @Component
    class Bell:
        def on_notification(self, notification: Notification) -> None:
            received.append(notification)

    with Context(namespaces={NS}) as ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
    assert len(received) == 1


@pytest.mark.parametrize("topics", [(), ("",), ("orders*",), ("*.received",)])
def test_subscriber_needs_valid_topics(topics):
    with pytest.raises(ValueError):
        Subscriber(*topics)


def test_subscriber_needs_a_known_delivery():
    with pytest.raises(ValueError, match="invalid deliver"):
        Subscriber("orders.received", deliver="later")  # type: ignore[arg-type]


def test_subscriber_needs_a_registered_class_with_on_notification():
    NS = make_ns()

    class Bare:
        def on_notification(self, notification: Notification) -> None: ...

    with pytest.raises(TypeError, match="execution type"):
        Subscriber("orders.received")(Bare)

    @NS
    @Function
    def react(notification: Notification) -> None: ...

    with pytest.raises(TypeError, match="execution type"):
        Subscriber("orders.received")(react)  # type: ignore[arg-type]

    @NS
    @Component
    class Deaf: ...

    with pytest.raises(TypeError, match="on_notification"):
        Subscriber("orders.received")(Deaf)


def test_async_on_notification_raises_at_open():
    NS = make_ns()

    @Subscriber("orders.received")
    @NS
    @Component
    class Slow:
        async def on_notification(self, notification: Notification) -> None: ...

    with pytest.raises(TypeError, match=r"Slow.on_notification\(\) is async"):
        Context(namespaces={NS}).open()


def test_plain_subscribe_is_unaffected_by_subscribers():
    NS = make_ns()
    _, declared = subscriber(NS, "orders.received")
    ctx = Context(namespaces={NS})
    plain = collect(ctx, "orders.received")
    with ctx:
        ctx.notifications.publish("orders.received", key="scope.x")
    assert len(plain) == len(declared) == 1


# --- @Publisher ----------------------------------------------------------------


def test_publishing_needs_a_publisher_declaration():
    NS = make_ns()

    @NS
    @Task
    class Shout:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def execute(self) -> None:
            self.notifications.publish("orders.received")

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError, match=r"not a @Publisher"):
            ctx.execute("scope.shout")


def test_publishing_an_undeclared_topic_raises_and_wildcards_allow_a_prefix():
    NS = make_ns()

    @Publisher("orders.*", "invoices.filed")
    @NS
    @Task
    class Till:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications
            self.topic = "orders.received"

        def execute(self) -> Notification:
            return self.notifications.publish(self.topic)

    with Context(namespaces={NS}) as ctx:
        till = ctx.get(Till)
        for topic in ("orders.received", "orders.received.late", "invoices.filed"):
            till.topic = topic
            assert ctx.execute("scope.till").topic == topic
        for topic in ("orders", "invoices.paid"):
            till.topic = topic
            with pytest.raises(ValueError, match="doesn't declare"):
                ctx.execute("scope.till")


def test_publishing_outside_a_protocol_call_raises():
    NS = make_ns()

    @Publisher("orders.received")
    @NS
    @Component
    class Till:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(RuntimeError, match="outside any protocol call"):
            ctx.get(Till).notifications.publish("orders.received")


def test_publishing_in_init_raises():
    NS = make_ns()

    @Publisher("orders.received")
    @NS
    @Component
    class Eager:
        def __init__(self, notifications: Notifications) -> None:
            notifications.publish("orders.received")

    with pytest.raises(RuntimeError, match="outside any protocol call"):
        Context(namespaces={NS}).open()


def test_a_subscriber_may_publish_what_it_declares():
    NS = make_ns()

    @Publisher("drafts.created")
    @Subscriber("messages.received")
    @NS
    @Component
    class Drafting:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def on_notification(self, notification: Notification) -> None:
            self.notifications.publish("drafts.created")

    ctx = Context(namespaces={NS})
    drafts = collect(ctx, "drafts.created")
    events: list[Event] = []
    ctx.events.subscribe(events.append)
    with ctx:
        ctx.notifications.publish("messages.received", key="scope.inbox")
    (draft,) = drafts
    reaction = next(e for e in events if e.key == "scope.drafting")
    assert draft.parent == reaction.call_id


def test_the_unbound_hub_is_unrestricted():
    ctx = Context(namespaces={make_ns()})
    assert ctx.notifications.publish("anything.goes", key="scope.x").topic == "anything.goes"


def test_publishers_lists_classes_and_functions():
    NS = make_ns()
    publishing_task(NS)

    @Publisher("orders.priced")
    @NS
    @Function
    def quote_price(notifications: Notifications) -> None:
        notifications.publish("orders.priced")

    with Context(namespaces={NS}) as ctx:
        assert ctx.publishers() == [
            {"key": "scope.quote-price", "topics": ["orders.priced"]},
            {"key": "scope.take-order", "topics": ["orders.received"]},
        ]
        assert ctx.call("scope.quote-price") is None


def test_publisher_needs_a_registered_target_and_valid_topics():
    class Bare: ...

    with pytest.raises(TypeError, match="registered"):
        Publisher("orders.received")(Bare)
    with pytest.raises(ValueError):
        Publisher()
    with pytest.raises(ValueError):
        Publisher("orders*")
