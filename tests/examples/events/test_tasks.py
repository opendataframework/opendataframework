import pytest
from app.components import Orders
from app.functions import price
from app.tasks import PriceOrders, ShipOrders

# PriceOrders takes any callable, so a test hands it a stand-in for price —
# no Project/Context needed, same as the function tests next to this file.


def test_price_sums_an_orders_items():
    orders = Orders()
    orders.on_start()

    assert price(orders, 1) == 12.5


def test_price_orders_prices_every_order_through_the_injected_function():
    orders = Orders()
    orders.on_start()
    asked: list[int] = []

    def price_of(order_id: int) -> float:
        asked.append(order_id)
        return 1.0

    assert PriceOrders(orders, price_of).execute() == 3.0
    assert asked == [1, 2, 3]


def test_ship_orders_fails():
    with pytest.raises(ValueError, match="courier unavailable"):
        ShipOrders().execute()
