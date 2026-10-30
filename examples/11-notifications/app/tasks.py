from app.components import Inbox
from app.entities import Order
from app.repositories import Orders
from opendataframework import Notifications, Task


@Task
class TakeOrders:
    def __init__(self, inbox: Inbox, orders: Orders, notifications: Notifications) -> None:
        self.inbox = inbox
        self.orders = orders
        # Bound to this task's key, so publish() needs no key.
        self.notifications = notifications

    def execute(self) -> int:
        taken = 0
        while self.inbox.pending:
            customer, item, quantity = self.inbox.pending.pop(0)
            order = self.orders.save(Order(None, customer, item, quantity))
            # The task doesn't know who listens: the kitchen, a counter, a UI.
            self.notifications.publish(
                "orders.received",
                {"customer": customer, "item": item, "quantity": quantity},
                summary=f"{customer}: {quantity} x {item}",
                subject=Orders,
                record=order.id,
            )
            if quantity >= 10:
                self.notifications.publish(
                    "orders.large",
                    {"quantity": quantity},
                    summary=f"Large order from {customer}: check flour stock",
                    level="warning",
                    subject=Orders,
                    record=order.id,
                )
            taken += 1
        return taken
