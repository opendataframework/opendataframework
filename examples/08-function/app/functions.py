from app.components import Inventory
from opendataframework import Function


@Function
def restock(inventory: Inventory, item: str, quantity: int) -> int:
    inventory.stock[item] = inventory.stock.get(item, 0) + quantity
    return inventory.stock[item]


@Function
def low_stock(inventory: Inventory, threshold: int = 5) -> list[str]:
    return sorted(item for item, quantity in inventory.stock.items() if quantity < threshold)


@Function
def format_report(items: list[str]) -> str:
    return ", ".join(items) if items else "nothing"
