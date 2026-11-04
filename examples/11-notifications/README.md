# 11 — Notifications

A bakery's order intake. `TakeOrders`, a `@Task`, saves every order waiting in
the `Inbox` (a stand-in for a café POS or a messenger) to the `Orders`
repository, then publishes `orders.received`, plus an `orders.large` warning
for a big order. It doesn't know who is listening.

This isolates the concept covered in
[`docs/notifications.md`](../../docs/notifications.md). A component publishes
a `Notification` (a topic, a payload, an optional summary) about something
that happened (here, an order arriving), and other components react to it:

- `TakeOrders` is a `@Publisher("orders.received", "orders.large")`. It
  declares `notifications: Notifications`, like `logger: Logger`, and
  receives a view bound to its own key, so `publish()` needs no key. It may
  publish only the topics it declares, and only inside a protocol call (its
  `execute()`), so every notification can be traced.
- `Kitchen` is a `@Subscriber("orders.received")`. The `Context` calls its
  `on_notification()` while it runs, and it reacts by calling an injected
  `schedule_bake` `@Function`.
- `OrderCounter` is a `@Subscriber("orders.*", deliver="background")`: it
  matches both topics by prefix, and counts them on a worker thread of its
  own, so it never holds up the publisher. `project.stop()` drains its queue
  first.
- `main.py` plays the UI. It subscribes through `context.notifications` and
  shows a toast for every notification that has a summary.

The reaction is linked to what caused it **through the notification**, not by
nesting. Each `on_notification()` is a top-level call (`parent=None`) whose
`cause` is the notification's `id`, and `schedule_bake()` is its child. The
notification's own `parent` is the `TakeOrders.execute()` call it was
published during. So `context.trace()` of that one call reaches every
reaction: publisher → notification → `on_notification()` → `schedule_bake()`.

## Structure

```
11-notifications/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — takes the orders, prints the reactions and the trace
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── entities.py        # Order — @Entity
    ├── repositories.py    # Orders — @Repository, in memory
    ├── components.py      # Inbox — @Component, loaded in on_start()
    ├── functions.py       # schedule_bake — @Function
    ├── tasks.py           # TakeOrders — @Publisher @Task, notifications: Notifications
    └── subscribers.py     # Kitchen, OrderCounter — @Subscriber @Component
```

## Run it

```bash
cd examples/11-notifications
python main.py
```

Expected output:

```
Subscribers:
  component.kitchen <- orders.received (sync)
  component.order-counter <- orders.* (background)

execute('task.take-orders') took 2 orders

Toasts (what a UI would show):
  [info   ] Le Petit: 2 x baguette   (orders.received, repository.orders #1)
  [info   ] Millers Ltd: 12 x sourdough   (orders.received, repository.orders #2)
  [warning] Large order from Millers Ltd: check flour stock   (orders.large, repository.orders #2)

Kitchen's bakes:
  bake 2 x baguette for Le Petit
  bake 12 x sourdough for Millers Ltd

OrderCounter (topic='orders.*', background):
  orders.large x1
  orders.received x2

Trace of the execute() call, from the logs:
  task.take-orders execute() completed
    -> notified orders.received
         component.kitchen on_notification() completed  [caused by the notification]
           function.schedule-bake __call__() completed
         component.order-counter on_notification() completed  [caused by the notification]
    -> notified orders.received
         component.kitchen on_notification() completed  [caused by the notification]
           function.schedule-bake __call__() completed
         component.order-counter on_notification() completed  [caused by the notification]
    -> notified orders.large
         component.order-counter on_notification() completed  [caused by the notification]
```

Each publish is also logged in the publisher's own file,
`logs/task.take-orders.jsonl`, as a record at the level matching the
notification's. The record carries the notification's `id` (as `notification`),
`topic`, `subject` and `record`, and the call it was published during as its
`parent`, which is the `call` of TakeOrders' `execute()` record. Each
subscriber's `on_notification()` records, in its own file, carry that `id`
as their `cause`. Ids differ on every run; records are
shortened here:

```json
{"level": "INFO", "message": "execute() started", "call": "5e2b90c1…", "parent": null, "state": "started", …}
{"level": "INFO", "message": "notified orders.received: Le Petit: 2 x baguette", "notification": "8d41f0a7…", "topic": "orders.received", "subject": "repository.orders", "record": 1, "parent": "5e2b90c1…", …}
{"level": "INFO", "message": "notified orders.received: Millers Ltd: 12 x sourdough", "topic": "orders.received", "record": 2, "parent": "5e2b90c1…", …}
{"level": "WARNING", "message": "notified orders.large: Large order from Millers Ltd: check flour stock", "topic": "orders.large", "notification_level": "warning", "parent": "5e2b90c1…", …}
{"level": "INFO", "message": "execute() completed in 0.2ms", "call": "5e2b90c1…", "parent": null, "state": "completed", …}
```
