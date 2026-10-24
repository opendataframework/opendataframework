"""Events: reacting to the protocol calls the framework makes.

Three components declare `events: Events` and subscribe in their
constructor: CallTrace records every call, FailureAlerts queues failed
ones for the AlertSender @Service to send, and FunctionCalls counts
@Function calls only. NightlyOrders, a @Pipeline, prices the orders (a
@Task calling an injected @Function) and then fails to ship them.
Run from this directory: `python main.py`.
"""

from app.listeners import CallTrace, FunctionCalls
from app.services import AlertSender

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

try:
    project.context.execute("pipeline.nightly-orders")
except ValueError as exc:
    print(f"execute('pipeline.nightly-orders') raised {exc!r}\n")

trace = project.context.get(CallTrace)
function_calls = project.context.get(FunctionCalls)
sender = project.context.get(AlertSender)
project.stop()

print("Call tree:")
for line in trace.tree("pipeline.nightly-orders"):
    print(f"  {line}")

print("\nFunction calls (protocol=FunctionProtocol):")
for key, count in function_calls.counts.items():
    print(f"  {key} x{count}")

print("\nAlerts sent by AlertSender:")
for alert in sender.sent:
    print(f"  {alert}")

print("\nEvery call seen, startup and shutdown included:")
for call in trace.seen():
    print(f"  {call}")
