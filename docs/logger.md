# Logger

`Logger` is a per-component logging handle. It is declared as a constructor
dependency exactly like any other — `logger: Logger` — but the `Context`
resolves it differently from everything else: instead of handing out one
shared instance, every consumer receives its own `Logger`, already bound to
its own `<namespace>.<name>` key, so `self.logger.info(...)` needs no name argument and
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

Four levels are available, each writing one record to the component's own log
file, if the level passes the component's threshold (see [Levels](#levels)):

```python
self.logger.debug("...")  # dropped by default
self.logger.info("...")
self.logger.warning("...")
self.logger.error("...")
```

Keyword arguments are written as the record's structured `fields`, so they
can be filtered on later without parsing the message:

```python
self.logger.info("order taken", order_id=7, customer="Le Petit")
# {"ts": "…", "level": "INFO", "key": "task.take-orders", …,
#  "message": "order taken", "fields": {"order_id": 7, "customer": "Le Petit"}}
```

A value that isn't JSON-serializable is written as its `str()`, so a log call
never raises.

Only components that want to log explicitly need to declare it — omit the
parameter if you have nothing to say.

See [`examples/06-logger-and-view/`](examples.md) for a full runnable
project built around this.

---

## Automatic Logging

Most log lines require no code at all. The framework writes to each
component's log file on its behalf:

* **Resolution**: `"Users resolved"` (the class or function's own name), once
  each component is instantiated or each [Function](function.md) is bound.
* **Protocol calls**, written by [Events](events.md): every lifecycle or
  execution call the framework makes (`setup()`/`run()`/`stop()`,
  `on_start()`/`on_stop()`, `execute()`, `invoke()`, a `Function` call made
  through the `Context`, a repository's `stream()`) is logged when it starts and
  when it completes or fails, with its duration and any error.
* **Notifications**: every [Notification](notifications.md) published is
  logged on the publisher's key.

`logger: Logger` is only needed for messages specific to what a component is
actually doing. The framework-level lines above are covered either way.

Logs are for people; for code that needs to react to the same calls, use
[Events](events.md) instead of parsing log lines.

---

## Log Format

Each log line is one **record**. By default a file is
[JSON Lines](https://jsonlines.org/), `logs/<namespace>.<name>.jsonl`, with
one JSON object per line:

```json
{"ts": "2026-10-31T10:00:00.123+01:00", "level": "ERROR",
 "key": "task.ship-orders", "namespace": "task", "name": "ship-orders",
 "source": "events", "message": "execute() failed in 0.2ms: ValueError('courier unavailable')",
 "call": "b71d04aa9c2e4f1d8a3b6c5d7e9f0a1b", "parent": "3f9a1c2e51b04d7c9e8f2a6b3c1d5e70",
 "protocol": "TaskProtocol", "method": "execute", "state": "failed",
 "elapsed_ms": 0.21, "error": "ValueError('courier unavailable')"}
```

(Shown wrapped here; in the file each record is a single line.)

| Field | In | Meaning |
|---|---|---|
| `ts` | every record | ISO 8601, with milliseconds and the UTC offset |
| `level` | every record | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `key`, `namespace`, `name` | every record | The component: `task.ship-orders`, split into `task` and `ship-orders` |
| `source` | every record | `"events"`, `"notifications"`, or `null` for anything else |
| `message` | every record | Human-readable text |
| `call`, `parent`, `protocol`, `method`, `state`, `elapsed_ms`, `error` | protocol-call records | The [Event](events.md#the-event)'s fields, with full ids |
| `topic`, `notification_level`, `subject`, `record`, `parent` | notification records | The [Notification](notifications.md#the-notification)'s fields, without its `payload` |
| `fields` | records with user fields | The keyword arguments of a `Logger` call |

The field names are fixed. A namespace never becomes a field name of its own,
so the schema is the same for every component, custom namespaces included.

### Tracing a call across files

A pipeline's steps log to their own files, and the ids tie them together: a
step's `parent` is the pipeline's `call`. `parent` is `null` for a top-level
call. With the standard library:

```python
import json
from pathlib import Path

records = [json.loads(line) for f in Path("logs").glob("*.jsonl") for line in f.open()]
failed = [r for r in records if r.get("state") == "failed"]
steps = [r for r in records if r.get("parent") == failed[-1]["call"]]
```

Or, if you have [jq](https://jqlang.org/) installed:

```bash
jq -c 'select(.state == "failed") | {key, call, parent, error}' logs/*.jsonl
```

A notification's record carries the call it was published during as its
`parent`, so the same lookup finds what a call announced.

### Text format

To read the files by eye, set the format to text:

```toml
[project.logging]
format = "text"
```

Files are then `logs/<namespace>.<name>.log`, with one readable line per
record. Ids are shortened to 8 characters, and user fields are appended as
`name=value`:

```
2026-10-31 10:00:00.120 INFO     execute() started [call=3f9a1c2e parent=-]
2026-10-31 10:00:00.123 INFO     execute() started [call=b71d04aa parent=3f9a1c2e]
2026-10-31 10:00:00.124 ERROR    execute() failed in 0.2ms: ValueError('courier unavailable') [call=b71d04aa parent=3f9a1c2e]
2026-10-31 10:00:00.130 INFO     order taken order_id=7 customer='Le Petit'
```

`grep 3f9a1c2e logs/*.log` then finds a call and everything made directly
inside it. The text format keeps only `ts`, `level` and `message` when read
back. For structure, keep the default.

`opendataframework.logger.render(record)` turns a JSON record into that same
line, e.g. to pretty-print a `.jsonl` file.

---

## Levels

A record is written only if its level is at or above the threshold that
applies to it. Users never pass a level name in code: the `Logger` method
picks it, and the framework picks one for its own records (`INFO` for a call
starting or completing, `ERROR` for a failure, and a notification's own
`level` for its record). Thresholds are set under `[project.logging]`, next to
`format`:

```toml
[project.logging]
level = "INFO"            # default for every line
events = "WARNING"        # protocol-call lines: failures only
notifications = "INFO"    # "notified <topic>" lines

[project.logging.task]    # a namespace
level = "INFO"            # every task
take-orders = "DEBUG"     # one component
```

The namespace tables can also be written inline under `[project.logging]`,
as `task.level = "INFO"` and `task.take-orders = "DEBUG"`; TOML reads both
forms the same way.

**The most specific setting wins.** For a protocol-call line about
`task.take-orders`, the threshold is the first one set of:

1. `task.take-orders`, the component;
2. `task.level`, its namespace;
3. `events`, the line's source (`notifications` for a notification's line;
   a `Logger` call or a resolution line has none);
4. `level`, the default;
5. `INFO`.

A component or namespace setting covers every line about it. So in the
example above, every task's call lines are kept even though `events` is
`WARNING`. Without any configuration the threshold is `INFO`, so
`logger.debug()` lines are dropped until you enable them.

Level names are `DEBUG`, `INFO`, `WARNING` and `ERROR`, in any casing. They
are checked when the project is created. Namespace and component names are
checked when it starts: a name that doesn't exist, like a typo
`take-order`, raises `ValueError` listing the valid ones, rather than
silently setting nothing. `level` is reserved inside a namespace table, so a
component named `level` can't be set on its own.

A listener's exception (`listener raised ...`) is logged with no source, so
`events = "ERROR"` never hides a bug in your own listener.

Constructing a `Context` directly, pass the same mapping as
`Context(log_dir="logs", log_config={"level": "DEBUG"})`.

---

## Enabling File Logging

Log files are written under a single directory, one
`<namespace>.<name>.jsonl` (`.log` in the text format) per registered class or function — the same key
the [Context](context.md#by-key-single-component-control) addresses it by,
so `@Task class Loader` and `@Agent class Loader` never share a file —
scoped to one `Context`. `Project.from_config`/`from_dict` enable it
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

`Context.tail_logs(key, lines=300)` returns the most recent records for
a component, oldest first, as dicts:

```python
project.context.tail_logs("service.postgres", lines=100)
# → [{"ts": "2026-10-31T10:00:00.123+01:00", "level": "INFO", "key": "service.postgres",
#     ..., "message": "setup() started", "call": "3f9a1c2e…", "parent": None, ...}, ...]
```

Every record has at least `ts`, `level` and `message`. In the text format
those three are all that come back.

!!! tip "Seeing it in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI's per-component log panel is backed by this same method, via
    `GET /api/components/{component_id}/logs`.

---

## Not a Singleton — Special-Cased Resolution

Every other registered class (`Component`, `Service`, `Task`, `Pipeline`,
`Agent`, `Repository`) is a per-`Context` singleton: `Context` creates exactly one
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
