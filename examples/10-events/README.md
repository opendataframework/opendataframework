# 10 — Events

A nightly order run: `NightlyOrders`, a `@Pipeline`, prices every order with
`PriceOrders` (a `@Task` that calls an injected `price` `@Function`), then
fails to ship them in `ShipOrders`. Three components watch it happen, without
the pipeline, the tasks or the function knowing about them.

This isolates the concept covered in [`docs/events.md`](../../docs/events.md):
every lifecycle or execution protocol call the framework makes is reported as
an `Event` (`started`, then `completed` or `failed`). A component declares
`events: Events` in its constructor, like `logger: Logger`, and subscribes
there:

- `CallTrace` subscribes to everything and records each call with its
  `parent`, so it can print who called whom as a tree.
- `FailureAlerts` only puts failed calls on a queue. A listener runs inside
  the call it is notified about, so it does nothing slow itself.
- `AlertSender`, a `@Service`, drains that queue in `run()`, off the calls'
  hot path. This is the recommended shape for a listener with real work to do.
- `FunctionCalls` subscribes with `protocol=FunctionProtocol`, so it only
  hears about `@Function` calls.

Subscribing in `__init__` matters: the `Context` constructs every component
before it calls any `setup()` or `on_start()`, so all three also see startup.

## Structure

```
10-events/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — runs the pipeline, prints what the listeners saw
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── components.py      # Orders — @Component, loaded in on_start()
    ├── functions.py       # price — @Function
    ├── tasks.py           # PriceOrders (price injected), ShipOrders (fails) — @Task
    ├── pipelines.py       # NightlyOrders — @Pipeline
    ├── listeners.py       # CallTrace, FailureAlerts, FunctionCalls — @Component, events: Events
    └── services.py        # AlertSender — @Service draining FailureAlerts' queue
```

## Run it

```bash
cd examples/10-events
python main.py
```

Expected output:

```
execute('pipeline.nightly-orders') raised ValueError('courier unavailable')

Call tree:
  pipeline.nightly-orders execute()        PipelineProtocol  failed
    task.price-orders execute()            TaskProtocol      completed
      function.price __call__()            FunctionProtocol  completed
      function.price __call__()            FunctionProtocol  completed
      function.price __call__()            FunctionProtocol  completed
    task.ship-orders execute()             TaskProtocol      failed

Function calls (protocol=FunctionProtocol):
  function.price x3

Alerts sent by AlertSender:
  task.ship-orders execute() failed: ValueError('courier unavailable')
  pipeline.nightly-orders execute() failed: ValueError('courier unavailable')

Every call seen, startup and shutdown included:
  component.call-trace on_stop()
  component.failure-alerts on_stop()
  component.function-calls on_stop()
  component.orders on_start()
  function.price __call__()
  pipeline.nightly-orders execute()
  service.alert-sender run()
  service.alert-sender setup()
  service.alert-sender stop()
  task.price-orders execute()
  task.ship-orders execute()
```

What to notice:

- **`parent` builds the tree.** Each step's `parent` is the pipeline's call,
  and each `price` call's `parent` is `PriceOrders`' call. Nothing in the
  pipeline or the tasks passes anything along.
- **A failure is reported at every level.** `ShipOrders` fails, and so does
  the pipeline it raised through, so `AlertSender` sends two alerts.
- **Startup and shutdown are calls too.** `Orders.on_start()`,
  `AlertSender`'s `setup()`/`run()`/`stop()` and the listeners' own
  `on_stop()` are all in the last list.
- **The output is printed after `project.stop()`.** `AlertSender.run()` runs
  on its own thread, so its alerts are read only once `stop()` has waited for
  the queue to drain.

The tests in `tests/examples/events/` drive the listeners with a bare `Events`
and `events.notify(...)`, the same call the framework wraps each protocol call
in, so they need no `Project`.
