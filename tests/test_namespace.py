import pytest

from opendataframework.agent import Agent
from opendataframework.component import Component
from opendataframework.entity import Entity
from opendataframework.namespace import ClassNamespace, Namespace
from opendataframework.pipeline import Pipeline
from opendataframework.repository import Repository
from opendataframework.service import Service
from opendataframework.task import Task


def test_subclasses_get_independent_namespaces():
    class A(Namespace): ...

    class B(Namespace): ...

    assert A._namespace is not B._namespace


def test_bare_decorator_registers_under_kebab_name():
    class NS(Namespace): ...

    @NS
    class MetricsFetcher: ...

    assert NS.get("metrics-fetcher") is MetricsFetcher


def test_factory_decorator_registers_under_custom_name():
    class NS(Namespace): ...

    @NS(name="custom-foo")
    class Foo: ...

    assert NS.get("custom-foo") is Foo


def test_bare_decorator_returns_class_unchanged():
    class NS(Namespace): ...

    class Foo: ...

    result = NS(Foo)

    assert result is Foo


def test_factory_decorator_returns_class_unchanged():
    class NS(Namespace): ...

    class Foo: ...

    result = NS(name="custom")(Foo)

    assert result is Foo


def test_get_returns_none_for_unknown_name():
    class NS(Namespace): ...

    assert NS.get("unknown") is None


def test_items_returns_all_registered():
    class NS(Namespace): ...

    @NS
    class MetricsFetcher: ...

    @NS(name="bar")
    class Bar: ...

    assert dict(NS.items()) == {"metrics-fetcher": MetricsFetcher, "bar": Bar}


def test_get_accepts_snake_case():
    class NS(Namespace): ...

    @NS
    class MetricsFetcher: ...

    assert NS.get("metrics_fetcher") is MetricsFetcher


def test_get_accepts_pascal_case():
    class NS(Namespace): ...

    @NS
    class MetricsFetcher: ...

    assert NS.get("MetricsFetcher") is MetricsFetcher


def test_registration_does_not_leak_between_namespaces():
    class A(Namespace): ...

    class B(Namespace): ...

    @A
    class MetricsFetcher: ...

    assert B.get("metrics-fetcher") is None


def test_bare_decorator_duplicate_name_raises():
    class NS(Namespace): ...

    @NS
    class MetricsFetcher: ...

    with pytest.raises(ValueError, match="Duplicate registration"):

        @NS
        class MetricsFetcher: ...  # noqa: F811


def test_factory_decorator_duplicate_name_raises():
    class NS(Namespace): ...

    @NS(name="custom-foo")
    class Foo: ...

    with pytest.raises(ValueError, match="Duplicate registration"):

        @NS(name="custom-foo")
        class Bar: ...


def test_duplicate_registration_names_both_classes():
    class NS(Namespace): ...

    @NS(name="dup")
    class First: ...

    with pytest.raises(ValueError) as excinfo:

        @NS(name="dup")
        class Second: ...

    assert "First" in str(excinfo.value)
    assert "Second" in str(excinfo.value)


def test_bare_decorator_registers_function_unchanged():
    class NS(Namespace): ...

    def load_data(): ...

    assert NS(load_data) is load_data
    assert NS.get("load-data") is load_data


def test_factory_decorator_registers_function_under_custom_name():
    class NS(Namespace): ...

    @NS(name="loader")
    def load_data(): ...

    assert dict(NS.items()) == {"loader": load_data}


def test_bare_decorator_on_non_callable_raises():
    class NS(Namespace): ...

    with pytest.raises(TypeError, match="NS can only decorate a class or a function, got int"):
        NS(123)

    assert dict(NS.items()) == {}


def test_factory_decorator_on_non_callable_raises():
    class NS(Namespace): ...

    with pytest.raises(TypeError, match="NS can only decorate a class or a function, got int"):
        NS(name="number")(123)


def test_class_namespace_rejects_function():
    class NS(ClassNamespace): ...

    with pytest.raises(TypeError, match="NS can only decorate a class, got function 'load_data'"):

        @NS
        def load_data(): ...

    assert dict(NS.items()) == {}


@pytest.mark.parametrize("execution_type", [Component, Service, Task, Pipeline, Agent])
def test_execution_type_on_function_points_to_function_decorator(execution_type):
    name = execution_type.__name__
    message = f"{name} can only decorate a class, got function 'load_data' — .*use @Function"

    with pytest.raises(TypeError, match=message):

        @execution_type
        def load_data(): ...

    with pytest.raises(TypeError, match=message):

        @execution_type(name="loader")
        def load_data(): ...

    assert execution_type.get("load-data") is None
    assert execution_type.get("loader") is None


def test_second_execution_type_on_a_class_raises():
    with pytest.raises(TypeError, match="Refresh is already registered as a Task — .*@Component"):

        @Component
        @Task
        class Refresh:
            def execute(self): ...

    assert Component.get("refresh") is None


def test_second_execution_type_raises_in_either_order():
    with pytest.raises(TypeError, match="Refresh is already registered as a Component — .*@Task"):

        @Task(name="refresh-task")
        @Component
        class Refresh:
            def execute(self): ...

    assert Task.get("refresh-task") is None


def test_repository_on_a_class_with_an_execution_type_raises():
    @Entity
    class User: ...

    with pytest.raises(TypeError, match="Users is already registered as a Service"):

        @Repository(User)
        @Service
        class Users: ...


def test_entity_rejects_function():
    with pytest.raises(TypeError, match="Entity can only decorate a class, got function 'user'"):

        @Entity
        def user(): ...
