# 05 — Layer

Two components in two different layers: `Warehouse` is `@Storage`, `UsageTracker`
is `@Analytics` and depends on `Warehouse` through its constructor — a normal
DI dependency that happens to cross layers. `main.py` reads both back through
`project.context.get(cls)`, typed by the class passed in, and inspects layer
membership directly through `Storage.items()`/`Analytics.items()`.

This isolates the concept covered in [`docs/layer.md`](../../docs/layer.md): a
`Layer` answers "which subsystem does this belong to" and is entirely
independent of a component's execution type (`Component`, `Service`, `Task`,
`Pipeline`) — nothing stops an `@Analytics` component from depending on an
`@Storage` one.

## Structure

```
05-layer/
├── config.toml       # no custom keys needed for this example
├── main.py           # entry point — reads components back via project.context.get()
└── app/
    ├── __init__.py   # imports both modules so decorators register at startup
    ├── storage.py    # Warehouse — @Storage @Component
    └── analytics.py  # UsageTracker — @Analytics @Component, depends on Warehouse
```

## Run it

```bash
cd examples/05-layer
python main.py
```

Expected output:

```
tracker summary: {'events': 2, 'warehouse_items': 2}

Warehouse (via Storage layer): ['signup', 'login']

Storage layer members:   {'warehouse': <class 'app.storage.Warehouse'>}
Analytics layer members: {'usage-tracker': <class 'app.analytics.UsageTracker'>}
```
