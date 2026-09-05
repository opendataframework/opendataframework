from app.entities import Reading
from app.storages import Store
from opendataframework import LocationView, Logger, Repository


@Repository(Reading)
class Readings:
    def __init__(self, store: Store, logger: Logger) -> None:
        self.store = store
        self.logger = logger

    def all(self) -> list[Reading]:
        self.logger.info("all() called")
        return [Reading(**row) for row in self.store.all()]

    def save(self, reading: Reading) -> None:
        row_id = self.store.insert(
            {
                "sensor_id": reading.sensor_id,
                "lat": reading.lat,
                "lon": reading.lon,
                "value": reading.value,
                "recorded_at": reading.recorded_at,
            }
        )
        reading.id = row_id
        self.logger.info(f"saved reading {row_id} for sensor {reading.sensor_id}")

    def data_view(self) -> LocationView:
        return LocationView(fields=("lat", "lon"))

    def replay_field(self) -> str:
        return "recorded_at"
