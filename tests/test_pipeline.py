from opendataframework.namespace import Namespace
from opendataframework.pipeline import Pipeline, PipelineProtocol
from opendataframework.task import Task


def test_pipeline_is_namespace_subclass():
    assert issubclass(Pipeline, Namespace)


def test_pipeline_has_own_namespace():
    assert "_namespace" in Pipeline.__dict__


def test_pipeline_namespace_is_independent_from_task():
    assert Pipeline._namespace is not Task._namespace


def test_bare_decorator():
    class DailyAnalytics: ...

    result = Pipeline(DailyAnalytics)

    assert result is DailyAnalytics
    assert Pipeline.get("daily-analytics") is DailyAnalytics


def test_keyword_name():
    class DailyAnalytics: ...

    result = Pipeline(name="daily-analytics")(DailyAnalytics)

    assert result is DailyAnalytics
    assert Pipeline.get("daily-analytics") is DailyAnalytics


def test_bare_decorator_returns_class_unchanged():
    class DailyAnalytics: ...

    result = Pipeline(DailyAnalytics)

    assert result is DailyAnalytics


def test_get_returns_none_for_unknown_name():
    assert Pipeline.get("unknown") is None


def test_registration_does_not_leak_to_task():
    class Workflow: ...

    Pipeline(Workflow)

    assert Task.get("workflow") is None


def test_pipeline_protocol_satisfied_by_execute():
    class DailyAnalytics:
        def execute(self): ...

    assert isinstance(DailyAnalytics(), PipelineProtocol)


def test_pipeline_protocol_not_satisfied_without_execute():
    class NotAPipeline: ...

    assert not isinstance(NotAPipeline(), PipelineProtocol)
