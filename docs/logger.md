# Logger

`Logger` is a per-component logging handle. It is declared as a constructor
dependency exactly like any other — `logger: Logger` — but the `Context`
resolves it differently from everything else: instead of handing out one
shared instance, every consumer receives its own `Logger`, already bound to
its own class name, so `self.logger.info(...)` needs no name argument and
still lands in that component's own log file.

---

## Declaring it

```python
from opendataframework import Logger, Task

@Task
class ExportUsers:

    def __init__(self, users: Users, logger: Logger) -> None:
        self.users = users
        self.logger = logger

    def execute(self) -> None:
        self.logger.info("export starting")
        ...
```

Four levels are available, each writing one line to the component's own log
file:

```python
self.logger.debug("...")
self.logger.info("...")
self.logger.warning("...")
self.logger.error("...")
```

Only components that want to log explicitly need to declare it — omit the
parameter if you have nothing to say.

See [`examples/06-logger-and-view/`](examples.md) for a full runnable
project built around this.

---

## Automatic Logging

Most log lines require no code at all. `Context` writes to each component's log
file on its behalf:

* **Resolution** — `"<Class> resolved"`, once each component is instantiated.
* **Lifecycle** — `setup()`/`run()`/`stop()` for a `Service`, `on_start()`/
  `on_stop()` for a `Component`/`Repository` — start, completion, and any
  raised exception.
* **Execution** — `execute()` for a `Task`/`Pipeline` — start, duration, and
  any raised exception.

`logger: Logger` is only needed for messages specific to what a component is
actually doing — the framework-level lifecycle noise above is covered either
way.

---

## Enabling File Logging

Log files are written under a single directory, one `<component>.log` per
class, scoped to one `Context`. `Project.from_config`/`from_dict` enable it
automatically under `[project] log-dir` (default `"logs"`, relative to the
current working directory):

```toml
[project]
log-dir = "logs"
```

Constructing a `Context` directly without a `log_dir` disables file logging
entirely: writes become no-ops and reads return nothing.

---

## Reading Logs Back

`Context.tail_logs(component, lines=300)` returns the most recent entries for
a component, oldest first:

```python
project.context.tail_logs("Postgres", lines=100)
# → [{"ts": "2026-08-08 10:00:00", "level": "INFO", "message": "setup() starting"}, ...]
```

!!! tip "Seeing it in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI's per-component log panel is backed by this same method, via
    `GET /api/components/{component_id}/logs`.

---

## Not a Singleton — Special-Cased Resolution

Every other registered class (`Component`, `Service`, `Task`, `Pipeline`,
`Repository`) is a per-`Context` singleton: `Context` creates exactly one
instance and stores it under that class in `Context.instances`, which is what
`project.context.get(cls)` looks up (see [Context](context.md#direct-access)).

`Logger` doesn't fit that model, so it isn't registered in any namespace and
never gets a slot in `Context.instances` at all. Instead, `Context` detects
a `logger: Logger` constructor parameter directly and supplies a fresh
`Logger` bound to the *consuming* class's own name. A `Context` with ten
components that all declare `logger: Logger` has ten live `Logger` instances,
each writing to a different file; there is no single canonical one.

Practically, this means:

```python
project.context.get(Logger)  # doesn't work — no canonical instance to return
```

There's no equivalent lookup for `Logger` — it only exists bound to whichever
class asked for it via its own constructor.

---

## What Logger is Not

* **Not resolvable via `context.get(Logger)`.** `Logger` is never registered
  in a namespace or given a slot in `Context.instances`, so there's no single
  shared instance to fetch.

* **Not a global or process-wide logger.** Each `Context` owns its own set of
  log files, with nothing shared implicitly across `Project` instances.
  Nothing stops two `Project`s configured with the same `log_dir` from
  writing to the same files, though — keeping `log_dir` distinct per
  `Project` is up to you.

* **Not enabled by default outside `Project.from_config`/`from_dict`.** A
  bare `Context()` has no `log_dir`, so logging is a no-op unless one is
  passed explicitly.
