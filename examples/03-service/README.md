# 03 — Service

A single `Heartbeat` `@Service` that ticks once a second. Deliberately not an
API server — the point is the `Service` *contract* itself
(`setup() → run() → stop()`), not FastAPI or any particular kind of
long-running process.

This isolates the concept covered in [`docs/service.md`](../../docs/service.md):
`run()` blocks by design (it runs for the lifetime of the application), so the
framework spawns it in a background thread automatically — the service author
never manages threading directly. `project.start()` returns as soon as
`setup()` completes, without waiting for `run()` to finish (it never does,
until `stop()` asks it to).

## Structure

```
03-service/
├── config.toml       # heartbeat tick interval
├── main.py           # entry point — starts the project, waits, stops it
└── app/
    ├── __init__.py   # imports services.py so the decorator registers at startup
    └── services.py   # Heartbeat — @Service
```

## Run it

```bash
cd examples/03-service
python main.py
```

Expected output:

```
project.start() ...
Heartbeat.setup    starting up
... start() returned — Heartbeat.run() is now ticking in the background

Heartbeat.run      tick 1
Heartbeat.run      tick 2
Heartbeat.run      tick 3

project.stop() ...
Heartbeat.stop     stopping after 3 ticks
... stop() returned
```

Or drive it from the UI instead, which starts and stops the service
the same way `main.py` does, just interactively:

```bash
odf run
```
