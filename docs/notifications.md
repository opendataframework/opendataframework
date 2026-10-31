# Notifications

`Notifications` lets a component announce that something happened (a file
arrived, a sensor crossed a threshold, a training run finished, an order came
in) so that others can react without the publisher knowing who they are. Another
component might draft an order change, and a UI might show a toast. Each
message is a `Notification`: a topic, a payload, and an optional
human-readable summary.

`Notifications` is the hub, one per `Context`. A component publishes; any
callable that takes a `Notification` can subscribe.

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

Declare `notifications: Notifications` in a constructor, or in a
[Function](function.md)'s signature. Like [Logger](logger.md), it is
special-cased: each consumer receives a view **bound to its own key**, so
`publish()` needs no key:

```python
from opendataframework import Notifications, Task


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

`publish()` delivers the notification to every matching subscriber, writes
`notified <topic>: <summary> [parent=...]` to the publisher's log, and returns
the `Notification`. The line is written at the log level matching the
notification's `level` (`info` and `success` as `INFO`, `warning` as `WARNING`,
`error` as `ERROR`), and `parent` is the call it was published during. Set
`[project.logging] notifications = ...` to choose which are kept (see
[Levels](logger.md#levels)).

| Argument | Meaning |
|---|---|
| `topic` | Dotted name of what happened, e.g. `"orders.received"`. Non-empty, with no `*`. |
| `payload` | Data for subscribers. Keep it JSON-serialisable, so a UI can show it. Copied, and delivered read-only. |
| `summary` | One human-readable line. A UI shows only notifications that have one. |
| `level` | `"info"` (the default), `"success"`, `"warning"`, or `"error"`. Anything else raises `ValueError`. |
| `subject` | The component it's about: a class or function, resolved to its key, or a key string such as `"repository.orders"`. |
| `record` | Id of the record it's about, within `subject`. |
| `key` | The publisher's key. Filled in by an injected view; required on `context.notifications`. |

Code that holds the `Context` (a script, a test, the sibling
[`odf`](https://opendataframework.github.io/odf/) package's UI server) uses the
unbound hub, `context.notifications`, and passes the key itself:

```python
project.context.notifications.publish("orders.imported", key="task.import-orders")
```

A `subject` given as a class or function is resolved through the `Context`,
so it only works once `open()` has resolved it. Before that, or for a
component the `Context` doesn't know, it raises `KeyError`; pass the key
string instead.

---

## Subscribing

```python
unsubscribe = notifications.subscribe(listener)  # every notification
unsubscribe = notifications.subscribe(listener, topic="orders.received")  # exactly this topic
unsubscribe = notifications.subscribe(listener, topic="orders.*")  # by prefix
unsubscribe()  # stop; safe to call twice
```

`"orders.*"` matches `orders.received` and `orders.received.late`, but not
`orders` itself. A `*` anywhere other than a trailing `.*` raises `ValueError`.

A component subscribes in its constructor, through the same injected view,
and unsubscribes in `on_stop()`:

```python
from collections.abc import Callable
from typing import Annotated

from opendataframework import Component, Notification, Notifications


@Component
class Kitchen:
    def __init__(
        self,
        notifications: Notifications,
        schedule: Annotated[Callable[..., str], schedule_bake],
    ) -> None:
        self.schedule = schedule
        self._unsubscribe = notifications.subscribe(self.on_order, topic="orders.received")

    def on_order(self, notification: Notification) -> None:
        self.schedule(order_id=notification.record)

    def on_stop(self) -> None:
        self._unsubscribe()
```

See [`examples/11-notifications/`](examples.md) for a full runnable project
built around this.

---

## The Notification

| Field | Meaning |
|---|---|
| `key` | The publisher's `<namespace>.<name>` key, e.g. `"task.take-orders"`. |
| `topic` | e.g. `"orders.received"`. |
| `payload` | Read-only mapping; `{}` when none was given. |
| `summary` | One human-readable line, or `None`. |
| `level` | `"info"`, `"success"`, `"warning"`, or `"error"`. |
| `subject` | Key of the component it's about, or `None`. |
| `record` | Id of the record it's about, or `None`. |
| `parent` | `call_id` of the protocol call in progress when it was published (see [How `parent` Nests](events.md#how-parent-nests)), or `None`. |
| `ts` | `time.time()` when it was published. |

---

## Delivery

Delivery follows the same contract as [Events](events.md#listeners-run-inline):

* **Synchronous.** Every listener runs inside `publish()`, in the
  publisher's thread, before `publish()` returns. A slow listener holds up
  the publisher, so hand slow work to a queue drained by a
  [Service](service.md).
* **Thread-safe listeners.** Publishers can be on several threads (a
  service's `run()`, a stream), so listeners can be called from several
  threads.
* **Exceptions are contained.** If a listener raises, the exception is logged
  as a `WARNING` (`listener of <topic> raised ...`) and never reaches the
  publisher or other listeners. It is logged on the subscriber's key when the
  listener subscribed through an injected view, and on the publisher's key
  when it subscribed through `context.notifications`.
* **Listeners run with no current call.** A call a listener makes, like
  `Kitchen`'s `schedule()` above, is top-level (`parent=None`), not a child of
  the publisher's call. The reaction is linked to what caused it through
  the notification's own `parent`, not through nesting.
* **A listener may publish.** That publish is delivered right away, before
  the outer `publish()` moves on to its next listener. Don't have a listener
  publish a topic it subscribes to.

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
