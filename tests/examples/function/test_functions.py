from app.components import Inventory
from app.functions import format_report, low_stock, restock

# Deliberately calls the functions directly rather than going through
# Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): registration is global
# for the whole pytest process. It also shows the point of @Function: the
# decorator leaves the function, and tests like these, exactly as they were.


def test_restock_adds_to_existing_quantity():
    inventory = Inventory()

    assert restock(inventory, "apple", 10) == 12
    assert inventory.stock["apple"] == 12


def test_restock_creates_missing_item():
    inventory = Inventory()

    assert restock(inventory, "cherry", 1) == 1


def test_low_stock_uses_default_threshold():
    assert low_stock(Inventory()) == ["apple"]


def test_low_stock_with_explicit_threshold():
    assert low_stock(Inventory(), threshold=15) == ["apple", "banana"]


def test_format_report():
    assert format_report(["apple", "banana"]) == "apple, banana"
    assert format_report([]) == "nothing"
