from collections.abc import Callable
from typing import Annotated

from app.components import Orders
from app.functions import price
from opendataframework import Task


@Task
class PriceOrders:
    def __init__(self, orders: Orders, price_of: Annotated[Callable[..., float], price]) -> None:
        self.orders = orders
        self.price_of = price_of

    def execute(self) -> float:
        # Each call goes through the Context, so it is reported as a
        # FunctionProtocol call whose parent is this task's call.
        return sum(self.price_of(order_id=order_id) for order_id in self.orders.items)


@Task
class ShipOrders:
    def execute(self) -> None:
        raise ValueError("courier unavailable")
