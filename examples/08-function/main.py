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

# By key — what a caller holding only a <namespace>.<name> key and arguments would do.
low = project.context.call("function.low-stock")
print(f"call('function.low-stock')       -> {low}")

total = project.context.call("function.restock", item="apple", quantity=10)
print(f"call('function.restock', ...)    -> {total}")

# By function — the same thing, typed, for use from Python.
low = project.context.get(low_stock)(threshold=15)
print(f"get(low_stock)(threshold=15)     -> {low}")
print(f"get(format_report)(...)          -> {project.context.get(format_report)(low)}")

# Injected — Reorder declared low_stock in its constructor, under its own name.
print(f"execute('task.reorder')          -> {project.context.execute('task.reorder')}")

# Directly — unchanged: nothing is injected, every argument is passed.
total = restock(Inventory(), "cherry", 1)
print(f"restock(Inventory(), cherry, 1)  -> {total}")

project.stop()
