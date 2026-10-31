import re
import threading
import time
from collections.abc import Callable
from typing import Annotated

import pytest

from opendataframework.agent import Agent, AgentProtocol
from opendataframework.component import Component, OnStartProtocol, OnStopProtocol
from opendataframework.context import Context
from opendataframework.events import Event, Events, build_trace
from opendataframework.function import Function, FunctionProtocol
from opendataframework.namespace import Namespace
from opendataframework.notifications import Notifications
from opendataframework.pipeline import Pipeline, PipelineProtocol
from opendataframework.repository import (
    CloseStreamProtocol,
    OpenStreamProtocol,
    StreamableProtocol,
)
from opendataframework.service import ServiceProtocol
from opendataframework.task import Task, TaskProtocol

# --- helpers -----------------------------------------------------------------


def make_ns():
    """Return a fresh isolated Namespace subclass for each test."""

    class Scope(Namespace): ...

    return Scope


def collect(ctx: Context, protocol: type | None = None) -> list[Event]:
    """Subscribe a list to ``ctx``'s events and return it."""
    events: list[Event] = []
    ctx.events.subscribe(events.append, protocol)
    return events


def calls(events: list[Event]) -> list[tuple[str, str, str]]:
    """Reduce events to ``(key, method, state)`` for order assertions."""
    return [(e.key, e.method, e.state) for e in events]


def wait_for(condition: Callable[[], bool]) -> None:
    """Poll ``condition`` until it holds, failing after about a second."""
    for _ in range(100):
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met")


# --- execution protocols -----------------------------------------------------


def test_task_execute_emits_started_then_completed():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> int:
            return 42

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert ctx.execute("scope.t") == 42

    started, completed = events
    assert (started.protocol, started.method, started.state) == (TaskProtocol, "execute", "started")
    assert completed.state == "completed"
    assert started.call_id == completed.call_id
    assert started.parent is None and completed.parent is None
    assert started.elapsed_ms is None
    assert completed.elapsed_ms is not None and completed.elapsed_ms >= 0
    assert completed.error is None


def test_raising_task_emits_failed_and_still_raises():
    NS = make_ns()
    error = ValueError("nope")

    @NS
    @Task
    class T:
        def execute(self) -> None:
            raise error

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        with pytest.raises(ValueError, match="nope"):
            ctx.execute("scope.t")

    assert [e.state for e in events] == ["started", "failed"]
    assert events[1].error == repr(error)
    assert events[1].elapsed_ms is not None


def test_pipeline_steps_are_children_of_the_pipeline():
    NS = make_ns()

    @NS
    @Task
    class StepOne:
        def execute(self) -> None: ...

    @NS
    @Task
    class StepTwo:
        def execute(self) -> None: ...

    @NS
    @Pipeline
    class Flow:
        def __init__(self, one: StepOne, two: StepTwo) -> None:
            self.one = one
            self.two = two

        def execute(self) -> None:
            self.one.execute()
            self.two.execute()

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        ctx.execute("scope.flow")

    assert calls(events) == [
        ("scope.flow", "execute", "started"),
        ("scope.step-one", "execute", "started"),
        ("scope.step-one", "execute", "completed"),
        ("scope.step-two", "execute", "started"),
        ("scope.step-two", "execute", "completed"),
        ("scope.flow", "execute", "completed"),
    ]
    flow = events[0]
    assert flow.protocol is PipelineProtocol
    assert all(e.protocol is TaskProtocol for e in events[1:5])
    assert all(e.parent == flow.call_id for e in events[1:5])


def test_function_injected_into_a_task_is_a_child_call():
    NS = make_ns()

    @NS
    @Function
    def load_data(path: str) -> int:
        return len(path)

    @NS
    @Task
    class DailyImport:
        def __init__(self, load: Annotated[Callable[..., int], load_data]) -> None:
            self.load = load

        def execute(self) -> int:
            return self.load("data.csv")

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert ctx.execute("scope.daily-import") == 8

    task, call, called, done = events
    assert (call.protocol, call.method, call.key) == (
        FunctionProtocol,
        "__call__",
        "scope.load-data",
    )
    assert call.parent == task.call_id
    assert called.call_id == call.call_id and called.state == "completed"
    assert done.state == "completed"


def test_function_filter_receives_only_function_calls():
    NS = make_ns()

    @NS
    @Function
    def load_data(path: str) -> int:
        return len(path)

    @NS
    @Task
    class DailyImport:
        def __init__(self, load: Annotated[Callable[..., int], load_data]) -> None:
            self.load = load

        def execute(self) -> int:
            return self.load("data.csv")

    @NS
    @Component
    class SlowCalls:
        def __init__(self, events: Events) -> None:
            self.seen: list[Event] = []
            self._unsubscribe = events.subscribe(self.seen.append, protocol=FunctionProtocol)

    with Context(namespaces={NS}) as ctx:
        ctx.execute("scope.daily-import")
        seen = ctx.get(SlowCalls).seen

    assert [(e.key, e.state) for e in seen] == [
        ("scope.load-data", "started"),
        ("scope.load-data", "completed"),
    ]


def test_function_called_through_the_context_is_top_level():
    NS = make_ns()

    @NS
    @Function
    def load_data(path: str) -> int:
        return len(path)

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert ctx.call("scope.load-data", path="abc") == 3
        assert ctx.get(load_data)("abcd") == 4

    assert [e.protocol for e in events] == [FunctionProtocol] * 4
    assert all(e.parent is None for e in events)


def test_direct_function_call_emits_nothing():
    NS = make_ns()

    @NS
    @Function
    def load_data(path: str) -> int:
        return len(path)

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert load_data("abc") == 3

    assert events == []


def test_agent_invoke_emits_invoke_events():
    NS = make_ns()

    @NS
    @Agent
    class Archivist:
        def invoke(self, question: str) -> str:
            return question.upper()

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert ctx.call("scope.archivist", question="dune?") == "DUNE?"

    assert [(e.protocol, e.method, e.state) for e in events] == [
        (AgentProtocol, "invoke", "started"),
        (AgentProtocol, "invoke", "completed"),
    ]


# --- lifecycle protocols -----------------------------------------------------


def test_service_lifecycle_emits_setup_run_and_stop():
    NS = make_ns()
    running = threading.Event()

    @NS
    class Svc:
        def setup(self) -> None: ...

        def run(self) -> None:
            running.set()

        def stop(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx, protocol=ServiceProtocol)
    with ctx:
        assert running.wait(timeout=1)
        wait_for(lambda: ("scope.svc", "run", "completed") in calls(events))
        assert calls(events)[:2] == [
            ("scope.svc", "setup", "started"),
            ("scope.svc", "setup", "completed"),
        ]
        run = next(e for e in events if e.method == "run")
        assert run.parent is None

    assert calls(events)[-2:] == [
        ("scope.svc", "stop", "started"),
        ("scope.svc", "stop", "completed"),
    ]


def test_service_run_started_from_a_task_is_still_top_level():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    with Context(namespaces={NS}) as ctx:
        ctx.stop("scope.svc")
        events = collect(ctx)
        # Start the service from inside a protocol call, as a task calling
        # context.start() would, so setup() has a parent to inherit.
        with ctx.events.notify("scope.starter", TaskProtocol, "execute"):
            ctx.start("scope.svc")
        wait_for(lambda: any(e.method == "run" for e in events))

    outer = events[0]
    setup = next(e for e in events if e.method == "setup")
    run = next(e for e in events if e.method == "run")
    assert setup.parent == outer.call_id
    assert run.parent is None


def test_service_run_raising_emits_failed():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...

        def run(self) -> None:
            raise RuntimeError("boom")

        def stop(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        wait_for(lambda: any(e.method == "run" and e.state == "failed" for e in events))

    failed = next(e for e in events if e.method == "run" and e.state == "failed")
    assert failed.error == repr(RuntimeError("boom"))


def test_stop_by_key_emits_stop_events():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    with Context(namespaces={NS}) as ctx:
        events = collect(ctx)
        ctx.stop("scope.svc")
        assert calls(events) == [
            ("scope.svc", "stop", "started"),
            ("scope.svc", "stop", "completed"),
        ]


def test_setup_raising_emits_failed_and_open_raises():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None:
            raise RuntimeError("no db")

        def run(self) -> None: ...
        def stop(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with pytest.raises(RuntimeError, match="no db"):
        ctx.open()

    assert calls(events) == [("scope.svc", "setup", "started"), ("scope.svc", "setup", "failed")]
    assert ctx.is_running("scope.svc") is False


def test_on_start_and_on_stop_hooks_emit_events():
    NS = make_ns()

    @NS
    class Users:
        def on_start(self) -> None: ...
        def on_stop(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert [(e.protocol, e.method, e.state) for e in events] == [
            (OnStartProtocol, "on_start", "started"),
            (OnStartProtocol, "on_start", "completed"),
        ]

    assert [(e.protocol, e.method, e.state) for e in events[2:]] == [
        (OnStopProtocol, "on_stop", "started"),
        (OnStopProtocol, "on_stop", "completed"),
    ]


def test_on_start_raising_emits_failed_and_open_raises():
    NS = make_ns()

    @NS
    class Users:
        def on_start(self) -> None:
            raise RuntimeError("cache")

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with pytest.raises(RuntimeError, match="cache"):
        ctx.open()

    assert calls(events) == [
        ("scope.users", "on_start", "started"),
        ("scope.users", "on_start", "failed"),
    ]


def test_instance_without_hooks_emits_nothing():
    NS = make_ns()

    @NS
    class Plain: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        pass

    assert events == []


# --- stream protocols --------------------------------------------------------


def test_stream_emits_open_stream_stream_and_close_stream():
    NS = make_ns()

    @NS
    class Device:
        def open_stream(self) -> None: ...
        def close_stream(self) -> None: ...

        def stream(self):
            yield 1  # a finite source, so the stream completes on its own

    with Context(namespaces={NS}) as ctx:
        events = collect(ctx)
        ctx.start_stream("scope.device")
        wait_for(lambda: ("scope.device", "close_stream", "completed") in calls(events))

    assert [(e.protocol, e.method, e.state) for e in events] == [
        (OpenStreamProtocol, "open_stream", "started"),
        (OpenStreamProtocol, "open_stream", "completed"),
        (StreamableProtocol, "stream", "started"),
        (StreamableProtocol, "stream", "completed"),
        (CloseStreamProtocol, "close_stream", "started"),
        (CloseStreamProtocol, "close_stream", "completed"),
    ]
    stream = events[2]
    assert stream.parent is None


def test_raising_stream_emits_failed_and_is_still_swallowed():
    NS = make_ns()

    @NS
    class Device:
        def stream(self):
            raise RuntimeError("unplugged")
            yield  # pragma: no cover

    with Context(namespaces={NS}) as ctx:
        events = collect(ctx)
        ctx.start_stream("scope.device")
        wait_for(lambda: any(e.state == "failed" for e in events))
        wait_for(lambda: not ctx.is_streaming("scope.device"))

    assert calls(events) == [
        ("scope.device", "stream", "started"),
        ("scope.device", "stream", "failed"),
    ]
    assert events[1].error == repr(RuntimeError("unplugged"))


def test_raising_close_stream_emits_failed_and_is_still_swallowed():
    NS = make_ns()

    @NS
    class Device:
        def close_stream(self) -> None:
            raise RuntimeError("stuck")

        def stream(self):
            yield 1

    with Context(namespaces={NS}) as ctx:
        events = collect(ctx, protocol=CloseStreamProtocol)
        ctx.start_stream("scope.device")
        wait_for(lambda: any(e.state == "failed" for e in events))

    assert [e.state for e in events] == ["started", "failed"]


# --- subscription ------------------------------------------------------------


def test_protocol_filter_is_an_exact_match():
    NS = make_ns()

    @NS
    @Task
    class Step:
        def execute(self) -> None: ...

    @NS
    @Pipeline
    class Flow:
        def __init__(self, step: Step) -> None:
            self.step = step

        def execute(self) -> None:
            self.step.execute()

    ctx = Context(namespaces={NS})
    tasks = collect(ctx, protocol=TaskProtocol)
    services = collect(ctx, protocol=ServiceProtocol)
    with ctx:
        ctx.execute("scope.flow")

    assert {e.key for e in tasks} == {"scope.step"}
    assert services == []


def test_events_is_injected_as_the_contexts_own_instance():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    @NS
    @Component
    class Watcher:
        # Every __init__ runs before any setup(), so subscribing here catches Svc's.
        def __init__(self, events: Events) -> None:
            self.events = events
            self.seen: list[Event] = []
            events.subscribe(self.seen.append, protocol=ServiceProtocol)

    with Context(namespaces={NS}) as ctx:
        watcher = ctx.get(Watcher)
        assert watcher.events is ctx.events
        assert ("scope.svc", "setup", "completed") in calls(watcher.seen)


def test_subscribing_before_open_sees_startup():
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        assert calls(events)[:2] == [
            ("scope.svc", "setup", "started"),
            ("scope.svc", "setup", "completed"),
        ]


def test_call_started_by_a_listener_is_top_level():
    NS = make_ns()

    @NS
    @Task
    class Load:
        def execute(self) -> None:
            raise ValueError("empty")

    @NS
    @Task
    class Cleanup:
        def execute(self) -> None: ...

    ctx = Context(namespaces={NS})
    events = collect(ctx)

    def on_event(event: Event) -> None:
        if event.key == "scope.load" and event.state == "failed":
            ctx.execute("scope.cleanup")

    ctx.events.subscribe(on_event)
    with ctx:
        with pytest.raises(ValueError, match="empty"):
            ctx.execute("scope.load")

    cleanup = [e for e in events if e.key == "scope.cleanup"]
    assert [e.state for e in cleanup] == ["started", "completed"]
    assert all(e.parent is None for e in cleanup)


def test_raising_listener_does_not_affect_the_call_or_other_listeners(tmp_path):
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> int:
            return 42

    def broken(event: Event) -> None:
        raise RuntimeError("listener bug")

    ctx = Context(namespaces={NS}, log_dir=tmp_path)
    ctx.events.subscribe(broken)
    events = collect(ctx)
    with ctx:
        assert ctx.execute("scope.t") == 42
        messages = [(e["level"], e["message"]) for e in ctx.tail_logs("scope.t")]

    assert [e.state for e in events] == ["started", "completed"]
    assert ("WARNING", "listener raised RuntimeError('listener bug')") in messages


def test_unsubscribe_stops_delivery_and_is_idempotent():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None: ...

    ctx = Context(namespaces={NS})
    events: list[Event] = []
    unsubscribe = ctx.events.subscribe(events.append)
    with ctx:
        ctx.execute("scope.t")
        unsubscribe()
        unsubscribe()
        ctx.execute("scope.t")

    assert len(events) == 2


def test_match_style_listener_from_the_docs():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None:
            raise ValueError("bad")

    failures: list[str] = []

    def on_event(event: Event) -> None:
        # A bare name in a pattern captures instead of comparing, so the
        # protocol is checked in a guard.
        match event:
            case Event(state="failed", key=key) if event.protocol is TaskProtocol:
                failures.append(key)
            case _:
                pass

    ctx = Context(namespaces={NS})
    ctx.events.subscribe(on_event)
    with ctx:
        with pytest.raises(ValueError):
            ctx.execute("scope.t")

    assert failures == ["scope.t"]


# --- log records -------------------------------------------------------------


def records(ctx: Context, key: str) -> list[dict]:
    """Return the event records in ``key``'s log."""
    return [r for r in ctx.tail_logs(key) if r.get("source") == "events"]


def chain(NS):
    """Register a pipeline → task → function chain; the function fails if asked to."""

    @NS
    @Function
    def fetch(fail: bool = False) -> int:
        if fail:
            raise ValueError("nope")
        return 1

    @NS
    @Task
    class Load:
        def __init__(self, fetch: Annotated[Callable[..., int], fetch]) -> None:
            self.fetch = fetch
            self.fail = False

        def execute(self) -> int:
            return self.fetch(fail=self.fail)

    @NS
    @Pipeline
    class Nightly:
        def __init__(self, load: Load) -> None:
            self.load = load

        def execute(self) -> int:
            return self.load.execute()

    return Load


def test_every_event_record_carries_the_events_fields(tmp_path):
    NS = make_ns()
    chain(NS)
    ctx = Context(namespaces={NS}, log_dir=tmp_path)
    events = collect(ctx)
    with ctx:
        ctx.execute("scope.nightly")

    for key in ("scope.nightly", "scope.load", "scope.fetch"):
        started, completed = (e for e in events if e.key == key)
        first, second = records(ctx, key)
        for record, event in ((first, started), (second, completed)):
            assert record["call"] == event.call_id
            assert record["parent"] == event.parent
            assert record["protocol"] == event.protocol.__name__
            assert record["method"] == event.method
            assert record["state"] == event.state
            assert (record["key"], record["namespace"]) == (key, "scope")
        assert "elapsed_ms" not in first and "error" not in first
        assert second["elapsed_ms"] >= 0 and "error" not in second
        assert first["message"] in ("execute() started", "call started")
        assert second["message"].startswith(("execute() completed in ", "call completed in "))


def test_a_childs_parent_is_its_callers_call_across_files(tmp_path):
    NS = make_ns()
    chain(NS)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.nightly")
        nightly, _ = records(ctx, "scope.nightly")
        load, _ = records(ctx, "scope.load")
        fetch, _ = records(ctx, "scope.fetch")

    assert nightly["parent"] is None
    assert load["parent"] == nightly["call"]
    assert fetch["parent"] == load["call"]


def test_failed_record_is_an_error_and_keeps_its_parent_when_others_are_filtered(tmp_path):
    NS = make_ns()
    Load = chain(NS)
    with Context(namespaces={NS}, log_dir=tmp_path, log_config={"events": "WARNING"}) as ctx:
        ctx.get(Load).fail = True
        with pytest.raises(ValueError):
            ctx.execute("scope.nightly")
        (load,) = records(ctx, "scope.load")
        (fetch,) = records(ctx, "scope.fetch")

    assert fetch["level"] == "ERROR"
    assert fetch["state"] == "failed"
    assert fetch["error"] == "ValueError('nope')"
    assert fetch["message"].startswith("call failed in ")
    assert fetch["message"].endswith(": ValueError('nope')")
    assert fetch["parent"] == load["call"]


def test_text_format_appends_shortened_ids(tmp_path):
    NS = make_ns()
    chain(NS)
    config = {"format": "text"}
    with Context(namespaces={NS}, log_dir=tmp_path, log_config=config) as ctx:
        ctx.execute("scope.nightly")
        nightly = ctx.tail_logs("scope.nightly")
        load = ctx.tail_logs("scope.load")

    call = re.search(r"\[call=(\w{8}) parent=-\]$", nightly[-1]["message"])[1]
    assert load[-1]["message"].endswith(f"parent={call}]")
    assert (tmp_path / "scope.nightly.log").exists()


def test_listener_exception_is_logged_whatever_the_events_level(tmp_path):
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None: ...

    ctx = Context(namespaces={NS}, log_dir=tmp_path, log_config={"events": "ERROR"})

    def broken(event: Event) -> None:
        raise RuntimeError("listener bug")

    ctx.events.subscribe(broken)
    with ctx:
        ctx.execute("scope.t")
        logged = ctx.tail_logs("scope.t")
    assert "listener raised RuntimeError('listener bug')" in [r["message"] for r in logged]
    assert records(ctx, "scope.t") == []


# --- traces ------------------------------------------------------------------


def shape(node: dict) -> tuple:
    """Reduce a trace node to ``(key, state, [children...])`` for assertions."""
    return (node["key"], node["state"], [shape(child) for child in node["children"]])


def test_trace_from_logs_is_the_call_tree(tmp_path):
    NS = make_ns()
    chain(NS)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.nightly")
        (nightly, _) = records(ctx, "scope.nightly")
        trace = ctx.trace(nightly["call"])

    assert shape(trace) == (
        "scope.nightly",
        "completed",
        [("scope.load", "completed", [("scope.fetch", "completed", [])])],
    )
    assert trace["parent"] is None
    assert trace["protocol"] == "PipelineProtocol"
    assert trace["started"] <= trace["ended"]
    assert trace["elapsed_ms"] >= 0


def test_trace_works_after_close_and_by_prefix(tmp_path):
    NS = make_ns()
    chain(NS)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.nightly")
        (nightly, _) = records(ctx, "scope.nightly")
    assert ctx.trace(nightly["call"][:8])["call"] == nightly["call"]


def test_trace_from_a_child_is_its_subtree(tmp_path):
    NS = make_ns()
    chain(NS)
    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.nightly")
        (load, _) = records(ctx, "scope.load")
        assert shape(ctx.trace(load["call"])) == (
            "scope.load",
            "completed",
            [("scope.fetch", "completed", [])],
        )


def test_trace_keeps_failures_when_only_failures_are_logged(tmp_path):
    NS = make_ns()
    Load = chain(NS)
    config = {"events": "WARNING"}
    with Context(namespaces={NS}, log_dir=tmp_path, log_config=config) as ctx:
        ctx.get(Load).fail = True
        with pytest.raises(ValueError):
            ctx.execute("scope.nightly")
        (nightly,) = records(ctx, "scope.nightly")
        trace = ctx.trace(nightly["call"])

    assert shape(trace) == (
        "scope.nightly",
        "failed",
        [("scope.load", "failed", [("scope.fetch", "failed", [])])],
    )
    assert trace["started"] is None
    assert trace["children"][0]["children"][0]["error"] == "ValueError('nope')"


def test_trace_attaches_notifications_to_the_publishing_call(tmp_path):
    NS = make_ns()

    @NS
    @Task
    class Announce:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def execute(self) -> None:
            self.notifications.publish("orders.received", level="warning", summary="2 x baguette")

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.announce")
        (started, _) = records(ctx, "scope.announce")
        (notification,) = ctx.trace(started["call"])["notifications"]

    assert notification["key"] == "scope.announce"
    assert notification["topic"] == "orders.received"
    assert notification["level"] == "warning"
    assert notification["message"] == "notified orders.received: 2 x baguette"


def test_build_trace_from_live_events_and_running_calls():
    NS = make_ns()
    seen: list[Event] = []

    @NS
    @Task
    class Slow:
        def execute(self) -> None:
            # Mid-call: the task has started but not ended.
            seen.append(build_trace(list(events), events[0].call_id))

    ctx = Context(namespaces={NS})
    events = collect(ctx)
    with ctx:
        ctx.execute("scope.slow")

    (running,) = seen
    assert (running["key"], running["state"], running["ended"]) == ("scope.slow", "running", None)
    done = build_trace(events, events[0].call_id)
    assert (done["state"], done["protocol"]) == ("completed", "TaskProtocol")
    assert done["started"] is not None


def test_build_trace_unknown_and_ambiguous_ids():
    base = {"source": "events", "state": "started", "ts": "2026-10-31T10:00:00.000+00:00"}
    items = [{**base, "call": "abc1" + "0" * 28}, {**base, "call": "abc2" + "0" * 28}]
    with pytest.raises(KeyError, match="no call 'fff'"):
        build_trace(items, "fff")
    with pytest.raises(ValueError, match="ambiguous"):
        build_trace(items, "abc")
    assert build_trace(items, "abc1")["call"].startswith("abc1")


def test_trace_needs_json_file_logs(tmp_path):
    with pytest.raises(ValueError, match="file logging is off"):
        Context(namespaces={make_ns()}).trace("abc")
    ctx = Context(namespaces={make_ns()}, log_dir=tmp_path, log_config={"format": "text"})
    with pytest.raises(ValueError, match='"json" log format'):
        ctx.trace("abc")
    with pytest.raises(KeyError):
        Context(namespaces={make_ns()}, log_dir=tmp_path / "empty").trace("abc")
