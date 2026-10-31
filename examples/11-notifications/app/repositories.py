import threading

from app.entities import Order
from opendataframework import Repository


@Repository(Order)
class Orders:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[int, Order] = {}

    def save(self, order: Order) -> Order:
        with self._lock:
            order.id = len(self._orders) + 1
            self._orders[order.id] = order
        return order

    def get(self, order_id: int) -> Order:
        with self._lock:
            return self._orders[order_id]
