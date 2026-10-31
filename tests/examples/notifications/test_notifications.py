from app.components import Inbox
from app.listeners import Kitchen, OrderCounter
from app.repositories import Orders
from app.tasks import TakeOrders

from opendataframework import Notifications

# Deliberately drives a bare Notifications hub directly rather than going
# through Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): registration is global
# for the whole pytest process. bound_to() is what the Context injects.


def take_orders(hub: Notifications) -> tuple[TakeOrders, Orders]:
    inbox = Inbox()
    inbox.on_start()
    orders = Orders()
    task = TakeOrders(inbox, orders, hub.bound_to("task.take-orders"))
    return task, orders


def test_take_orders_publishes_received_and_large():
    hub = Notifications(key_of=lambda obj: "repository.orders")
    received = []
    hub.subscribe(received.append)
    task, _ = take_orders(hub)

    assert task.execute() == 2
    assert [(n.key, n.topic, n.level, n.record) for n in received] == [
        ("task.take-orders", "orders.received", "info", 1),
        ("task.take-orders", "orders.received", "info", 2),
        ("task.take-orders", "orders.large", "warning", 2),
    ]
    assert received[0].summary == "Le Petit: 2 x baguette"
    assert received[0].subject == "repository.orders"


def test_kitchen_schedules_a_bake_per_received_order():
    hub = Notifications(key_of=lambda obj: "repository.orders")
    task, orders = take_orders(hub)
    kitchen = Kitchen(
        hub.bound_to("component.kitchen"),
        lambda order_id: f"bake {orders.get(order_id).item}",
    )

    task.execute()

    assert [bake for _, bake in kitchen.bakes] == ["bake baguette", "bake sourdough"]


def test_order_counter_counts_by_prefix_and_stops_after_on_stop():
    hub = Notifications(key_of=lambda obj: "repository.orders")
    counter = OrderCounter(hub.bound_to("component.order-counter"))
    task, _ = take_orders(hub)

    task.execute()
    counter.on_stop()
    hub.publish("orders.received", key="task.take-orders")

    assert dict(counter.counts) == {"orders.received": 2, "orders.large": 1}
