from app.repositories import Orders
from opendataframework import Function


@Function
def schedule_bake(orders: Orders, order_id: int) -> str:
    order = orders.get(order_id)
    return f"bake {order.quantity} x {order.item} for {order.customer}"
