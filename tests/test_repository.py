from opendataframework.namespace import Namespace
from opendataframework.repository import (
    ReadableProtocol,
    Repository,
    StreamableProtocol,
    WritableProtocol,
)


class User: ...


class Order: ...


def test_repository_is_namespace_subclass():
    assert issubclass(Repository, Namespace)


def test_repository_has_own_namespace():
    assert "_namespace" in Repository.__dict__


def test_decorator_registers_under_kebab_name():
    @Repository(User)
    class UserRepo: ...

    assert Repository.get("user-repo") is UserRepo


def test_decorator_with_explicit_name():
    @Repository(User, name="users")
    class Users: ...

    assert Repository.get("users") is Users


def test_decorator_returns_class_unchanged():
    class Users: ...

    result = Repository(User)(Users)

    assert result is Users


def test_entity_is_stored():
    @Repository(User)
    class Users: ...

    assert Repository.entity(Users) is User


def test_entity_lookup_for_unregistered_returns_none():
    class Unregistered: ...

    assert Repository.entity(Unregistered) is None


def test_different_entities_tracked_independently():
    @Repository(User)
    class Users: ...

    @Repository(Order)
    class Orders: ...

    assert Repository.entity(Users) is User
    assert Repository.entity(Orders) is Order


def test_repository_namespace_is_independent_from_component():
    from opendataframework.component import Component

    assert Repository._namespace is not Component._namespace


def test_repository_in_default_namespaces():
    from opendataframework.context import _DEFAULT_NAMESPACES

    assert Repository in _DEFAULT_NAMESPACES


def test_streamable_protocol_detects_stream_method():
    class LiveFeed:
        def stream(self):
            yield from ()

    assert isinstance(LiveFeed(), StreamableProtocol)


def test_streamable_protocol_rejects_repository_without_stream():
    class Static:
        def all(self):
            return []

    instance = Static()
    assert isinstance(instance, ReadableProtocol)
    assert not isinstance(instance, StreamableProtocol)
    assert not isinstance(instance, WritableProtocol)
