import threading
import time

import pytest

from opendataframework.context import Context
from opendataframework.logger import Logger
from opendataframework.namespace import Namespace
from opendataframework.pipeline import Pipeline
from opendataframework.repository import Repository
from opendataframework.task import Task

# --- helpers -----------------------------------------------------------------


def make_ns():
    """Return a fresh isolated Namespace subclass for each test."""

    class NS(Namespace): ...

    return NS


# --- dependency resolution ----------------------------------------------------


def test_creates_instance_with_no_deps():
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}) as ctx:
        assert isinstance(ctx.instances[A], A)


def test_injects_dependency():
    NS = make_ns()

    @NS
    class A: ...

    @NS
    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    with Context(namespaces={NS}) as ctx:
        assert ctx.instances[B].a is ctx.instances[A]


def test_resolves_transitive_dependencies():
    NS = make_ns()

    @NS
    class A: ...

    @NS
    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    @NS
    class C:
        def __init__(self, b: B) -> None:
            self.b = b

    with Context(namespaces={NS}) as ctx:
        assert ctx.instances[C].b is ctx.instances[B]
        assert ctx.instances[C].b.a is ctx.instances[A]


def test_circular_dependency_raises():
    NS = make_ns()

    @NS
    class A:
        def __init__(self, b: B) -> None: ...  # type: ignore[name-defined]

    @NS
    class B:
        def __init__(self, a: A) -> None: ...

    # Patch annotations so they resolve to actual classes
    A.__init__.__annotations__["b"] = B

    with pytest.raises(ValueError, match="Circular dependency"):
        with Context(namespaces={NS}):
            pass


# --- instances property -------------------------------------------------------


def test_instances_returns_copy():
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}) as ctx:
        snapshot = ctx.instances
        snapshot.clear()
        assert A in ctx.instances


# --- service lifecycle --------------------------------------------------------


def test_stop_order_is_reverse_of_start():
    NS = make_ns()
    order = []

    @NS
    class A:
        def setup(self) -> None:
            order.append(("start", A))

        def run(self) -> None: ...

        def stop(self) -> None:
            order.append(("stop", A))

    @NS
    class B:
        def __init__(self, a: A) -> None: ...

        def setup(self) -> None:
            order.append(("start", B))

        def run(self) -> None: ...

        def stop(self) -> None:
            order.append(("stop", B))

    with Context(namespaces={NS}):
        pass

    assert order == [
        ("start", A),
        ("start", B),
        ("stop", B),
        ("stop", A),
    ]


def test_service_setup_called():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None:
            calls.append("setup")

        def run(self) -> None: ...

        def stop(self) -> None: ...

    with Context(namespaces={NS}):
        pass

    assert calls == ["setup"]


def test_service_run_in_background_thread():
    NS = make_ns()
    started = threading.Event()

    @NS
    class Svc:
        def setup(self) -> None: ...

        def run(self) -> None:
            started.set()

        def stop(self) -> None: ...

    with Context(namespaces={NS}):
        assert started.wait(timeout=1)


def test_service_stop_called():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None: ...

        def run(self) -> None: ...

        def stop(self) -> None:
            calls.append("stop")

    with Context(namespaces={NS}):
        pass

    assert calls == ["stop"]


# --- component / repository lifecycle (on_start / on_stop) --------------------


def test_component_on_start_and_on_stop_are_called():
    NS = make_ns()
    calls = []

    @NS
    class Thing:
        def on_start(self) -> None:
            calls.append("on_start")

        def on_stop(self) -> None:
            calls.append("on_stop")

    with Context(namespaces={NS}):
        assert calls == ["on_start"]

    assert calls == ["on_start", "on_stop"]


def test_repository_on_start_and_on_stop_are_called():
    NS = make_ns()
    calls = []

    class Entity: ...

    @NS
    @Repository(Entity)
    class Repo:
        def on_start(self) -> None:
            calls.append("on_start")

        def on_stop(self) -> None:
            calls.append("on_stop")

    with Context(namespaces={NS}):
        assert calls == ["on_start"]

    assert calls == ["on_start", "on_stop"]


def test_on_start_on_stop_order_matches_service_order():
    NS = make_ns()
    order = []

    @NS
    class A:
        def on_start(self) -> None:
            order.append(("start", "A"))

        def on_stop(self) -> None:
            order.append(("stop", "A"))

    @NS
    class B:
        def __init__(self, a: A) -> None: ...

        def on_start(self) -> None:
            order.append(("start", "B"))

        def on_stop(self) -> None:
            order.append(("stop", "B"))

    with Context(namespaces={NS}):
        pass

    assert order == [("start", "A"), ("start", "B"), ("stop", "B"), ("stop", "A")]


def test_component_without_on_start_on_stop_is_left_alone():
    NS = make_ns()

    @NS
    class Plain: ...

    with Context(namespaces={NS}) as ctx:
        assert isinstance(ctx.instances[Plain], Plain)


def test_on_start_and_on_stop_are_logged(tmp_path):
    NS = make_ns()

    @NS
    class Thing:
        def on_start(self) -> None: ...
        def on_stop(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        messages = [e["message"] for e in ctx.tail_logs("Thing")]
        assert "on_start() called" in messages
        assert "on_start() complete" in messages

    messages = [e["message"] for e in ctx.tail_logs("Thing")]
    assert "on_stop() called" in messages
    assert "on_stop() complete" in messages


# --- individual lifecycle control (UI actions) --------------------------------


def test_stop_and_start_a_single_service_by_name():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None:
            calls.append("setup")

        def run(self) -> None: ...

        def stop(self) -> None:
            calls.append("stop")

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_running("Svc") is True

        ctx.stop("Svc")
        assert ctx.is_running("Svc") is False

        ctx.start("Svc")
        assert ctx.is_running("Svc") is True

    assert calls == ["setup", "stop", "setup", "stop"]


def test_start_is_a_noop_when_already_running():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None:
            calls.append("setup")

        def run(self) -> None: ...

        def stop(self) -> None: ...

    with Context(namespaces={NS}) as ctx:
        ctx.start("Svc")

    assert calls == ["setup"]


def test_stop_is_a_noop_when_not_running():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None: ...

        def run(self) -> None: ...

        def stop(self) -> None:
            calls.append("stop")

    with Context(namespaces={NS}) as ctx:
        ctx.stop("Svc")
        ctx.stop("Svc")

    assert calls == ["stop"]  # only the context-manager teardown call


def test_start_stop_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.start("Nonexistent")
        with pytest.raises(KeyError):
            ctx.stop("Nonexistent")


def test_start_stop_non_service_raises_type_error():
    NS = make_ns()

    @NS
    class NotAService: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.start("NotAService")
        with pytest.raises(TypeError):
            ctx.stop("NotAService")


# --- repository stream control (UI actions) ------------------------------------


def make_camera(ns):
    @ns
    class Cam:
        def stream(self):
            n = 0
            while True:
                n += 1
                yield n

    return Cam


def test_start_stop_stream_toggles_a_streamable_repository():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_streaming("Cam") is False

        ctx.start_stream("Cam")
        assert ctx.is_streaming("Cam") is True

        ctx.stop_stream("Cam")
        assert ctx.is_streaming("Cam") is False


def test_start_stream_is_a_noop_when_already_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Cam")
        # would hang/raise if it spawned a second thread onto the same generator
        ctx.start_stream("Cam")
        assert ctx.is_streaming("Cam") is True
        ctx.stop_stream("Cam")


def test_stop_stream_is_a_noop_when_not_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.stop_stream("Cam")
        ctx.stop_stream("Cam")
        assert ctx.is_streaming("Cam") is False


def test_start_stop_stream_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.start_stream("Nonexistent")
        with pytest.raises(KeyError):
            ctx.stop_stream("Nonexistent")


def test_start_stop_stream_non_streamable_raises_type_error():
    NS = make_ns()

    @NS
    class NotStreamable: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.start_stream("NotStreamable")
        with pytest.raises(TypeError):
            ctx.stop_stream("NotStreamable")


def test_is_streaming_false_for_non_streamable():
    NS = make_ns()

    @NS
    class NotStreamable: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_streaming("NotStreamable") is False


def test_iter_stream_yields_frames_from_the_running_stream():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Cam")
        frames = ctx.iter_stream("Cam")
        assert isinstance(next(frames), int)
        ctx.stop_stream("Cam")


def test_iter_stream_fans_out_to_multiple_subscribers():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Cam")
        a = ctx.iter_stream("Cam")
        b = ctx.iter_stream("Cam")
        assert isinstance(next(a), int)
        assert isinstance(next(b), int)
        ctx.stop_stream("Cam")


def test_iter_stream_ends_when_stream_is_stopped():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Cam")
        frames = ctx.iter_stream("Cam")
        next(frames)
        ctx.stop_stream("Cam")

        with pytest.raises(StopIteration):
            next(frames)


def test_iter_stream_raises_key_error_when_not_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(KeyError):
            ctx.iter_stream("Cam")


# --- repository stream resource lifecycle (open_stream / close_stream) --------


def make_device(ns):
    """A streamable repository that ties a fake device to the stream's own
    lifetime via open_stream()/close_stream(), mirroring how Webcam ties a
    real camera handle to Context.start_stream()/stop_stream().
    """
    calls = []

    @ns
    class Device:
        def open_stream(self) -> None:
            calls.append("open_stream")
            self.open = True

        def close_stream(self) -> None:
            calls.append("close_stream")
            self.open = False

        def stream(self):
            n = 0
            while True:
                n += 1
                yield n

    return Device, calls


def test_start_stream_calls_open_stream_before_spawning_the_thread():
    NS = make_ns()
    Device, calls = make_device(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Device")
        assert calls == ["open_stream"]
        ctx.stop_stream("Device")


def test_stop_stream_calls_close_stream_after_the_thread_exits():
    NS = make_ns()
    Device, calls = make_device(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Device")
        ctx.stop_stream("Device")
        assert calls == ["open_stream", "close_stream"]


def test_close_stream_is_called_when_the_source_ends_on_its_own():
    NS = make_ns()

    @NS
    class Device:
        def __init__(self) -> None:
            self.calls = []

        def open_stream(self) -> None:
            self.calls.append("open_stream")

        def close_stream(self) -> None:
            self.calls.append("close_stream")

        def stream(self):
            yield 1  # a finite source — no explicit stop_stream() call

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Device")
        device = ctx.instances[Device]
        for _ in range(50):
            if device.calls == ["open_stream", "close_stream"]:
                break
            time.sleep(0.01)
        assert device.calls == ["open_stream", "close_stream"]
        assert ctx.is_streaming("Device") is False


def test_repository_without_open_close_stream_hooks_still_streams():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("Cam")
        assert ctx.is_streaming("Cam") is True
        ctx.stop_stream("Cam")


def test_open_stream_failure_propagates_and_does_not_stick():
    NS = make_ns()

    @NS
    class Flaky:
        def __init__(self) -> None:
            self.attempts = 0

        def open_stream(self) -> None:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("device busy")

        def close_stream(self) -> None: ...

        def stream(self):
            while True:
                yield 1

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(RuntimeError):
            ctx.start_stream("Flaky")
        assert ctx.is_streaming("Flaky") is False

        # a retry isn't stuck behind the failed attempt's bookkeeping
        ctx.start_stream("Flaky")
        assert ctx.is_streaming("Flaky") is True
        ctx.stop_stream("Flaky")


def test_close_stream_exception_is_logged_not_raised(tmp_path):
    NS = make_ns()

    @NS
    class Device:
        def open_stream(self) -> None: ...

        def close_stream(self) -> None:
            raise RuntimeError("release failed")

        def stream(self):
            while True:
                yield 1

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.start_stream("Device")
        ctx.stop_stream("Device")  # must not raise despite close_stream() failing
        assert ctx.is_streaming("Device") is False

        messages = [e["message"] for e in ctx.tail_logs("Device")]
        assert any("close_stream() raised" in m for m in messages)


def test_execute_runs_a_task_by_name():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> int:
            return 42

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("T") == 42


def test_execute_runs_a_pipeline_by_name():
    NS = make_ns()

    @NS
    @Pipeline
    class P:
        def execute(self) -> str:
            return "done"

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("P") == "done"


def test_execute_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.execute("Nonexistent")


def test_execute_non_task_pipeline_raises_type_error():
    NS = make_ns()

    @NS
    class NotExecutable:
        def execute(self) -> None: ...  # not registered as Task/Pipeline

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.execute("NotExecutable")


def test_is_running_false_for_non_service():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_running("T") is False


# --- task / pipeline — no lifecycle ------------------------------------------


def test_task_has_no_lifecycle():
    NS = make_ns()
    calls = []

    @NS
    class T:
        def execute(self) -> None:
            calls.append("execute")

    with Context(namespaces={NS}):
        pass

    assert calls == []


# --- default namespaces -------------------------------------------------------


def test_default_namespaces_include_builtin_types():
    from opendataframework.component import Component
    from opendataframework.pipeline import Pipeline
    from opendataframework.service import Service
    from opendataframework.task import Task

    ctx = Context(namespaces={Component, Service, Task, Pipeline})
    assert ctx._resolver._namespaces == {Component, Service, Task, Pipeline}


# --- logging: disabled by default ----------------------------------------------


def test_tail_logs_empty_without_log_dir():
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.tail_logs("A") == []


# --- logging: automatic instrumentation -----------------------------------------


def test_resolution_is_logged(tmp_path):
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        entries = ctx.tail_logs("A")
        assert any("resolved" in e["message"] for e in entries)


def test_service_lifecycle_is_logged(tmp_path):
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        messages = [e["message"] for e in ctx.tail_logs("Svc")]
        assert "setup() starting" in messages
        assert "setup() complete" in messages

    messages = [e["message"] for e in ctx.tail_logs("Svc")]
    assert "stop() called" in messages
    assert "stop() complete" in messages


def test_service_run_exception_is_logged(tmp_path):
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None:
            raise RuntimeError("boom")

        def stop(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        for _ in range(50):
            if any("raised" in e["message"] for e in ctx.tail_logs("Svc")):
                break
            threading.Event().wait(0.02)
        messages = [e["message"] for e in ctx.tail_logs("Svc")]
        assert any("run() raised" in m and "boom" in m for m in messages)


def test_task_execute_is_logged(tmp_path):
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> int:
            return 42

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        instance = ctx.instances[T]
        result = instance.execute()

    assert result == 42
    messages = [e["message"] for e in ctx.tail_logs("T")]
    assert "execute() started" in messages
    assert any("execute() completed" in m for m in messages)


def test_task_execute_exception_is_logged_and_reraised(tmp_path):
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None:
            raise ValueError("nope")

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        instance = ctx.instances[T]
        with pytest.raises(ValueError):
            instance.execute()

    messages = [e["message"] for e in ctx.tail_logs("T")]
    assert any("execute() raised" in m and "nope" in m for m in messages)


def test_pipeline_execute_is_logged(tmp_path):
    NS = make_ns()

    @NS
    @Pipeline
    class P:
        def execute(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.instances[P].execute()

    messages = [e["message"] for e in ctx.tail_logs("P")]
    assert "execute() started" in messages


def test_component_has_no_execute_instrumentation(tmp_path):
    from opendataframework.component import Component

    NS = make_ns()

    @NS
    @Component
    class C:
        def execute(self) -> str:
            return "not a task"

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        assert ctx.instances[C].execute() == "not a task"
        messages = [e["message"] for e in ctx.tail_logs("C")]
        assert not any("execute()" in m for m in messages)


# --- logging: injectable Logger --------------------------------------------------


def test_logger_dependency_is_injected(tmp_path):
    NS = make_ns()

    @NS
    class A:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        assert isinstance(ctx.instances[A].logger, Logger)


def test_logger_is_bound_to_consuming_class(tmp_path):
    NS = make_ns()

    @NS
    class A:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    @NS
    class B:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.instances[A].logger.info("from A")
        ctx.instances[B].logger.info("from B")

        assert [e["message"] for e in ctx.tail_logs("A") if e["message"] == "from A"]
        assert [e["message"] for e in ctx.tail_logs("B") if e["message"] == "from B"]
        assert not any(e["message"] == "from B" for e in ctx.tail_logs("A"))


def test_logger_without_log_dir_is_safe_noop():
    NS = make_ns()

    @NS
    class A:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    with Context(namespaces={NS}) as ctx:
        ctx.instances[A].logger.info("no-op")  # must not raise
