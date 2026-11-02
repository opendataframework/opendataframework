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
| `notification`, `topic`, `notification_level`, `summary`, `subject`, `record`, `parent` | notification records | The [Notification](notifications.md#the-notification)'s fields (its `id` as `notification`), without its `payload` |
| `fields` | records with user fields | The keyword arguments of a `Logger` call |
| `parent` | records written during a protocol call | The `call` of the call in progress when a `Logger` line (or any other record) was written. Absent outside any call, e.g. in `__init__` |

The field names are fixed. A namespace never becomes a field name of its own,
so the schema is the same for every component, custom namespaces included.

### Tracing a call across files

A pipeline's steps log to their own files, and the ids tie them together: a
step's `parent` is the pipeline's `call`. `parent` is `null` for a top-level
call. `context.trace(call_id)` follows those links for you and returns the
whole call tree:

```python
logged = project.context.tail_logs("pipeline.nightly-orders")
run = next(r for r in reversed(logged) if r.get("state") == "failed")
trace = project.context.trace(run["call"])
```

```python
{"call": "3f9a1c2e…", "parent": None, "key": "pipeline.nightly-orders",
 "protocol": "PipelineProtocol", "method": "execute", "state": "failed",
 "started": "2026-10-31T10:00:00.120+01:00", "ended": "2026-10-31T10:00:00.124+01:00",
 "elapsed_ms": 4.1, "error": "ValueError('courier unavailable')",
 "logs": [{"ts": "2026-10-31T10:00:00.121+01:00", "level": "INFO",
           "message": "shipping", "fields": {"orders": 3}}],
 "notifications": [],
 "children": [
     {"call": "7ceee7cb…", "key": "task.price-orders", "state": "completed", ...,
      "children": [{"key": "function.price", ...}, ...]},
     {"call": "b71d04aa…", "key": "task.ship-orders", "state": "failed", ...,
      "children": []}]}
```

Each node merges a call's `started` and `completed`/`failed` records, and
children are ordered by when they started. A call that hasn't ended shows as
`"running"`. A notification is attached to the call it was published
during, under `notifications`, and a component's own log lines to the call
they were written in, under `logs` (each with `ts`, `level`, `message` and
`fields`). The tree is plain, JSON-ready data, so a UI
(such as the sibling [`odf`](https://opendataframework.github.io/odf/)
package's) can draw it as-is.

`trace()` reads every `.jsonl` file in the log directory once, so it works
after the call ended, and after a restart. Which files it reads follows the
configured format, never what happens to be on disk:

* With `format = "json"` (the default), it reads the `.jsonl` files only.
  `.log` files left over from an earlier `text` setup are ignored, so their
  calls aren't found (`KeyError`).
* With `format = "text"`, it raises `LogsUnavailable`: text lines read back
  as only `ts`, `level` and `message`, with no call structure to rebuild a
  tree from.
* With file logging off (no `log_dir`), it raises `LogsUnavailable` too.

`LogsUnavailable` (from `opendataframework`) is a `ValueError`, so code that
catches `ValueError` keeps working; catch it first to tell "this can't be
read here" from a bad argument. `context.logs()` raises it in the same
cases. A trace's notifications carry their `summary` as well as their
`message`.

It can only show records that were kept: with `events = "WARNING"`, only
failed calls appear, so a failure can still be traced back to its root but
successful steps are missing.

`trace(call_id)` returns the tree *below* the call. To get the whole story a
call belongs to, pass `root=True`: it climbs first, through `parent` links
and across [notification causes](notifications.md#ids-and-causes), and
returns the tree from the top. It never climbs into a Service's `run()` or a
Repository's `stream()` (see
[One Call per Inbound Item](service.md#one-call-per-inbound-item)).

### One call's records

A `Logger` line written inside a protocol call carries that call's id as
its `parent` — the same field an event record uses for its caller, and a
notification record for the call it was published during:

```python
@Task
class ShipOrders:
    def __init__(self, logger: Logger) -> None:
        self.logger = logger
        logger.info("ready")  # no parent: not inside a call

    def execute(self) -> None:
        self.logger.info("shipping", orders=3)  # parent = this execute() call
```

A line written by a function the task calls belongs to the function's call,
not the task's. `context.logs(call_id)` returns every record of one call
across files — its own `started`/`completed`, its log lines, its
notifications, and the start and end of the calls made directly inside it —
so a logs view can show one run, even while other runs of the same
component overlap with it. Unlike `trace()`, it doesn't follow nested calls.

To build the same tree from live [Events](events.md) instead, as they
arrive, use `opendataframework.events.build_trace(events, call_id)`. It takes
`Event`s, log records, or a mix of both.

The records can also be queried directly, with the standard library:

```python
import json
from pathlib import Path

records = [json.loads(line) for f in Path("logs").glob("*.jsonl") for line in f.open()]
failed = [r for r in records if r.get("state") == "failed"]
```

Or, if you have [jq](https://jqlang.org/) installed:

```bash
jq -c 'select(.state == "failed") | {key, call, parent, error}' logs/*.jsonl
```

### Text format

To read the files by eye, set the format to text:

```toml
[project.logging]
format = "text"
```

Files are then `logs/<namespace>.<name>.log`, with one readable line per
record. Call and parent ids are written in full, and user fields are
appended as `name=value`:

```
2026-10-31 10:00:00.120 INFO     execute() started [call=3f9a1c2e51b04d7c9e8f2a6b3c1d5e70 parent=-]
2026-10-31 10:00:00.123 INFO     execute() started [call=b71d04aa9c2e4f1d8a3b6c5d7e9f0a1b parent=3f9a1c2e51b04d7c9e8f2a6b3c1d5e70]
2026-10-31 10:00:00.124 ERROR    execute() failed in 0.2ms: ValueError('courier unavailable') [call=b71d04aa9c2e4f1d8a3b6c5d7e9f0a1b parent=3f9a1c2e51b04d7c9e8f2a6b3c1d5e70]
2026-10-31 10:00:00.130 INFO     order taken [parent=7ceee7cbd1a04f2e9b8c6d5a4e3f2a10] order_id=7 customer='Le Petit'
```

A `Logger` line written inside a call ends with `[parent=<id>]`, before
its fields. `grep 3f9a1c2e51b04d7c9e8f2a6b3c1d5e70 logs/*.log` then finds a call and
everything written directly inside it. The text format keeps only `ts`, `level` and `message` when read
back, and `context.trace()` isn't available. For structure, keep the default.

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

`tail_logs()` reads backwards from the end of the file, and into rotated
backups only if it needs more, so polling it stays cheap however large the
file has grown.

Notifications have a history of their own, read with
`context.notification_history()`: see
[Notifications — History](notifications.md#history).

### The `history/` directory

Every notification record is also written to
`<log-dir>/history/notifications.jsonl`, which holds nothing else, each line
with a sequence number, `seq`. The directory is created on the first
notification. It is always JSON Lines, whatever `format` says, and a record
is written there only if it passes its component's threshold. `tail_logs()`,
`context.logs()` and `context.trace()` never read it, so they never see a
notification twice.

---

## Rotation

By default a log file grows without limit. Set `max-bytes` to rotate it:

```toml
[project.logging]
max-bytes = 10_000_000          # off by default
backups = 5                     # the default
history-max-bytes = 20_000_000  # the notification history; defaults to max-bytes
history-backups = 5             # defaults to backups
```

Before a record would grow `task.load.jsonl` past `max-bytes`, the file
becomes `task.load.1.jsonl`, older backups shift up to `task.load.5.jsonl`,
and the one beyond `backups` is deleted (`.log` files likewise, in the text
format). A single record larger than `max-bytes` is still written whole.

`tail_logs()`, `context.logs()` and `context.trace()` read the backups as
well as the current file, so a trace still finds a call that was rotated
out of the current file — until its backup is deleted. Records rotated
away are gone: size `max-bytes` and `backups` for how far back you need to
trace. `context.trace(call_id, since=...)` skips files last written before
`since` (a `time.time()` value or a `datetime`), so passing a call's start
time keeps tracing a recent call cheap with many backups.

The notification history (`history/notifications.jsonl`) rotates the same
way, by `history-max-bytes` and `history-backups`, which default to
`max-bytes` and `backups`. Size it on its own: the busiest topic decides
how far back it reaches, so with the component sizes a rare notice would
rotate out at the pace of the noisiest one. With neither `max-bytes` nor
`history-max-bytes` set, nothing rotates; `history-max-bytes` alone rotates
only the history. They are flat keys rather than a `[project.logging.history]`
table, which would be a level table for a namespace named `history`.

!!! warning "One process per log directory"
    Rotation is coordinated within one process. Two processes writing the
    same log directory, each rotating on its own, would clobber each other's
    backups — give each its own `log-dir`. Reading the notification
    history back while it rotates is POSIX-only: on Windows a rotation fails
    while a reader has the file open.

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
