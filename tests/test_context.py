import inspect
import threading
import time
from collections.abc import Callable
from typing import Annotated

import pytest

from opendataframework.agent import Agent
from opendataframework.context import Context, Resolver
from opendataframework.entity import Entity
from opendataframework.function import Function
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


def test_same_dependency_under_two_parameters_raises():
    NS = make_ns()

    @NS
    class Db: ...

    @NS
    class Sync:
        def __init__(self, source: Db, target: Db) -> None: ...

    with pytest.raises(ValueError, match="Sync asks for Db more than once.*'source', 'target'"):
        Context(namespaces={NS}).open()


def test_same_unmanaged_type_under_two_parameters_is_allowed():
    @Function
    def join(left: str, right: str):
        return left + right

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("join", left="a", right="b") == "ab"


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

    @Entity
    class Record: ...

    @NS
    @Repository(Record)
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


# --- functions ----------------------------------------------------------------


def test_function_dependency_is_injected_on_call():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(path: str, db: Db):
        return (path, db)

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.call("load-data", path="data.csv") == ("data.csv", ctx.instances[Db])


def test_call_accepts_snake_case_name():
    @Function
    def load_data(path: str):
        return path

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("load_data", path="data.csv") == "data.csv"


def test_call_explicit_argument_wins_over_injected():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db):
        return db

    fake = Db()

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.call("load-data", db=fake) is fake


def test_call_passes_unmanaged_class_through_as_argument():
    class Model: ...

    @Function
    def score(model: Model, threshold: float):
        return (model, threshold)

    model = Model()

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("score", model=model, threshold=0.5) == (model, 0.5)


def test_call_missing_unmanaged_argument_raises_clear_error():
    class Model: ...

    @Function
    def score(model: Model, threshold: float = 0.5):
        return threshold

    with Context(namespaces={Function}) as ctx:
        with pytest.raises(TypeError, match=r"score\(\) is missing 'model' \(Model\)"):
            ctx.call("score")


def test_call_supports_parameter_called_name():
    @Function
    def greet(name: str):
        return f"hello {name}"

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("greet", name="odf") == "hello odf"


def test_call_unknown_name_raises_key_error():
    with Context(namespaces={Function}) as ctx:
        with pytest.raises(KeyError):
            ctx.call("does-not-exist")


def test_call_before_open_raises_key_error():
    @Function
    def load_data(): ...

    with pytest.raises(KeyError):
        Context(namespaces={Function}).call("load-data")


def test_functions_excluded_when_function_namespace_not_configured():
    NS = make_ns()

    @Function
    def load_data(): ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.functions == {}
        with pytest.raises(KeyError):
            ctx.call("load-data")


def test_function_in_default_namespaces():
    from opendataframework.context import _DEFAULT_NAMESPACES

    assert Function in _DEFAULT_NAMESPACES


def test_function_is_not_in_instances():
    @Function
    def load_data(): ...

    with Context(namespaces={Function}) as ctx:
        assert load_data not in ctx.instances
        assert load_data in ctx.functions


def test_get_function_returns_bound_callable():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db, path: str, limit: int = 10):
        return (db, path, limit)

    with Context(namespaces={NS, Function}) as ctx:
        bound = ctx.get(load_data)

        assert bound is ctx.functions[load_data]
        assert bound("data.csv", 5) == (ctx.instances[Db], "data.csv", 5)


def test_get_unresolved_function_raises_key_error():
    def plain(): ...

    with Context(namespaces={Function}) as ctx:
        with pytest.raises(KeyError):
            ctx.get(plain)


def test_direct_call_of_registered_function_is_not_injected():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db):
        return db

    with Context(namespaces={NS, Function}):
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'db'"):
            load_data()


def test_function_logger_is_bound_to_function_name(tmp_path):
    @Function
    def load_data(logger: Logger):
        logger.info("loading")

    with Context(namespaces={Function}, log_dir=tmp_path) as ctx:
        ctx.call("load-data")
        messages = [e["message"] for e in ctx.tail_logs("load_data")]

    assert "loading" in messages


def test_function_call_is_logged(tmp_path):
    @Function
    def load_data():
        return 42

    with Context(namespaces={Function}, log_dir=tmp_path) as ctx:
        assert ctx.call("load-data") == 42
        messages = [e["message"] for e in ctx.tail_logs("load_data")]

    assert "load_data resolved" in messages
    assert "call started" in messages
    assert any("call completed" in m for m in messages)


def test_function_call_exception_is_logged_and_reraised(tmp_path):
    @Function
    def load_data():
        raise ValueError("nope")

    with Context(namespaces={Function}, log_dir=tmp_path) as ctx:
        with pytest.raises(ValueError):
            ctx.call("load-data")
        messages = [e["message"] for e in ctx.tail_logs("load_data")]

    assert any("call raised" in m and "nope" in m for m in messages)


def test_parameters_returns_only_caller_supplied_ones():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db, path: str, limit: int = 10, *, logger: Logger): ...

    with Context(namespaces={NS, Function}) as ctx:
        parameters = ctx.parameters(load_data)

    assert list(parameters) == ["path", "limit"]
    assert parameters["limit"].default == 10


def test_parameters_unresolved_function_raises_key_error():
    def plain(): ...

    with Context(namespaces={Function}) as ctx:
        with pytest.raises(KeyError):
            ctx.parameters(plain)


def test_dependencies_reads_a_functions_own_signature():
    class Db: ...

    def load_data(self: Db, path: str, limit=10): ...

    assert Resolver.dependencies(load_data) == {"self": Db, "path": str}


# --- injecting functions ------------------------------------------------------


def test_function_is_injected_into_a_class_under_any_parameter_name():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db, path: str):
        return (db, path)

    @NS
    class Report:
        def __init__(self, load: Annotated[Callable[..., tuple], load_data]) -> None:
            self.load = load

    with Context(namespaces={NS, Function}) as ctx:
        report = ctx.instances[Report]
        assert report.load is ctx.get(load_data)
        assert report.load("data.csv") == (ctx.instances[Db], "data.csv")


def test_bound_function_signature_matches_parameters():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db, path: str, limit: int = 10) -> int:
        """Load rows."""

    with Context(namespaces={NS, Function}) as ctx:
        bound = ctx.get(load_data)
        assert list(inspect.signature(bound).parameters) == list(ctx.parameters(load_data))
        assert bound.__doc__ == "Load rows."


def test_function_is_injected_into_another_function():
    @Function
    def parse(text: str):
        return text.upper()

    @Function
    def load_data(path: str, parser: Annotated[Callable[[str], str], parse]):
        return parser(path)

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("load-data", path="data.csv") == "DATA.CSV"
        assert list(ctx.parameters(load_data)) == ["path"]


def test_function_is_injected_through_an_alias():
    NS = make_ns()

    @Function
    def load_data():
        return 42

    Plain = Annotated[Callable[[], int], load_data]
    type Lazy = Annotated[Callable[[], int], load_data]

    @NS
    class A:
        def __init__(self, load: Plain) -> None:
            self.load = load

    @NS
    class B:
        def __init__(self, load: Lazy) -> None:
            self.load = load

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.instances[A].load() == 42
        assert ctx.instances[B].load() == 42


def test_call_through_an_injected_function_is_logged(tmp_path):
    NS = make_ns()

    @Function
    def load_data():
        return 42

    @NS
    class Report:
        def __init__(self, load: Annotated[Callable[[], int], load_data]) -> None:
            self.load = load

    with Context(namespaces={NS, Function}, log_dir=tmp_path) as ctx:
        ctx.instances[Report].load()
        messages = [e["message"] for e in ctx.tail_logs("load_data")]

    assert "call started" in messages
    assert any("call completed" in m for m in messages)


def test_circular_dependency_through_a_function_raises():
    NS = make_ns()

    @Function
    def load_data(report: Report): ...

    @NS
    class Report:
        def __init__(self, load: Annotated[Callable[[], None], load_data]) -> None: ...

    with pytest.raises(ValueError, match="Circular dependency"):
        Context(namespaces={NS, Function}).open()


def test_annotated_without_a_registered_function_is_not_injected():
    NS = make_ns()

    def plain(): ...

    @NS
    class A:
        def __init__(
            self,
            unregistered: Annotated[Callable[[], None], plain] = None,
            described: Annotated[int, "a number"] = 0,
        ) -> None:
            self.unregistered = unregistered
            self.described = described

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.instances[A].unregistered is None
        assert ctx.instances[A].described == 0


def test_order_holds_classes_only():
    NS = make_ns()

    @Function
    def load_data(): ...

    @NS
    class Report:
        def __init__(self, load: Annotated[Callable[[], None], load_data]) -> None: ...

    resolver = Resolver({NS, Function})
    resolver.resolve()

    assert resolver.order == [Report]


def test_dependencies_returns_the_function_named_in_annotated():
    def load_data(): ...

    class Report:
        def __init__(
            self, load: Annotated[Callable[[], None], load_data], note: Annotated[int, "x"]
        ): ...

    assert Resolver.dependencies(Report) == {"load": load_data}


# --- agents -------------------------------------------------------------------


def test_call_invokes_an_agent_by_name_with_arguments():
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self, question: str, limit: int = 3):
            return (question, limit)

    with Context(namespaces={NS}) as ctx:
        assert ctx.call("researcher", question="dune?") == ("dune?", 3)
        assert ctx.call("Researcher", question="dune?", limit=1) == ("dune?", 1)


def test_call_invokes_an_agent_registered_under_an_explicit_name():
    NS = make_ns()

    @NS
    @Agent(name="assistant")
    class Researcher:
        def invoke(self):
            return "ok"

    with Context(namespaces={NS}) as ctx:
        assert ctx.call("assistant") == "ok"


def test_agent_dependencies_are_injected_through_the_constructor():
    NS = make_ns()

    @NS
    class Books: ...

    @NS
    @Agent
    class Researcher:
        def __init__(self, books: Books):
            self.books = books

        def invoke(self):
            return self.books

    with Context(namespaces={NS}) as ctx:
        assert ctx.call("researcher") is ctx.instances[Books]
        assert ctx.get(Researcher).invoke() is ctx.instances[Books]


def test_call_agent_missing_argument_raises_type_error():
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self, question: str): ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError, match="question"):
            ctx.call("researcher")


def test_call_unresolved_agent_raises_key_error():
    @Agent
    class Researcher:
        def invoke(self): ...

    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.call("researcher")


def test_call_name_shared_by_function_and_agent_raises_value_error():
    NS = make_ns()

    @Function
    def researcher(): ...

    @NS
    @Agent
    class Researcher:
        def invoke(self): ...

    with Context(namespaces={NS, Function}) as ctx:
        with pytest.raises(ValueError, match="ambiguous"):
            ctx.call("researcher")


def test_agent_can_be_injected_into_a_pipeline():
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self, question: str):
            return question.upper()

    @NS
    @Pipeline
    class Digest:
        def __init__(self, researcher: Researcher):
            self.researcher = researcher

        def execute(self):
            return self.researcher.invoke("dune?")

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("Digest") == "DUNE?"


def test_agent_on_start_and_on_stop_are_called():
    NS = make_ns()
    calls = []

    @NS
    @Agent
    class Researcher:
        def on_start(self):
            calls.append("start")

        def on_stop(self):
            calls.append("stop")

        def invoke(self): ...

    with Context(namespaces={NS}):
        assert calls == ["start"]

    assert calls == ["start", "stop"]


def test_execute_rejects_an_agent():
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self): ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.execute("Researcher")


def test_agent_invoke_is_logged_through_call(tmp_path):
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self) -> int:
            return 42

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        assert ctx.call("researcher") == 42

    messages = [e["message"] for e in ctx.tail_logs("Researcher")]
    assert "invoke() started" in messages
    assert any("invoke() completed" in m for m in messages)


def test_agent_direct_invoke_is_logged(tmp_path):
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self, question: str) -> str:
            return question

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        assert ctx.get(Researcher).invoke("dune?") == "dune?"

    messages = [e["message"] for e in ctx.tail_logs("Researcher")]
    assert "invoke() started" in messages
    assert any("invoke() completed" in m for m in messages)


def test_agent_invoke_exception_is_logged_and_reraised(tmp_path):
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self) -> None:
            raise ValueError("nope")

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        with pytest.raises(ValueError):
            ctx.call("researcher")

    messages = [e["message"] for e in ctx.tail_logs("Researcher")]
    assert any("invoke() raised" in m and "nope" in m for m in messages)


def test_parameters_returns_an_agents_invoke_parameters():
    NS = make_ns()

    @NS
    class Books: ...

    @NS
    @Agent
    class Researcher:
        def __init__(self, books: Books): ...

        def invoke(self, question: str, limit: int = 3): ...

    with Context(namespaces={NS}) as ctx:
        parameters = ctx.parameters(Researcher)

    assert list(parameters) == ["question", "limit"]
    assert parameters["question"].annotation is str
    assert parameters["limit"].default == 3


def test_parameters_unresolved_agent_raises_key_error():
    @Agent
    class Researcher:
        def invoke(self): ...

    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.parameters(Researcher)


def test_parameters_non_agent_class_raises_key_error():
    NS = make_ns()

    @NS
    class Books: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(KeyError):
            ctx.parameters(Books)
