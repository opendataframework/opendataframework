"""Notifications: components reacting to what other components report.

TakeOrders, a @Task and a @Publisher, saves the orders waiting in the Inbox
and publishes orders.received for each — and orders.large, a warning, for a
big one — without knowing who listens. Kitchen, a @Subscriber, reacts by
calling an injected @Function; OrderCounter, a background @Subscriber,
counts everything under orders.* on a thread of its own. main.py plays the
UI: it prints a toast for every notification with a summary, then the trace
of the publishing call, which reaches the reactions through the
notifications. Run from this directory: `python main.py`.
"""

from app.subscribers import Kitchen, OrderCounter

from opendataframework import Event, Notification, Project

project = Project.from_config("config.toml")

toasts: list[Notification] = []
project.context.notifications.subscribe(
    lambda n: toasts.append(n) if n.summary is not None else None
)
started: list[Event] = []
project.context.events.subscribe(lambda e: started.append(e) if e.state == "started" else None)

project.start()
taken = project.context.execute("task.take-orders")
kitchen = project.context.get(Kitchen)
counter = project.context.get(OrderCounter)
print("Subscribers:")
for s in project.context.subscribers():
    print(f"  {s['key']} <- {', '.join(s['topics'])} ({s['deliver']})")
project.stop()  # drains OrderCounter's queue before it stops

print(f"\nexecute('task.take-orders') took {taken} orders\n")

print("Toasts (what a UI would show):")
for n in toasts:
    print(f"  [{n.level:<7}] {n.summary}   ({n.topic}, {n.subject} #{n.record})")

print("\nKitchen's bakes:")
for _, bake in kitchen.bakes:
    print(f"  {bake}")

print("\nOrderCounter (topic='orders.*', background):")
for topic, count in sorted(counter.counts.items()):
    print(f"  {topic} x{count}")


def show(node: dict, indent: str = "  ") -> None:
    """Print one trace node, its notifications and what they triggered, then its children."""
    caused = "  [caused by the notification]" if node["cause"] else ""
    print(f"{indent}{node['key']} {node['method']}() {node['state']}{caused}")
    for n in node["notifications"]:
        print(f"{indent}  -> notified {n['topic']}")
        for reaction in sorted(n["triggered"], key=lambda r: r["key"]):
            show(reaction, indent + "       ")
    for child in node["children"]:
        show(child, indent + "  ")


(execute,) = (e for e in started if e.key == "task.take-orders")
print("\nTrace of the execute() call, from the logs:")
show(project.context.trace(execute.call_id))
