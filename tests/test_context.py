import inspect
import threading
import time
from collections.abc import Callable
from typing import Annotated

import pytest

from opendataframework.agent import Agent
from opendataframework.component import Component
from opendataframework.context import Context, Resolver
from opendataframework.entity import Entity
from opendataframework.function import Function
from opendataframework.logger import Logger
from opendataframework.namespace import Namespace
from opendataframework.pipeline import Pipeline
from opendataframework.repository import Repository
from opendataframework.service import Service
from opendataframework.task import Task

# --- helpers -----------------------------------------------------------------


def make_ns():
    """Return a fresh isolated Namespace subclass for each test."""

    class Scope(Namespace): ...

    return Scope


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
        assert ctx.call("function.join", left="a", right="b") == "ab"


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
        messages = [e["message"] for e in ctx.tail_logs("scope.thing")]
        assert any(m.startswith("on_start() started [call=") for m in messages)
        assert any(m.startswith("on_start() completed in ") for m in messages)

    messages = [e["message"] for e in ctx.tail_logs("scope.thing")]
    assert any(m.startswith("on_stop() started [call=") for m in messages)
    assert any(m.startswith("on_stop() completed in ") for m in messages)


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
        assert ctx.is_running("scope.svc") is True

        ctx.stop("scope.svc")
        assert ctx.is_running("scope.svc") is False

        ctx.start("scope.svc")
        assert ctx.is_running("scope.svc") is True

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
        ctx.start("scope.svc")

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
        ctx.stop("scope.svc")
        ctx.stop("scope.svc")

    assert calls == ["stop"]  # only the context-manager teardown call


def test_start_stop_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.start("service.nonexistent")
        with pytest.raises(KeyError):
            ctx.stop("service.nonexistent")


def test_start_stop_non_service_raises_type_error():
    NS = make_ns()

    @NS
    class NotAService: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.start("scope.not-a-service")
        with pytest.raises(TypeError):
            ctx.stop("scope.not-a-service")


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
        assert ctx.is_streaming("scope.cam") is False

        ctx.start_stream("scope.cam")
        assert ctx.is_streaming("scope.cam") is True

        ctx.stop_stream("scope.cam")
        assert ctx.is_streaming("scope.cam") is False


def test_start_stream_is_a_noop_when_already_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.cam")
        # would hang/raise if it spawned a second thread onto the same generator
        ctx.start_stream("scope.cam")
        assert ctx.is_streaming("scope.cam") is True
        ctx.stop_stream("scope.cam")


def test_stop_stream_is_a_noop_when_not_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.stop_stream("scope.cam")
        ctx.stop_stream("scope.cam")
        assert ctx.is_streaming("scope.cam") is False


def test_start_stop_stream_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.start_stream("repository.nonexistent")
        with pytest.raises(KeyError):
            ctx.stop_stream("repository.nonexistent")


def test_start_stop_stream_non_streamable_raises_type_error():
    NS = make_ns()

    @NS
    class NotStreamable: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.start_stream("scope.not-streamable")
        with pytest.raises(TypeError):
            ctx.stop_stream("scope.not-streamable")


def test_is_streaming_false_for_non_streamable():
    NS = make_ns()

    @NS
    class NotStreamable: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_streaming("scope.not-streamable") is False


def test_iter_stream_yields_frames_from_the_running_stream():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.cam")
        frames = ctx.iter_stream("scope.cam")
        assert isinstance(next(frames), int)
        ctx.stop_stream("scope.cam")


def test_iter_stream_fans_out_to_multiple_subscribers():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.cam")
        a = ctx.iter_stream("scope.cam")
        b = ctx.iter_stream("scope.cam")
        assert isinstance(next(a), int)
        assert isinstance(next(b), int)
        ctx.stop_stream("scope.cam")


def test_iter_stream_ends_when_stream_is_stopped():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.cam")
        frames = ctx.iter_stream("scope.cam")
        next(frames)
        ctx.stop_stream("scope.cam")

        with pytest.raises(StopIteration):
            next(frames)


def test_iter_stream_raises_key_error_when_not_streaming():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(KeyError):
            ctx.iter_stream("scope.cam")


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
        ctx.start_stream("scope.device")
        assert calls == ["open_stream"]
        ctx.stop_stream("scope.device")


def test_stop_stream_calls_close_stream_after_the_thread_exits():
    NS = make_ns()
    Device, calls = make_device(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.device")
        ctx.stop_stream("scope.device")
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
        ctx.start_stream("scope.device")
        device = ctx.instances[Device]
        for _ in range(50):
            if device.calls == ["open_stream", "close_stream"]:
                break
            time.sleep(0.01)
        assert device.calls == ["open_stream", "close_stream"]
        assert ctx.is_streaming("scope.device") is False


def test_repository_without_open_close_stream_hooks_still_streams():
    NS = make_ns()
    make_camera(NS)

    with Context(namespaces={NS}) as ctx:
        ctx.start_stream("scope.cam")
        assert ctx.is_streaming("scope.cam") is True
        ctx.stop_stream("scope.cam")


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
            ctx.start_stream("scope.flaky")
        assert ctx.is_streaming("scope.flaky") is False

        # a retry isn't stuck behind the failed attempt's bookkeeping
        ctx.start_stream("scope.flaky")
        assert ctx.is_streaming("scope.flaky") is True
        ctx.stop_stream("scope.flaky")


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
        ctx.start_stream("scope.device")
        ctx.stop_stream("scope.device")  # must not raise despite close_stream() failing
        assert ctx.is_streaming("scope.device") is False

        messages = [e["message"] for e in ctx.tail_logs("scope.device")]
        assert any("close_stream() failed" in m for m in messages)


def test_execute_runs_a_task_by_name():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> int:
            return 42

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("scope.t") == 42


def test_execute_runs_a_pipeline_by_name():
    NS = make_ns()

    @NS
    @Pipeline
    class P:
        def execute(self) -> str:
            return "done"

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("scope.p") == "done"


def test_execute_unknown_name_raises_key_error():
    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.execute("task.nonexistent")


def test_execute_non_task_pipeline_raises_type_error():
    NS = make_ns()

    @NS
    class NotExecutable:
        def execute(self) -> None: ...  # not registered as Task/Pipeline

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError):
            ctx.execute("scope.not-executable")


def test_is_running_false_for_non_service():
    NS = make_ns()

    @NS
    @Task
    class T:
        def execute(self) -> None: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.is_running("scope.t") is False


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
    from opendataframework.task import Task

    ctx = Context(namespaces={Component, Service, Task, Pipeline})
    assert ctx._resolver._namespaces == {Component, Service, Task, Pipeline}


# --- logging: disabled by default ----------------------------------------------


def test_tail_logs_empty_without_log_dir():
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.tail_logs("scope.a") == []


# --- logging: automatic instrumentation -----------------------------------------


def test_resolution_is_logged(tmp_path):
    NS = make_ns()

    @NS
    class A: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        entries = ctx.tail_logs("scope.a")
        assert any("resolved" in e["message"] for e in entries)


def test_service_lifecycle_is_logged(tmp_path):
    NS = make_ns()

    @NS
    class Svc:
        def setup(self) -> None: ...
        def run(self) -> None: ...
        def stop(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        messages = [e["message"] for e in ctx.tail_logs("scope.svc")]
        assert any(m.startswith("setup() started [call=") for m in messages)
        assert any(m.startswith("setup() completed in ") for m in messages)

    messages = [e["message"] for e in ctx.tail_logs("scope.svc")]
    assert any(m.startswith("stop() started [call=") for m in messages)
    assert any(m.startswith("stop() completed in ") for m in messages)


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
            if any("failed" in e["message"] for e in ctx.tail_logs("scope.svc")):
                break
            threading.Event().wait(0.02)
        messages = [e["message"] for e in ctx.tail_logs("scope.svc")]
        assert any("run() failed" in m and "boom" in m for m in messages)


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
    messages = [e["message"] for e in ctx.tail_logs("scope.t")]
    assert any(m.startswith("execute() started [call=") for m in messages)
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

    messages = [e["message"] for e in ctx.tail_logs("scope.t")]
    assert any("execute() failed" in m and "nope" in m for m in messages)


def test_pipeline_execute_is_logged(tmp_path):
    NS = make_ns()

    @NS
    @Pipeline
    class P:
        def execute(self) -> None: ...

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.instances[P].execute()

    messages = [e["message"] for e in ctx.tail_logs("scope.p")]
    assert any(m.startswith("execute() started [call=") for m in messages)


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
        messages = [e["message"] for e in ctx.tail_logs("scope.c")]
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

        assert [e["message"] for e in ctx.tail_logs("scope.a") if e["message"] == "from A"]
        assert [e["message"] for e in ctx.tail_logs("scope.b") if e["message"] == "from B"]
        assert not any(e["message"] == "from B" for e in ctx.tail_logs("scope.a"))


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
        assert ctx.call("function.load-data", path="data.csv") == ("data.csv", ctx.instances[Db])


def test_call_accepts_snake_case_name():
    @Function
    def load_data(path: str):
        return path

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("function.load-data", path="data.csv") == "data.csv"


def test_call_explicit_argument_wins_over_injected():
    NS = make_ns()

    @NS
    class Db: ...

    @Function
    def load_data(db: Db):
        return db

    fake = Db()

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.call("function.load-data", db=fake) is fake


def test_call_passes_unmanaged_class_through_as_argument():
    class Model: ...

    @Function
    def score(model: Model, threshold: float):
        return (model, threshold)

    model = Model()

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("function.score", model=model, threshold=0.5) == (model, 0.5)


def test_call_missing_unmanaged_argument_raises_clear_error():
    class Model: ...

    @Function
    def score(model: Model, threshold: float = 0.5):
        return threshold

    with Context(namespaces={Function}) as ctx:
        with pytest.raises(TypeError, match=r"score\(\) is missing 'model' \(Model\)"):
            ctx.call("function.score")


def test_call_supports_parameter_called_name():
    @Function
    def greet(name: str):
        return f"hello {name}"

    with Context(namespaces={Function}) as ctx:
        assert ctx.call("function.greet", name="odf") == "hello odf"


def test_call_unknown_name_raises_key_error():
    with Context(namespaces={Function}) as ctx:
        with pytest.raises(KeyError):
            ctx.call("function.does-not-exist")


def test_call_before_open_raises_key_error():
    @Function
    def load_data(): ...

    with pytest.raises(KeyError):
        Context(namespaces={Function}).call("function.load-data")


def test_functions_excluded_when_function_namespace_not_configured():
    NS = make_ns()

    @Function
    def load_data(): ...

    with Context(namespaces={NS}) as ctx:
        assert ctx.functions == {}
        with pytest.raises(KeyError):
            ctx.call("function.load-data")


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
        ctx.call("function.load-data")
        messages = [e["message"] for e in ctx.tail_logs("function.load-data")]

    assert "loading" in messages


def test_function_call_is_logged(tmp_path):
    @Function
    def load_data():
        return 42

    with Context(namespaces={Function}, log_dir=tmp_path) as ctx:
        assert ctx.call("function.load-data") == 42
        messages = [e["message"] for e in ctx.tail_logs("function.load-data")]

    assert "load_data resolved" in messages
    assert any(m.startswith("call started [call=") for m in messages)
    assert any("call completed" in m for m in messages)


def test_function_call_exception_is_logged_and_reraised(tmp_path):
    @Function
    def load_data():
        raise ValueError("nope")

    with Context(namespaces={Function}, log_dir=tmp_path) as ctx:
        with pytest.raises(ValueError):
            ctx.call("function.load-data")
        messages = [e["message"] for e in ctx.tail_logs("function.load-data")]

    assert any("call failed" in m and "nope" in m for m in messages)


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
        assert ctx.call("function.load-data", path="data.csv") == "DATA.CSV"
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
        messages = [e["message"] for e in ctx.tail_logs("function.load-data")]

    assert any(m.startswith("call started [call=") for m in messages)
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
        assert ctx.call("scope.researcher", question="dune?") == ("dune?", 3)
        assert ctx.call("scope.researcher", question="dune?", limit=1) == ("dune?", 1)


def test_call_invokes_an_agent_registered_under_an_explicit_name():
    NS = make_ns()

    @NS("assistant")
    @Agent
    class Researcher:
        def invoke(self):
            return "ok"

    with Context(namespaces={NS}) as ctx:
        assert ctx.call("scope.assistant") == "ok"
        with pytest.raises(KeyError):
            ctx.call("scope.researcher")


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
        assert ctx.call("scope.researcher") is ctx.instances[Books]
        assert ctx.get(Researcher).invoke() is ctx.instances[Books]


def test_call_agent_missing_argument_raises_type_error():
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self, question: str): ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(TypeError, match="question"):
            ctx.call("scope.researcher")


def test_call_unresolved_agent_raises_key_error():
    @Agent
    class Researcher:
        def invoke(self): ...

    with Context(namespaces=set()) as ctx:
        with pytest.raises(KeyError):
            ctx.call("agent.researcher")


def test_call_reaches_a_function_and_an_agent_sharing_a_name_by_namespace():
    NS = make_ns()

    @Function
    def researcher():
        return "function"

    @NS
    @Agent
    class Researcher:
        def invoke(self):
            return "agent"

    with Context(namespaces={NS, Function}) as ctx:
        assert ctx.call("function.researcher") == "function"
        assert ctx.call("scope.researcher") == "agent"


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
        assert ctx.execute("scope.digest") == "DUNE?"


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
            ctx.execute("scope.researcher")


def test_agent_invoke_is_logged_through_call(tmp_path):
    NS = make_ns()

    @NS
    @Agent
    class Researcher:
        def invoke(self) -> int:
            return 42

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        assert ctx.call("scope.researcher") == 42

    messages = [e["message"] for e in ctx.tail_logs("scope.researcher")]
    assert any(m.startswith("invoke() started [call=") for m in messages)
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

    messages = [e["message"] for e in ctx.tail_logs("scope.researcher")]
    assert any(m.startswith("invoke() started [call=") for m in messages)
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
            ctx.call("scope.researcher")

    messages = [e["message"] for e in ctx.tail_logs("scope.researcher")]
    assert any("invoke() failed" in m and "nope" in m for m in messages)


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


# --- string annotations --------------------------------------------------------


def test_string_annotated_constructor_parameter_names_the_cause():
    NS = make_ns()

    @NS
    class Postgres: ...

    @NS
    class Users:
        def __init__(self, postgres):
            self.postgres = postgres

    # What `from __future__ import annotations` leaves behind: a string.
    Users.__init__.__annotations__ = {"postgres": "Postgres"}

    with pytest.raises(TypeError) as excinfo:
        Context(namespaces={NS}).open()

    message = str(excinfo.value)
    assert "Users.__init__() is missing 'postgres'" in message
    assert "String annotation on 'postgres'" in message
    assert "from __future__ import annotations" in message


def test_string_annotated_constructor_parameter_with_default_is_left_alone():
    NS = make_ns()

    @NS
    class Users:
        def __init__(self, table="users"):
            self.table = table

    Users.__init__.__annotations__ = {"table": "str"}

    with Context(namespaces={NS}) as ctx:
        assert ctx.get(Users).table == "users"


def test_string_annotated_function_parameter_names_the_cause():
    NS = make_ns()

    @NS
    class Postgres: ...

    @Function
    def load_data(path, db):
        return 1

    load_data.__annotations__ = {"path": "str", "db": "Postgres"}

    with Context(namespaces={NS, Function}) as ctx:
        with pytest.raises(TypeError, match="String annotation on 'db'"):
            ctx.call("function.load-data", path="data.csv")


# --- async is not supported ----------------------------------------------------


def test_async_function_raises_on_open():
    @Function
    async def load_data(path: str) -> int:
        return 1

    with pytest.raises(TypeError, match=r"load_data\(\) is async — the Context does not await"):
        Context(namespaces={Function}).open()


def test_async_generator_function_raises_on_open():
    @Function
    async def rows():
        yield 1

    with pytest.raises(TypeError, match=r"rows\(\) is async"):
        Context(namespaces={Function}).open()


def test_async_execute_raises_on_open():
    @Task
    class Refresh:
        async def execute(self): ...

    with pytest.raises(TypeError, match=r"Refresh\.execute\(\) is async"):
        Context(namespaces={Task}).open()


def test_async_pipeline_execute_raises_on_open():
    @Pipeline
    class Nightly:
        async def execute(self): ...

    with pytest.raises(TypeError, match=r"Nightly\.execute\(\) is async"):
        Context(namespaces={Pipeline}).open()


def test_async_invoke_raises_on_open():
    @Agent
    class Archivist:
        async def invoke(self, question: str) -> str:
            return question

    with pytest.raises(TypeError, match=r"Archivist\.invoke\(\) is async"):
        Context(namespaces={Agent}).open()


@pytest.mark.parametrize("hook", ["on_start", "on_stop"])
def test_async_lifecycle_hook_raises_on_open(hook):
    NS = make_ns()

    async def method(self): ...

    NS(type("Cache", (), {hook: method}))

    with pytest.raises(TypeError, match=rf"Cache\.{hook}\(\) is async"):
        Context(namespaces={NS}).open()


def test_async_service_method_raises_on_open():
    NS = make_ns()

    @NS
    class Worker:
        def setup(self): ...
        async def run(self): ...
        def stop(self): ...

    with pytest.raises(TypeError, match=r"Worker\.run\(\) is async"):
        Context(namespaces={NS}).open()


def test_async_stream_raises_on_open():
    @Entity
    class Event: ...

    @Repository(Event)
    class Events:
        async def stream(self):
            yield Event()

    with pytest.raises(TypeError, match=r"Events\.stream\(\) is async"):
        Context(namespaces={Repository}).open()


def test_async_check_runs_before_anything_is_created():
    NS = make_ns()
    created = []

    @NS
    class Cache:
        def __init__(self):
            created.append(self)

    @Function
    async def load_data(): ...

    with pytest.raises(TypeError):
        Context(namespaces={NS, Function}).open()

    assert created == []


def test_unrelated_async_method_is_left_alone():
    NS = make_ns()

    @NS
    class Client:
        async def run(self): ...
        async def execute(self): ...
        async def fetch(self): ...

    with Context(namespaces={NS}) as ctx:
        assert isinstance(ctx.get(Client), Client)


# --- keys ---------------------------------------------------------------------


@pytest.fixture
def builtin_namespaces():
    """Empty the built-in registries for one test; conftest restores them after."""
    namespaces = (Component, Task, Agent, Function)
    for ns in namespaces:
        ns._namespace.clear()
    return set(namespaces)


def test_same_name_in_different_namespaces_is_addressed_by_key(builtin_namespaces, tmp_path):
    def component():
        @Component
        class Loader:
            def __init__(self, logger: Logger):
                self.logger = logger

            def on_start(self):
                self.logger.info("from component")

        return Loader

    def task():
        @Task
        class Loader:
            def execute(self):
                return "task"

        return Loader

    def agent():
        @Agent
        class Loader:
            def invoke(self):
                return "agent"

        return Loader

    @Function
    def loader():
        return "function"

    component_cls, task_cls, agent_cls = component(), task(), agent()

    with Context(namespaces=builtin_namespaces, log_dir=tmp_path) as ctx:
        assert ctx.execute("task.loader") == "task"
        assert ctx.call("agent.loader") == "agent"
        assert ctx.call("function.loader") == "function"
        assert ctx.key(component_cls) == "component.loader"
        assert ctx.key(task_cls) == "task.loader"
        assert ctx.key(agent_cls) == "agent.loader"
        assert ctx.key(loader) == "function.loader"
        messages = [e["message"] for e in ctx.tail_logs("component.loader")]
        assert "from component" in messages
        assert not any("execute()" in m for m in messages)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "agent.loader.log",
        "component.loader.log",
        "function.loader.log",
        "task.loader.log",
    ]


def test_explicit_name_is_the_key_not_the_class_name(builtin_namespaces):
    @Task("loader")
    class LoadJob:
        def execute(self):
            return 1

    with Context(namespaces=builtin_namespaces) as ctx:
        assert ctx.key(LoadJob) == "task.loader"
        assert ctx.execute("task.loader") == 1
        with pytest.raises(KeyError):
            ctx.execute("task.load-job")


def test_key_is_accepted_in_any_casing():
    NS = make_ns()

    @NS
    @Task
    class LoadJob:
        def execute(self):
            return 1

    with Context(namespaces={NS}) as ctx:
        assert ctx.execute("Scope.LoadJob") == 1
        assert ctx.execute("scope.load_job") == 1


@pytest.mark.parametrize(
    "method", ["execute", "call", "start", "stop", "is_running", "start_stream", "tail_logs"]
)
def test_bare_name_is_rejected_with_a_hint(method):
    NS = make_ns()

    @NS
    class Svc: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(ValueError, match=r"<namespace>\.<name>"):
            getattr(ctx, method)("Svc")


def test_key_of_an_unresolved_object_raises_key_error():
    NS = make_ns()

    class Stray: ...

    with Context(namespaces={NS}) as ctx:
        with pytest.raises(KeyError):
            ctx.key(Stray)


def test_object_in_two_gathered_namespaces_raises():
    NS = make_ns()

    class Other(Namespace): ...

    @Other
    @NS
    class Users: ...

    with pytest.raises(ValueError, match="registered as both 'other.users' and 'scope.users'"):
        Context(namespaces={NS, Other}).open()


def test_two_gathered_namespaces_with_one_name_raise():
    First, Second = make_ns(), make_ns()

    @First
    class Users: ...

    @Second
    class Orders: ...

    @Second("users")
    class Accounts: ...

    with pytest.raises(ValueError, match="'scope.users' names both"):
        Context(namespaces={First, Second}).open()
