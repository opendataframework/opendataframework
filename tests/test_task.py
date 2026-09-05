from opendataframework.component import Component
from opendataframework.namespace import Namespace
from opendataframework.task import Task, TaskProtocol


def test_task_is_namespace_subclass():
    assert issubclass(Task, Namespace)


def test_task_has_own_namespace():
    assert "_namespace" in Task.__dict__


def test_task_namespace_is_independent_from_component():
    assert Task._namespace is not Component._namespace


def test_bare_decorator():
    class MetricsFetcher: ...

    result = Task(MetricsFetcher)

    assert result is MetricsFetcher
    assert Task.get("metrics-fetcher") is MetricsFetcher


def test_keyword_name():
    class MetricsFetcher: ...

    result = Task(name="metrics-fetcher")(MetricsFetcher)

    assert result is MetricsFetcher
    assert Task.get("metrics-fetcher") is MetricsFetcher


def test_bare_decorator_returns_class_unchanged():
    class MetricsFetcher: ...

    result = Task(MetricsFetcher)

    assert result is MetricsFetcher


def test_get_returns_none_for_unknown_name():
    assert Task.get("unknown") is None


def test_registration_does_not_leak_to_component():
    class Standalone: ...

    Task(Standalone)

    assert Component.get("standalone") is None


def test_task_protocol_satisfied_by_execute():
    class MetricsFetcher:
        def execute(self): ...

    assert isinstance(MetricsFetcher(), TaskProtocol)


def test_task_protocol_not_satisfied_without_execute():
    class NotATask: ...

    assert not isinstance(NotATask(), TaskProtocol)
