# Notifications

`Notifications` lets a component announce that something happened (a file
arrived, a sensor crossed a threshold, a training run finished, an order came
in) so that others can react without the publisher knowing who they are. Another
component might draft an order change, and a UI might show a toast. Each
message is a `Notification`: a topic, a payload, and an optional
human-readable summary.

`Notifications` is the hub, one per `Context`. A component declared a
`@Publisher` publishes; a component declared a `@Subscriber` reacts, and
the framework subscribes it while it runs and traces every reaction back to
the notification that caused it.

```python
@Publisher("messages.received")
@Service
class Mailbox: ...  # publishes, from run()


@Subscriber("messages.received", deliver="background")
@Component
class Drafting:
    def on_notification(self, notification: Notification) -> None: ...
```

---

## Events or Notifications?

They look alike, and they are deliberately separate.

| | [`Event`](events.md) | `Notification` |
|---|---|---|
| What it is | A record of a protocol call the framework made: `started` / `completed` / `failed`, with timing | A message a component publishes about something it did or saw, with a topic and a payload |
| Who emits it | Only the framework (`Context`) | Only component code |
| Content | Key, protocol, method, call id, parent, timing, error. Never arguments or results | Topic, payload, an optional summary, level, an optional subject and record |
| Use it to | Observe how the app runs: run state, monitoring, failure alerts | Let others react without the publisher knowing who they are: other components, and people through a UI |
| Not for | Application data | Getting a result back (call the component directly, through DI), or durable messaging across processes (a broker `@Service`) |

In short: an Event is the framework reporting how it runs your code; a
Notification is your code reporting what happened.

They are two hubs with separate subscriptions, `context.events` and
`context.notifications`, and neither delivers the other's type. A
notification records the protocol call in progress when it was published as
its `parent`, so a consumer can relate the two. For example, "published during
`task.take-orders`' `execute()`".

!!! note "`Events.notify()` is unrelated"
    `Events.notify()` is how the framework emits `Event`s around a protocol
    call. It has nothing to do with `Notifications`; to publish one, call
    `notifications.publish()`.

---

## Publishing

Declare the class a `@Publisher` of the topics it publishes, and
`notifications: Notifications` in its constructor (or in a
[Function](function.md)'s signature). Like [Logger](logger.md), it is
special-cased: each consumer receives a view **bound to its own key**, so
`publish()` needs no key:

```python
from opendataframework import Notifications, Publisher, Task


@Publisher("orders.received")
@Task
class TakeOrders:
    def __init__(self, inbox: Inbox, orders: Orders, notifications: Notifications) -> None:
        self.inbox = inbox
        self.orders = orders
        self.notifications = notifications

    def execute(self) -> None:
        for customer, item, quantity in self.inbox.drain():
            order = self.orders.save(Order(None, customer, item, quantity))
            self.notifications.publish(
                "orders.received",
                {"customer": customer, "item": item, "quantity": quantity},
                summary=f"{customer}: {quantity} x {item}",
                subject=Orders,
                record=order.id,
            )
```

`publish()` delivers the notification to every matching subscriber, writes a
record to the publisher's log, and returns the `Notification`. The record's
`message` is `notified <topic>: <summary>`, and it carries `topic`,
`notification_level`, `subject`, `record` and `parent` (the call it was
published during) as fields, but never the `payload` (see
[Log Format](logger.md#log-format)). It is written at the log level matching
the notification's `level`: `info` and `success` as `INFO`, `warning` as
`WARNING`, `error` as `ERROR`. Set `[project.logging] notifications = ...` to
choose which are kept (see [Levels](logger.md#levels)).

| Argument | Meaning |
|---|---|
| `topic` | Dotted name of what happened, e.g. `"orders.received"`. Non-empty, with no `*`. |
| `payload` | Data for subscribers. Keep it JSON-serialisable, so a UI can show it. Its containers are copied and delivered read-only all the way down: nested mappings arrive as read-only mappings, lists and tuples as tuples, sets as frozensets. Other values are passed as they are, never copied. |
| `summary` | One human-readable line. A UI shows only notifications that have one. |
| `level` | `"info"` (the default), `"success"`, `"warning"`, or `"error"`. Anything else raises `ValueError`. |
| `subject` | The component it's about: a class or function, resolved to its key, or a key string such as `"repository.orders"`. |
| `record` | Id of the record it's about, within `subject`. |
| `key` | The publisher's key. Filled in by an injected view; required on `context.notifications`. |

### `@Publisher` and the Publishing Rules

`@Publisher(*topics)` goes on top of the class's execution type
(`@Component`, `@Service`, `@Task`, `@Agent`, ...) or on top of
`@Function`, the way a [layer](layer.md) does. Each topic is exact, or
`"x.*"` to allow every topic under `x`. It has no protocol method: publishing
is started by your own code, at moments only it knows, so the framework has
nothing to call. What it does is make three rules hold for an injected view:

1. **Only a `@Publisher` publishes.** Publishing without one raises
   `TypeError`, so the framework knows every publisher: `context.publishers()`
   lists them, and a UI can draw who publishes what before anything has been
   published.
2. **Only declared topics.** Publishing a topic the `@Publisher` doesn't
   declare raises `ValueError`.
3. **Only inside a protocol call.** Publishing with no call in progress raises
   `RuntimeError`, because the notification would have no `parent` and
   couldn't be traced. Publish from `execute()`, `run()`, `on_start()`,
   `on_notification()`, `invoke()`, a `@Function` call, ... never from
   `__init__` or from a thread you started yourself.

```python
context.publishers()
# [{"key": "task.take-orders", "topics": ["orders.received"]}]
```

`Publisher` is a [namespace](namespace.md), like a [layer](layer.md):
`Publisher.items()` lists every publisher by name, and `Publisher.of(target)`
returns what one declares (or `None`). Nothing is written onto your class or
function, and a subclass of a publisher isn't one. It registers by name, so
a publishing class and a publishing function with the same name clash —
give one a name: `@Publisher("orders.priced", name="price-function")`.

Code that holds the `Context` (a script, a test, the sibling
[`odf`](https://opendataframework.github.io/odf/) package's UI server) uses the
unbound hub, `context.notifications`, and passes the key itself. The unbound
hub is exempt from all three rules:

```python
project.context.notifications.publish("orders.imported", key="task.import-orders")
```

A `subject` given as a class or function is resolved through the `Context`,
so it only works once `open()` has resolved it. Before that, or for a
component the `Context` doesn't know, it raises `KeyError`; pass the key
string instead.

---

## Subscribing

### `@Subscriber`

A component reacts to notifications by declaring itself a `@Subscriber`
and defining `on_notification()` (`SubscriberProtocol`):

```python
from opendataframework import Component, Notification, Subscriber


@Subscriber("orders.received")
@Component
class Kitchen:
    def __init__(self, bakery: Bakery) -> None:
        self.bakery = bakery

    def on_notification(self, notification: Notification) -> None:
        self.bakery.schedule(order_id=notification.record)
```

`@Subscriber(*topics, deliver="sync")` goes on top of the execution type,
like `@Publisher`. Topics are filters, as below; a notification matching
several is delivered once. A class without `on_notification()`, or with an
`async` one, raises `TypeError`.

* **Managed.** The `Context` subscribes `on_notification()` right after the
  component starts (after its `on_start()`, or a service's `setup()`) and
  unsubscribes it right before it stops. A component never receives a
  notification before it started or after it stopped, and a service stopped
  with `context.stop(key)` receives nothing until it starts again. The flip
  side: what was published before the component started — during an
  earlier component's `on_start()`, say — it doesn't see.
* **Instrumented.** Each delivery is a protocol call, reported to
  [Events](events.md) as `SubscriberProtocol` / `on_notification`, written to
  the component's log, and linked to the notification by its `cause` (see
  [Ids and Causes](#ids-and-causes)). If it raises, the call's `failed`
  record says so; the exception never reaches the publisher.
* **Sync or background.** With `deliver="sync"` (the default),
  `on_notification()` runs inside `publish()`, in the publisher's thread. With
  `deliver="background"`, `publish()` only queues the delivery and returns;
  see [Background Delivery](#background-delivery).
* **Visible.** `context.subscribers()` lists every subscriber:

  ```python
  context.subscribers()
  # [{"key": "component.kitchen", "topics": ["orders.received"], "deliver": "sync"}]
  ```

  Like `Publisher`, `Subscriber` is a namespace: `Subscriber.items()` lists
  every subscriber class, and `Subscriber.of(Kitchen)` returns its
  `Subscription(topics, deliver)`. The declaration is kept by the namespace,
  not written onto the class, so a subclass of a subscriber isn't one.

Keep **one reaction per component**. Two reactions to different topics are
two subscribers, each with its own node in a topology, its own delivery
mode and its own trace. What they share (state, a model client, an order
desk) belongs in a plain component they both depend on, not in a
subscriber that branches on `notification.topic`:

```python
@Component
class OrderDesk:
    def draft_change(self, message_id: str) -> None: ...
    def file_invoice(self, invoice_id: str) -> None: ...


@Subscriber("messages.received")
@Component
class MessageDrafter:
    def __init__(self, desk: OrderDesk) -> None:
        self.desk = desk

    def on_notification(self, notification: Notification) -> None:
        self.desk.draft_change(notification.record)


@Subscriber("invoices.*")
@Component
class InvoiceFiler:
    def __init__(self, desk: OrderDesk) -> None:
        self.desk = desk

    def on_notification(self, notification: Notification) -> None:
        self.desk.file_invoice(notification.record)
```

A subscriber that also publishes is a `@Publisher` too; it publishes from
`on_notification()`, which is a protocol call, so the new notification's
`parent` is the reaction and chains continue.

### `subscribe()`

For code outside components, and for dynamic cases, subscribe directly:

```python
unsubscribe = notifications.subscribe(listener)  # every notification
unsubscribe = notifications.subscribe(listener, topic="orders.received")  # exactly this topic
unsubscribe = notifications.subscribe(listener, topic="orders.*")  # by prefix
unsubscribe()  # stop; safe to call twice
```

`"orders.*"` matches `orders.received` and `orders.received.late`, but not
`orders` itself. A `*` anywhere other than a trailing `.*` raises `ValueError`.

A listener subscribed this way isn't managed or instrumented: you
unsubscribe it yourself, and its own run emits no events (the calls it makes
still record the notification as their `cause`). Prefer `@Subscriber` in a
component.

See [`examples/11-notifications/`](examples.md) for a full runnable project
built around this.

---

## The Notification

| Field | Meaning |
|---|---|
| `key` | The publisher's `<namespace>.<name>` key, e.g. `"task.take-orders"`. |
| `topic` | e.g. `"orders.received"`. |
| `payload` | Read-only mapping, frozen recursively (nested lists arrive as tuples); `{}` when none was given. |
| `summary` | One human-readable line, or `None`. |
| `level` | `"info"`, `"success"`, `"warning"`, or `"error"`. |
| `subject` | Key of the component it's about, or `None`. |
| `record` | Id of the record it's about, or `None`. |
| `parent` | `call_id` of the protocol call in progress when it was published (see [How `parent` Nests](events.md#how-parent-nests)), or `None`. |
| `ts` | `time.time()` when it was published. |
| `id` | Unique per publish (`uuid4().hex`). Logged as the record's `notification`; see [Ids and Causes](#ids-and-causes). |

---

## Delivery

Delivery follows the same contract as [Events](events.md#listeners-run-inline):

* **Synchronous, unless declared background.** Every `subscribe()` listener,
  and every `@Subscriber` with the default `deliver="sync"`, runs inside
  `publish()`, in the publisher's thread, before `publish()` returns. A slow
  one holds up the publisher — a webhook handler, a mailbox poll — so declare
  it `deliver="background"` (below).
* **Thread-safe listeners.** Publishers can be on several threads (a
  service's `run()`, a stream), so listeners can be called from several
  threads.
* **Exceptions are contained.** If a listener raises, the exception never
  reaches the publisher or other listeners. A `@Subscriber`'s failure is its
  `on_notification()` call's `failed` record. A `subscribe()` listener's is
  logged as a `WARNING` (`listener of <topic> raised ...`), on the
  subscriber's key when it subscribed through an injected view, and on the
  publisher's key when it subscribed through `context.notifications`.
* **Listeners run with no current call.** A `@Subscriber`'s
  `on_notification()`, or the first call a `subscribe()` listener makes, is
  top-level (`parent=None`), not a child of the publisher's call. The
  reaction is linked to what caused it through its `cause`, the
  notification's `id` — see [Ids and Causes](#ids-and-causes).
* **A reaction may publish.** A `@Subscriber` that is also a `@Publisher`
  publishes from `on_notification()`. That publish is delivered right away,
  before the outer `publish()` moves on to its next listener. A
  `subscribe()` listener isn't inside a call, so it can publish only
  through the unbound `context.notifications`. Don't publish a topic you
  subscribe to.

### Background Delivery

A reaction that calls a model or an external API shouldn't block whatever
published. Declare it background:

```python
@Subscriber("messages.received", deliver="background")
@Component
class Drafting:
    def __init__(self, order_desk: OrderDesk) -> None:
        self.order_desk = order_desk

    def on_notification(self, notification: Notification) -> None:
        self.order_desk.invoke(message_id=notification.record)  # tens of seconds
```

* Each background subscriber has **its own worker thread and queue**,
  started when the component starts and stopped when it stops. `publish()`
  queues the delivery and returns.
* **Publish order is kept** per subscriber. A slow subscriber holds up only
  itself: a burst of invoices for one never delays another's messages.
* The delivery is the same instrumented `on_notification()` call, with the
  same `cause`, so traces look the same as for a sync subscriber.
* **The queue is bounded.** When it is full, `publish()` blocks until there
  is room — backpressure, never a silent drop — and the subscriber logs one
  `WARNING` per full episode.
* **Stopping drains.** Before the component's `on_stop()` (or a service's
  `stop()`), the `Context` stops queuing, waits for the queue to drain up to
  `drain-timeout`, and logs a `WARNING` with how many deliveries it dropped
  if it couldn't.

Both are set under `[project.notifications]`:

```toml
[project.notifications]
queue-size = 1000     # each background subscriber's queue bound
drain-timeout = 10    # seconds stopping one waits for its queue to drain
```

---

## Ids and Causes

Every notification has an `id`, so it can be referred to: a UI can
deduplicate a stream after reconnecting, and a trace can follow it.

While a listener runs, the notification is its *cause*. The first protocol
call the listener makes — a `@Function`, an agent's `invoke()`, a task's
`execute()` — records the notification's `id` as its
[`cause`](events.md#the-event), with `parent=None`. Calls nested inside it
have a `parent` as usual, so the cause marks the top of the reaction only.

`context.trace()` follows that link. A notification in a node's
`notifications` lists, under `triggered`, the subtrees of the calls whose
`cause` is its `id` — so the trace of the call that published "a message
arrived" reaches "an agent drafted an order change", across files:

```python
{"key": "task.take-orders", ...,
 "notifications": [
     {"id": "9b1f…", "topic": "orders.received", ...,
      "triggered": [{"key": "function.schedule", "cause": "9b1f…", "parent": None,
                     "children": [...], ...}]}],
 "children": []}
```

A notification published inside a reaction has that reaction's call as its
`parent`, so chains continue: message, draft, notification, reply.

For a long-running [Service](service.md) — a mailbox poller, a webhook
receiver — publish from a `@Function` called once per inbound item, not
inline in `run()`, so each item gets a trace of its own: see
[One Call per Inbound Item](service.md#one-call-per-inbound-item).

---

## When Not to Use It

* **To get a result back.** If the publisher needs an answer, it should
  declare the other component as a dependency and call it. A notification
  doesn't return anything to its publisher.
* **For durable or cross-process messaging.** Nothing is stored, retried, or
  sent beyond the process. A subscriber that isn't subscribed yet misses the
  message. For that, put a broker behind a `@Service`.
* **To observe the framework.** Use [Events](events.md) for run state,
  timings, and failures.

`Notifications` is per `Context` too: two `Project`s in one process never see
each other's notifications.
