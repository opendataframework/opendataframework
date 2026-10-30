"""Notifications: components reacting to what other components report.

TakeOrders, a @Task, saves the orders waiting in the Inbox and publishes
orders.received for each — and orders.large, a warning, for a big one —
without knowing who listens. Kitchen reacts by calling an injected
@Function, OrderCounter counts everything under orders.*, and main.py
plays the UI: it prints a toast for every notification with a summary.
Run from this directory: `python main.py`.
"""

from app.listeners import Kitchen, OrderCounter

from opendataframework import Event, Notification, Project

project = Project.from_config("config.toml")

toasts: list[Notification] = []
project.context.notifications.subscribe(
    lambda n: toasts.append(n) if n.summary is not None else None
)
calls: dict[str, Event] = {}  # call_id → its started event, to name a parent
project.context.events.subscribe(
    lambda e: calls.setdefault(e.call_id, e) if e.state == "started" else None
)

project.start()
taken = project.context.execute("task.take-orders")
kitchen = project.context.get(Kitchen)
counter = project.context.get(OrderCounter)
project.stop()


def call_name(call_id: str | None) -> str:
    if call_id is None:
        return "none (top-level)"
    call = calls[call_id]
    return f"{call.key} {call.method}()"


print(f"execute('task.take-orders') took {taken} orders\n")

print("Toasts (what a UI would show):")
for n in toasts:
    print(f"  [{n.level:<7}] {n.summary}   ({n.topic}, {n.subject} #{n.record})")

print("\nKitchen's reactions:")
bake_calls = [e for e in calls.values() if e.key == "function.schedule-bake"]
for (n, bake), bake_call in zip(kitchen.bakes, bake_calls, strict=True):
    print(f"  {bake}")
    print(f"    notification published during: {call_name(n.parent)}")
    print(f"    schedule_bake() call's parent: {call_name(bake_call.parent)}")

print("\nOrderCounter (topic='orders.*'):")
for topic, count in counter.counts.items():
    print(f"  {topic} x{count}")
