"""Service: setup() -> run() -> stop(), run() backgrounded by the framework.

Heartbeat prints a tick every second from a background thread the framework
manages — main.py just starts the project, waits to observe a few ticks,
then stops it. Deliberately not an API server: the Service *contract* is
the point here, not FastAPI. Run from this directory: `python main.py`, or
`odf run` to drive it from the UI instead.
"""

import time

# `import app` runs app/__init__.py, which imports services.py so its
# @Service decorator executes and registers Heartbeat with the Context.
# Unlike 01/02's main.py, nothing below imports from `app` directly, so this
# import is the only thing that makes the registration happen.
import app  # noqa: F401

from opendataframework import Project

project = Project.from_config("config.toml")

print("project.start() ...")
project.start()
print("... start() returned — Heartbeat.run() is now ticking in the background\n")

time.sleep(3.5)

print("\nproject.stop() ...")
project.stop()
print("... stop() returned")
