# 11 — Notifications

A bakery's order intake. `TakeOrders`, a `@Task`, saves every order waiting in
the `Inbox` (a stand-in for a café POS or a messenger) to the `Orders`
repository, then publishes `orders.received`, plus an `orders.large` warning
for a big order. It doesn't know who is listening.

This isolates the concept covered in
[`docs/notifications.md`](../../docs/notifications.md). A component publishes
a `Notification` (a topic, a payload, an optional summary) about something
that happened (here, an order arriving). A component declares
`notifications: Notifications`, like `logger: Logger`, and receives a view
bound to its own key:

- `TakeOrders` publishes through its view, so `publish()` needs no key.
- `Kitchen` subscribes to `orders.received` and reacts by calling an injected
  `schedule_bake` `@Function`.
- `OrderCounter` subscribes to `orders.*`, matching both topics by prefix.
- `main.py` plays the UI. It subscribes through `context.notifications` and
  shows a toast for every notification that has a summary.

The reaction is linked to what caused it **through the notification**, not by
nesting. Kitchen's `schedule_bake()` call is top-level (`parent=None`),
because listeners run with no current call. The notification's own `parent`
is the `TakeOrders.execute()` call it was published during.

## Structure

```
11-notifications/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — takes the orders, prints what the subscribers saw
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── entities.py        # Order — @Entity
    ├── repositories.py    # Orders — @Repository, in memory
    ├── components.py      # Inbox — @Component, loaded in on_start()
    ├── functions.py       # schedule_bake — @Function
    ├── tasks.py           # TakeOrders — @Task, notifications: Notifications
    └── listeners.py       # Kitchen, OrderCounter — @Component, subscribe in __init__
```

## Run it

```bash
cd examples/11-notifications
python main.py
```

Expected output:

```
execute('task.take-orders') took 2 orders

Toasts (what a UI would show):
  [info   ] Le Petit: 2 x baguette   (orders.received, repository.orders #1)
  [info   ] Millers Ltd: 12 x sourdough   (orders.received, repository.orders #2)
  [warning] Large order from Millers Ltd: check flour stock   (orders.large, repository.orders #2)

Kitchen's reactions:
  bake 2 x baguette for Le Petit
    notification published during: task.take-orders execute()
    schedule_bake() call's parent: none (top-level)
  bake 12 x sourdough for Millers Ltd
    notification published during: task.take-orders execute()
    schedule_bake() call's parent: none (top-level)

OrderCounter (topic='orders.*'):
  orders.received x2
  orders.large x1
```

Each publish is also logged in the publisher's own file,
`logs/task.take-orders.jsonl`, as a record at the level matching the
notification's. The record carries the notification's `topic`, `subject` and
`record`, and the call it was published during as its `parent`, which is the
`call` of TakeOrders' `execute()` record. Ids differ on every run; records are
shortened here:

```json
{"level": "INFO", "message": "execute() started", "call": "5e2b90c1…", "parent": null, "state": "started", …}
{"level": "INFO", "message": "notified orders.received: Le Petit: 2 x baguette", "topic": "orders.received", "subject": "repository.orders", "record": 1, "parent": "5e2b90c1…", …}
{"level": "INFO", "message": "notified orders.received: Millers Ltd: 12 x sourdough", "topic": "orders.received", "record": 2, "parent": "5e2b90c1…", …}
{"level": "WARNING", "message": "notified orders.large: Large order from Millers Ltd: check flour stock", "topic": "orders.large", "notification_level": "warning", "parent": "5e2b90c1…", …}
{"level": "INFO", "message": "execute() completed in 0.2ms", "call": "5e2b90c1…", "parent": null, "state": "completed", …}
```
