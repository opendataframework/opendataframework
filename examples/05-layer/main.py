"""Layer: an organisational grouping independent of execution type.

Warehouse is @Storage, UsageTracker is @Analytics and depends on Warehouse
across layers — Layer and execution type are independent concepts. Both are
read back through `project.context.get(cls)`, typed by the class passed in.
Layer membership itself is inspected through `Storage.items()`/`Analytics.items()`
directly, independent of the Context. Run from this directory: `python main.py`.
"""

from app.analytics import UsageTracker
from app.storage import Warehouse

from opendataframework import Analytics, Project, Storage

project = Project.from_config("config.toml")
project.start()

tracker = project.context.get(UsageTracker)
tracker.record("signup")
tracker.record("login")

print(f"tracker summary: {tracker.summary()}")

warehouse = project.context.get(Warehouse)
print(f"\nWarehouse (via Storage layer): {warehouse.items}")

print(f"\nStorage layer members:   {dict(Storage.items())}")
print(f"Analytics layer members: {dict(Analytics.items())}")

project.stop()
