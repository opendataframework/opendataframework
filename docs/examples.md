# Examples

Small, focused `opendataframework` projects, each isolating exactly one
core abstraction, with runnable code you can read end-to-end. They live in
[`examples/`](https://github.com/opendataframework/opendataframework/tree/main/examples)
in the repo; each has its own `README.md` with a full walkthrough. Read
1–7 in order — each one builds on ideas from the last.

| # | Example | Concept(s) | Docs |
|---|---|---|---|
| 1 | [`01-entity-repository/`](https://github.com/opendataframework/opendataframework/tree/main/examples/01-entity-repository) | [Entity](entity.md) + [Repository](repository.md), backed by a `SQLite` `@Component`. The smallest possible data layer — no `Service`, no UI. | [Entity](entity.md), [Repository](repository.md) |
| 2 | [`02-component-and-context/`](https://github.com/opendataframework/opendataframework/tree/main/examples/02-component-and-context) | Two [Component](component.md)s with a constructor dependency, showing the [Context](context.md)'s dependency-ordered `on_start()`/`on_stop()` lifecycle. | [Component](component.md), [Context](context.md) |
| 3 | [`03-service/`](https://github.com/opendataframework/opendataframework/tree/main/examples/03-service) | A `Heartbeat` [Service](service.md): `setup() → run() → stop()`, `run()` backgrounded by the framework. Deliberately not an API server. | [Service](service.md) |
| 4 | [`04-task-and-pipeline/`](https://github.com/opendataframework/opendataframework/tree/main/examples/04-task-and-pipeline) | Two [Task](task.md)s composed into a [Pipeline](pipeline.md) that coordinates them, run explicitly via `project.context.get(...).execute()`. | [Task](task.md), [Pipeline](pipeline.md) |
| 5 | [`05-layer/`](https://github.com/opendataframework/opendataframework/tree/main/examples/05-layer) | Components split across two [Layer](layer.md)s (`@Storage`, `@Analytics`), read back through `project.context.get(cls)`. | [Layer](layer.md) |
| 6 | [`06-logger-and-view/`](https://github.com/opendataframework/opendataframework/tree/main/examples/06-logger-and-view) | A `Repository` with an injected `logger:` [Logger](logger.md) and `data_view()`/`replay_field()` ([View](view.md)) — per-component logging and self-describing data representation. | [Logger](logger.md), [View](view.md) |
| 7 | [`07-config-environments/`](https://github.com/opendataframework/opendataframework/tree/main/examples/07-config-environments) | Same `app/` code, two config directories (`config/dev/`, `config/prod/`) — no environment flag, just a different path. | [Config](config.md) |

Every example is self-contained: `config.toml` (or a `config/` directory)
plus an `app/` package, runnable with `python main.py` from inside the
example's own directory. None of them add third-party dependencies beyond
`opendataframework` itself and the Python standard library.

!!! tip "Looking for the CLI, UI, MCP, or chat?"
    Those, and the full `DataView` catalog, are out of scope here on purpose — see the
    [`odf`](https://opendataframework.github.io/odf/) package's own `examples/` instead,
    which depends on `opendataframework` and demonstrates that surface.

!!! note "Why no Namespace or Project example"
    [Namespace](namespace.md) and [Project](project.md) appear as supporting cast
    throughout every example above (every `main.py` uses `Project`; every decorator is
    built on `Namespace`), so a standalone example would mostly repeat what's already
    shown.
