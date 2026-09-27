"""Component + Context: dependency-ordered lifecycle.

Cache depends on Database through its constructor, so the Context resolves
Database first and tears it down last — on_start()/on_stop() print
statements make that order visible. No Service, no UI. Run from this
directory: `python main.py`.

config.toml's `[project] app = "app"` is what a real entrypoint relies on
to import the app package (registering @Database/@Cache via
app/__init__.py) without a hand-written `import app` here — this file
still imports app.components directly below, but only to get a typed
reference to Cache for project.context.get(Cache).
"""

from app.components import Cache

from opendataframework import Project

project = Project.from_config("config.toml")

print("project.start() ...")
project.start()
print("... start() returned\n")

# project.context.get(cls) is the typed way to fetch a resolved instance —
# see docs/context.md.
cache = project.context.get(Cache)

print(f"Cache.get('user:1') -> {cache.get('user:1')}")
print(f"Cache.get('user:1') -> {cache.get('user:1')}  (already cached)\n")

print("project.stop() ...")
project.stop()
print("... stop() returned")
