"""Function: making existing plain functions framework-aware.

restock, low_stock and format_report are ordinary functions with one
decorator added. Called directly they behave exactly as before; called
through the Context, the Inventory @Component they take is injected and
only the remaining arguments are passed. Reorder, a @Task, has low_stock
injected through its constructor and calls it like any other dependency.
Run from this directory: `python main.py`.
"""

from app.components import Inventory
from app.functions import format_report, low_stock, restock

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

# By name — what a caller holding only a name and arguments would do.
low = project.context.call("low-stock")
print(f"call('low-stock')                -> {low}")

total = project.context.call("restock", item="apple", quantity=10)
print(f"call('restock', apple, 10)       -> {total}")

# By function — the same thing, typed, for use from Python.
low = project.context.get(low_stock)(threshold=15)
print(f"get(low_stock)(threshold=15)     -> {low}")
print(f"get(format_report)(...)          -> {project.context.get(format_report)(low)}")

# Injected — Reorder declared low_stock in its constructor, under its own name.
print(f"execute('Reorder')               -> {project.context.execute('Reorder')}")

# Directly — unchanged: nothing is injected, every argument is passed.
total = restock(Inventory(), "cherry", 1)
print(f"restock(Inventory(), cherry, 1)  -> {total}")

project.stop()
