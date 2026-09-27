import pytest

from opendataframework.namespace import Namespace


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
