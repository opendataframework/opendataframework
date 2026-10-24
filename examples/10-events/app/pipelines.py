from app.tasks import PriceOrders, ShipOrders
from opendataframework import Pipeline


@Pipeline
class NightlyOrders:
    def __init__(self, price_orders: PriceOrders, ship_orders: ShipOrders) -> None:
        self.price_orders = price_orders
        self.ship_orders = ship_orders

    def execute(self) -> None:
        self.price_orders.execute()
        self.ship_orders.execute()
