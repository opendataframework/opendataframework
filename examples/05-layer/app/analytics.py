from app.storage import Warehouse
from opendataframework import Analytics, Component


@Analytics
@Component
class UsageTracker:
    """Cross-layer dependency: Layer and execution type are independent —
    an Analytics component can depend on a Storage component like any other."""

    def __init__(self, warehouse: Warehouse) -> None:
        self.warehouse = warehouse
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)
        self.warehouse.save(event)

    def summary(self) -> dict[str, int]:
        return {"events": len(self.events), "warehouse_items": len(self.warehouse.items)}
