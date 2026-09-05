from app.analytics import UsageTracker
from app.storage import Warehouse

from opendataframework import Analytics, Storage

# Storage/Analytics are global Namespace registries populated at import time
# by app/storage.py and app/analytics.py's decorators — no Project/Context
# involved. See tests/examples/entity_repository/test_books.py for the
# broader no-Context pattern used across these example tests.


def test_component_registered_under_its_layer():
    assert Storage.get("warehouse") is Warehouse
    assert Analytics.get("usage-tracker") is UsageTracker


def test_layer_items_include_registered_components():
    assert dict(Storage.items())["warehouse"] is Warehouse
    assert dict(Analytics.items())["usage-tracker"] is UsageTracker


def test_usage_tracker_records_into_warehouse_across_layers():
    warehouse = Warehouse()
    tracker = UsageTracker(warehouse)

    tracker.record("signup")

    assert warehouse.items == ["signup"]
    assert tracker.summary() == {"events": 1, "warehouse_items": 1}
