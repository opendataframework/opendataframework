from dataclasses import dataclass

from opendataframework import Entity


@Entity
@dataclass
class Reading:
    id: int | None
    sensor_id: str
    lat: float
    lon: float
    value: float
    recorded_at: str
