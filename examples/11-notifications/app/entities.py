from dataclasses import dataclass

from opendataframework import Entity


@Entity
@dataclass
class Order:
    id: int | None
    customer: str
    item: str
    quantity: int
