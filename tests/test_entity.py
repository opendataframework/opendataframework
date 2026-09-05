from opendataframework.entity import Entity
from opendataframework.namespace import Namespace


def test_entity_is_namespace_subclass():
    assert issubclass(Entity, Namespace)


def test_entity_has_own_namespace():
    assert "_namespace" in Entity.__dict__


def test_bare_decorator():
    class User: ...

    result = Entity(User)

    assert result is User
    assert Entity.get("user") is User


def test_factory_decorator():
    class Order: ...

    result = Entity(name="order")(Order)

    assert result is Order
    assert Entity.get("order") is Order


def test_bare_decorator_returns_class_unchanged():
    class Frame: ...

    result = Entity(Frame)

    assert result is Frame


def test_entity_namespace_is_independent_from_component():
    from opendataframework.component import Component

    assert Entity._namespace is not Component._namespace
