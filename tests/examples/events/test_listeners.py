import threading

import pytest
from app.listeners import CallTrace, FailureAlerts, FunctionCalls
from app.services import AlertSender

from opendataframework import Events, FunctionProtocol, PipelineProtocol, TaskProtocol

# Deliberately drives a bare Events directly rather than going through
# Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): registration is global
# for the whole pytest process. Events.notify() is what the framework wraps
# each protocol call in, so it stands in for the real calls here.


def nightly_orders(events: Events) -> None:
    """Emit the calls NightlyOrders makes: price (with a function call), then a failing ship."""
    with pytest.raises(ValueError):
        with events.notify("pipeline.nightly-orders", PipelineProtocol, "execute"):
            with events.notify("task.price-orders", TaskProtocol, "execute"):
                with events.notify("function.price", FunctionProtocol, "__call__"):
                    pass
            with events.notify("task.ship-orders", TaskProtocol, "execute"):
                raise ValueError("courier unavailable")


def test_call_trace_prints_the_tree_of_a_call():
    events = Events()
    trace = CallTrace(events)

    nightly_orders(events)

    assert [line.split() for line in trace.tree("pipeline.nightly-orders")] == [
        ["pipeline.nightly-orders", "execute()", "PipelineProtocol", "failed"],
        ["task.price-orders", "execute()", "TaskProtocol", "completed"],
        ["function.price", "__call__()", "FunctionProtocol", "completed"],
        ["task.ship-orders", "execute()", "TaskProtocol", "failed"],
    ]
    assert trace.tree("pipeline.nightly-orders")[2].startswith("    function.price")


def test_call_trace_stops_recording_after_on_stop():
    events = Events()
    trace = CallTrace(events)
    trace.on_stop()

    nightly_orders(events)

    assert trace.seen() == []


def test_failure_alerts_queues_only_failed_calls():
    events = Events()
    alerts = FailureAlerts(events)

    nightly_orders(events)

    queued = [alerts.queue.get_nowait() for _ in range(alerts.queue.qsize())]
    assert [(e.key, e.state) for e in queued] == [
        ("task.ship-orders", "failed"),
        ("pipeline.nightly-orders", "failed"),
    ]


def test_function_calls_counts_only_function_calls():
    events = Events()
    function_calls = FunctionCalls(events)

    nightly_orders(events)

    assert function_calls.counts == {"function.price": 1}


def test_alert_sender_sends_what_was_queued_before_stopping():
    events = Events()
    alerts = FailureAlerts(events)
    sender = AlertSender(alerts)
    sender.setup()
    thread = threading.Thread(target=sender.run)
    thread.start()

    nightly_orders(events)
    sender.stop()
    thread.join(timeout=1)

    assert sender.sent == [
        "task.ship-orders execute() failed: ValueError('courier unavailable')",
        "pipeline.nightly-orders execute() failed: ValueError('courier unavailable')",
    ]
