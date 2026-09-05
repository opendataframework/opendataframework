# 01 — Entity + Repository

The smallest possible ODF data layer: one `@Entity`, one `@Repository` that manages
it, and a `SQLite` `@Component` the repository depends on. No `Service`, no UI —
just a `Project` and the CRUD methods a repository conventionally exposes
(`all()` / `get()` / `save()` / `delete()`).

This isolates the concept covered in [`docs/entity.md`](../../docs/entity.md) and
[`docs/repository.md`](../../docs/repository.md): an `Entity` describes the shape of
data, a `Repository` answers "where does the data come from", and the `Context`
wires the two together with `SQLite` through constructor dependency injection —
nothing here is registered or connected by hand.

## Structure

```
01-entity-repository/
├── config.toml          # SQLite path
├── main.py              # entry point — plain script, no Service/UI involved
└── app/
    ├── __init__.py      # imports all modules so decorators register at startup
    ├── entities.py      # Book — @Entity @dataclass
    ├── storages.py       # SQLite — @Component
    └── repositories.py  # Books — @Repository(Book)
```

## Run it

```bash
cd examples/01-entity-repository
python main.py
```

This saves two books, lists them, updates one, and deletes it — printing each step
via `project.context.get(Books)`, which returns the resolved `Books` instance typed
as `Books` (see [`docs/context.md`](../../docs/context.md)).
