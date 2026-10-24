# Examples

Small, focused `opendataframework` projects, each isolating exactly one
core abstraction. Every example here has nothing else competing for
attention. Read 1–10 in order; each one builds on ideas from the last.

| # | Example | Concept(s) | Docs |
|---|---|---|---|
| 1 | [`01-entity-repository/`](01-entity-repository/) | `Entity` + `Repository`, backed by a `SQLite` `@Component`. The smallest possible data layer — no `Service`, no UI. | `entity.md`, `repository.md` |
| 2 | [`02-component-and-context/`](02-component-and-context/) | Two `@Component`s with a constructor dependency, showing the `Context`'s dependency-ordered `on_start()`/`on_stop()` lifecycle. | `component.md`, `context.md` |
| 3 | [`03-service/`](03-service/) | A `Heartbeat` `@Service`: `setup() → run() → stop()`, `run()` backgrounded by the framework. Deliberately not an API server. | `service.md` |
| 4 | [`04-task-and-pipeline/`](04-task-and-pipeline/) | Two `@Task`s composed into a `@Pipeline` that coordinates them, run explicitly via `project.context.get(...).execute()`. | `task.md`, `pipeline.md` |
| 5 | [`05-layer/`](05-layer/) | Components split across two `@Layer`s (`@Storage`, `@Analytics`), read back through `project.context.get(cls)`. | `layer.md` |
| 6 | [`06-logger-and-view/`](06-logger-and-view/) | A `Repository` with an injected `logger: Logger` and `data_view()`/`field()` — per-component logging and self-describing data representation. | `logger.md`, `view.md` |
| 7 | [`07-config-environments/`](07-config-environments/) | Same `app/` code, two config directories (`config/dev/`, `config/prod/`) — no environment flag, just a different path. | `config.md` |
| 8 | [`08-function/`](08-function/) | Plain functions made framework-aware with `@Function`: called by name through `project.context.call(...)` with an injected `@Component`, injected into a `@Task`, and still callable directly, unchanged. | `function.md` |
| 9 | [`09-agent/`](09-agent/) | A `Librarian` `@Agent`: handed a question through `project.context.call(...)`, it works towards an answer step by step, acting on an injected `@Component`. The model is a rule-based stand-in — no provider, no API key. | `agent.md` |
| 10 | [`10-events/`](10-events/) | Components declaring `events: Events` watch a `@Pipeline` run: a call tree built from each call's `parent`, failures queued for a `@Service` to send, and `@Function` calls counted with a protocol filter. | `events.md` |

Every example is self-contained: `config.toml` (or a `config/` directory) plus
an `app/` package, runnable with `python main.py` from inside the example's
own directory. None of them add third-party dependencies beyond
`opendataframework` itself and the Python standard library.

Out of scope here on purpose: the CLI (`odf init`/`odf run`), the UI, MCP,
chat, and the full `DataView` catalog. Those live in the separate `odf`
package — see its own `examples/` — which depends on `opendataframework`
and demonstrates that surface instead.
