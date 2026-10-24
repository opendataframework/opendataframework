from app.components import Orders
from opendataframework import Function


@Function
def price(orders: Orders, order_id: int) -> float:
    return sum(orders.items[order_id])
