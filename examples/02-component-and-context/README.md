# 02 — Component + Context

Two `@Component`s, `Database` and `Cache`, where `Cache` depends on `Database`
through its constructor. No `Service`, no UI — the point of this example is to
make the `Context`'s dependency-ordered lifecycle visible, not to build
anything realistic.

This isolates the concept covered in [`docs/component.md`](../../docs/component.md)
and [`docs/context.md`](../../docs/context.md): a `Component` carries no
execution contract of its own, but it can optionally define `on_start()` /
`on_stop()`. The `Context` derives the dependency graph from constructor
signatures alone — no explicit wiring — then calls `on_start()` in dependency
order (`Database` before `Cache`) and `on_stop()` in reverse (`Cache` before
`Database`).

## Structure

```
02-component-and-context/
├── config.toml          # Database dsn
├── main.py              # entry point — plain script, no Service/UI involved
└── app/
    ├── __init__.py      # imports components.py so decorators register at startup
    └── components.py    # Database, Cache — @Component
```

## Run it

```bash
cd examples/02-component-and-context
python main.py
```

Expected output:

```
project.start() ...
Database.on_start  connecting to postgres://localhost/app
Cache.on_start     ready, store is empty
... start() returned

Cache.get('user:1') -> row for 'user:1' from postgres://localhost/app
Cache.get('user:1') -> row for 'user:1' from postgres://localhost/app  (already cached)

project.stop() ...
Cache.on_stop      dropping 1 cached entries
Database.on_stop   closing connection
... stop() returned
```

`Database` starts first and stops last — it's the dependency. `Cache` is only
built, started, and reachable once `Database` already exists.
