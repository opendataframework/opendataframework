# Events

`Events` reports, as it happens, every protocol call the framework makes on
your components: a `Service`'s `setup()`, a `Task`'s `execute()`, a
repository's `on_start()`, a [Function](function.md) call, and so on. Each
call is reported when it starts and again when it completes or fails, as an
`Event`. Logs are for people; events are for code: alerting on a failure,
collecting metrics, or animating a live view of the project.

Every event is also written to its component's log file, with its call id
and its parent's, so a call can be traced across files:
`context.trace(call_id)` returns a call's whole tree from the logs, and
`build_trace(events, call_id)` builds the same tree from live events (see
[Logger](logger.md#tracing-a-call-across-files)).

It is the classic Observer pattern. `Events` is the subject, one per
`Context`; a listener is any callable that takes an `Event`; listeners
`subscribe`, and the framework notifies them around each protocol call.

---

## Declaring it

`Events` is declared as a constructor dependency like any other, and is
special-cased the way [Logger](logger.md) is. Every consumer receives the
`Context`'s own instance:

```python
from queue import Queue

from opendataframework import Component, Event, Events


@Component
class FailureAlerts:
    def __init__(self, events: Events) -> None:
        self.queue: Queue[Event | None] = Queue()
        self._unsubscribe = events.subscribe(self.queue.put)

    def on_stop(self) -> None:
        self._unsubscribe()
```

Code that holds the `Context` itself (a script, a test, the sibling
[`odf`](https://opendataframework.github.io/odf/) package's UI server) reaches
the same instance as `context.events`:

```python
project.context.events.subscribe(print)
```

See [`examples/10-events/`](examples.md) for a full runnable project built
around this. For messages your own components publish, see
[Notifications](notifications.md).

---

## Subscribing

```python
unsubscribe = events.subscribe(listener)  # every event
unsubscribe = events.subscribe(listener, protocol=ServiceProtocol)  # one protocol only
unsubscribe()  # stop; safe to call twice
```

`protocol` is an exact match. `TaskProtocol` and `PipelineProtocol` both
have an `execute()`, but `protocol=TaskProtocol` receives only task calls.

---

## The Event

| Field | Meaning |
|---|---|
| `key` | The component's `<namespace>.<name>` key, e.g. `"service.postgres"`. |
| `protocol` | The protocol whose method was called, e.g. `ServiceProtocol`. |
| `method` | The method called, e.g. `"setup"`, `"execute"`, `"__call__"`. |
| `state` | `"started"`, `"completed"`, or `"failed"`. |
| `call_id` | Identifies the call; shared by its `started` and `completed`/`failed` event. |
| `parent` | `call_id` of the call this one happened inside, or `None`. |
| `ts` | `time.time()` when the event was emitted. |
| `elapsed_ms` | Duration, on `completed`/`failed` only. |
| `error` | `repr()` of the exception, on `failed` only. |

To react to one kind of call, subscribe with `protocol=` and check the rest:

```python
def on_service(event: Event) -> None:
    if event.method == "run" and event.state == "failed":
        ...  # a service crashed
```

!!! warning "Matching on a protocol"
    In a `match` statement, a bare name in a pattern *captures* instead of
    comparing, so `case Event(protocol=TaskProtocol)` matches every event.
    Check the protocol in a guard instead:
    `case Event(state="failed") if event.protocol is TaskProtocol:`.

---

## Which Protocols Emit Events

The rule: **every lifecycle or execution protocol method the framework calls
emits events. Nothing else does.**

| Protocol | Methods | Events |
|---|---|---|
| [`ServiceProtocol`](service.md) | `setup`, `run`, `stop` | Yes |
| `OnStartProtocol` / `OnStopProtocol` | `on_start` / `on_stop` | Yes, for any non-service component or [repository](repository.md) that defines them |
| [`TaskProtocol`](task.md) | `execute` | Yes |
| [`PipelineProtocol`](pipeline.md) | `execute` | Yes |
| [`AgentProtocol`](agent.md) | `invoke` | Yes |
| [`FunctionProtocol`](function.md) | `__call__` | Yes, for calls made through the `Context` (see below) |
| `OpenStreamProtocol` / `StreamableProtocol` / `CloseStreamProtocol` | `open_stream` / `stream` / `close_stream` | Yes, once per stream start (never per item) |
| `WritableProtocol` | `save`, `delete` | Not yet, and still undecided. Writes change state and may be worth reacting to, but the framework never calls them itself. |
| `ReadableProtocol`, `DetailsProtocol`, `ChartProtocol`, `McpToolsProtocol` | `all`, `details`, `chart`, `mcp_tools` | No, and not planned. These are capability queries, not actions; the framework never calls them, and a UI polling them would flood listeners. |

Items a stream produces never become events. `context.iter_stream(key)`
already serves them.

### Function calls

A `@Function` is returned unchanged, so only calls that go through the
`Context` are reported: injected into a class, through
`context.call(key, ...)`, or through `context.get(func)`. Calling the function
directly by name emits nothing, just as it logs nothing.

```python
from collections.abc import Callable
from typing import Annotated

from opendataframework import Component, Event, Events, Function, FunctionProtocol, Task


@Function
def load_data(path: str, db: Db) -> int:  # db injected, path supplied by the caller
    return db.insert(read_csv(path))


@Task
class DailyImport:
    def __init__(self, load: Annotated[Callable[..., int], load_data]) -> None:
        self.load = load

    def execute(self) -> None:
        self.load("data/today.csv")  # reported as a FunctionProtocol call


@Component
class SlowCalls:
    def __init__(self, events: Events) -> None:
        self._unsubscribe = events.subscribe(self.on_call, protocol=FunctionProtocol)

    def on_call(self, event: Event) -> None:
        if event.state == "completed" and event.elapsed_ms > 1000:
            print(f"{event.key} took {event.elapsed_ms:.0f}ms")
```

`context.execute("task.daily-import")` emits:

```
TaskProtocol      execute   started    task.daily-import    call_id=a1  parent=None
FunctionProtocol  __call__  started    function.load-data   call_id=b2  parent=a1
FunctionProtocol  __call__  completed  function.load-data   call_id=b2  parent=a1
TaskProtocol      execute   completed  task.daily-import    call_id=a1  parent=None
```

`SlowCalls` receives only the two `FunctionProtocol` events.

---

## How `parent` Nests

A call's `parent` is the call in progress, in the same thread, when it
started:

* A pipeline's steps have the pipeline's call as their parent.
* A function a task calls has the task's call as its parent.
* A call made inside a service's `run()` has that `run` call as its parent.
* A service's `run()` and a repository's `stream()` run on their own
  threads, so they are always top-level (`parent=None`).
* A call a listener makes is top-level too, because nothing called it. A
  cleanup task a listener starts when it sees a failure isn't a child of the
  call that failed.

---

## Listeners Run Inline

A listener is called synchronously, in the thread making the call, at the
moment the state changes. That has consequences:

* **It delays the call.** A listener that takes two seconds holds up the
  call it was notified about for two seconds, and those seconds count in the
  call's `elapsed_ms`. During startup, it holds up the whole startup.
* **It must be thread-safe.** A service's `run()` and a stream report from
  their own threads, so listeners are called from several threads.
* **It can feed back on itself.** A listener that starts a call is notified
  about that call too. Reacting to every event by starting a call loops
  forever, so filter narrowly (a specific `protocol`, `key`, and `state`).
* **Its exceptions are contained.** If a listener raises, the exception is
  logged as a `WARNING` (`listener raised ...`) in that component's log and
  never reaches the call or other listeners.

So keep a listener to recording the event, and do the work elsewhere. The
recommended shape is a listener that only puts events on a queue, plus a
[Service](service.md) that drains it:

```python
from queue import Queue

from opendataframework import Component, Event, Events, Service


@Component
class FailureAlerts:
    def __init__(self, events: Events) -> None:
        self.queue: Queue[Event | None] = Queue()
        self._unsubscribe = events.subscribe(self.queue.put)  # instant, thread-safe

    def on_stop(self) -> None:
        self._unsubscribe()


@Service
class AlertSender:
    def __init__(self, alerts: FailureAlerts, slack: Slack) -> None:
        self.alerts = alerts
        self.slack = slack

    def setup(self) -> None: ...

    def run(self) -> None:
        while (event := self.alerts.queue.get()) is not None:
            if event.state == "failed":
                self.slack.post(f"{event.key} {event.method}() failed: {event.error}")

    def stop(self) -> None:
        self.alerts.queue.put(None)  # lets run() return
```

---

## Startup Timing

Subscribe in `__init__`, not in `on_start()`. The `Context` constructs every
component before it calls any `setup()` or `on_start()`, so a listener
subscribed in `__init__` sees the whole startup. One subscribed in
`on_start()` misses the calls made before its own hook ran.

The flip side is that a listener subscribed in `__init__` can be notified
about unrelated components before its own dependencies have started. Another
reason to only enqueue: in the example above, `AlertSender.run()` starts only
after `Slack` is set up, and anything reported earlier waits in the queue.

---

## What Events is Not

* **Not logging, though it writes the call records.** `Events` writes each
  call's `started`/`completed`/`failed` as a record in the component's log,
  with the event's fields (`call`, `parent`, `protocol`, `method`, `state`,
  `elapsed_ms`, `error`; see [Log Format](logger.md#log-format)). `started` and
  `completed` are written at `INFO`, `failed` at `ERROR`, and
  `[project.logging] events = ...` sets their threshold (see
  [Levels](logger.md#levels)). Events are delivered to listeners whether or
  not they're logged, and they work with file logging off (`log_dir=None`).
  The log is for people and tools; `Events` is for code in the process.

* **Not a way to emit your own events.** `notify()` is how the framework
  reports its protocol calls; it isn't meant for user code. To announce
  something your own code did or saw, publish a
  [Notification](notifications.md) instead.

* **Not global.** Each `Context` has its own `Events` and its own listeners,
  so two `Project`s in one process never see each other's calls.

* **Not asynchronous.** There is no queue, thread, or transport inside
  `Events`. A listener runs inline, and anything else (an SSE stream, a
  message bus) is built on top of it.
