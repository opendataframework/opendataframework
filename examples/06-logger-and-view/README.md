# 06 — Logger + View

A single `Readings` `@Repository` that uses both cross-cutting, optional
capabilities the earlier examples don't touch: a `logger: Logger`
constructor dependency for per-component logging, and `data_view()` /
`replay_field()` to declare how its records should be displayed and
scrubbed through over time.

This isolates the concepts covered in
[`docs/logger.md`](../../docs/logger.md) and
[`docs/view.md`](../../docs/view.md): `Logger` is injected like any other
dependency but resolves to an instance bound to the requesting class's own
name, and `data_view()`/`replay_field()` are metadata a repository
declares about itself — this package renders nothing itself, it only
carries the declaration.

## Structure

```
06-logger-and-view/
├── config.toml          # no extra settings needed — logging works out of the box
├── main.py               # entry point — plain script, no Service/UI involved
└── app/
    ├── __init__.py       # imports all modules so decorators register at startup
    ├── entities.py        # Reading — @Entity @dataclass
    ├── storages.py        # Store — @Component, in-memory
    └── repositories.py    # Readings — @Repository(Reading), Logger + LocationView + replay
```

## Run it

```bash
cd examples/06-logger-and-view
python main.py
```

This saves two readings, lists them back, prints `data_view()` (a
`LocationView` over `lat`/`lon`) and `replay_field()` (`recorded_at`), then
reads back the log entries `Readings` wrote for itself via
`project.context.tail_logs("Readings")` (see
[`docs/context.md`](../../docs/context.md)) — the same lines persisted to
`logs/readings.log`.
