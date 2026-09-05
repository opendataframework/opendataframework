"""Logger + View: a Repository that logs its own operations and declares
how its records should be displayed and replayed over time.

Run from this directory: `python main.py`.
"""

from app.entities import Reading
from app.repositories import Readings

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

readings = project.context.get(Readings)

readings.save(
    Reading(
        id=None,
        sensor_id="buoy-1",
        lat=37.77,
        lon=-122.42,
        value=14.2,
        recorded_at="2026-08-13T08:00:00",
    )
)
readings.save(
    Reading(
        id=None,
        sensor_id="buoy-1",
        lat=37.78,
        lon=-122.41,
        value=14.6,
        recorded_at="2026-08-13T09:00:00",
    )
)

print("All readings:")
for reading in readings.all():
    print(f"  {reading}")

print(f"\ndata_view():    {readings.data_view()}")
print(f"replay_field():  {readings.replay_field()!r}")

print("\nRecent log entries for Readings (see logs/readings.log):")
for entry in project.context.tail_logs("Readings"):
    print(f"  {entry['ts']} {entry['level']:<8} {entry['message']}")

project.stop()
