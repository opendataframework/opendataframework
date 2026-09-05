from opendataframework.component import Component
from opendataframework.namespace import Namespace


def test_component_is_namespace_subclass():
    assert issubclass(Component, Namespace)


def test_component_has_own_namespace():
    assert "_namespace" in Component.__dict__


def test_bare_decorator():
    class Foo: ...

    result = Component(Foo)

    assert result is Foo
    assert Component.get("foo") is Foo


def test_factory_decorator():
    class Bar: ...

    result = Component(name="custom-bar")(Bar)

    assert result is Bar
    assert Component.get("custom-bar") is Bar
