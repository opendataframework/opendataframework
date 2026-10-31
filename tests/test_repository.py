import pytest

from opendataframework.entity import Entity
from opendataframework.namespace import Namespace
from opendataframework.repository import (
    ReadableProtocol,
    Repository,
    StreamableProtocol,
    WritableProtocol,
)


class User: ...


class Invoice: ...


@pytest.fixture(autouse=True)
def _entities():
    # Registered per test rather than decorated at module level: the registry
    # is process-wide, and other test modules register their own ``User``.
    Entity(User)
    Entity(Invoice)


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

    @Repository(Invoice)
    class Invoices: ...

    assert Repository.entity(Users) is User
    assert Repository.entity(Invoices) is Invoice


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


def test_decorator_on_function_raises():
    with pytest.raises(
        TypeError, match="Repository can only decorate a class, got function 'users'"
    ):

        @Repository(User)
        def users(): ...

    assert Repository.get("users") is None
    assert all(isinstance(cls, type) for cls in Repository._entity_map)


def test_function_as_entity_raises():
    with pytest.raises(TypeError, match="Repository expects an entity class, got function 'users'"):

        @Repository
        def users(): ...


def test_entity_left_out_raises():
    with pytest.raises(TypeError, match="expects a class registered with @Entity, got 'Users'"):

        @Repository
        class Users: ...

    assert Repository.get("users") is None


def test_unregistered_entity_raises():
    class Plain: ...

    with pytest.raises(TypeError, match="expects a class registered with @Entity, got 'Plain'"):

        @Repository(Plain)
        class Plains: ...

    assert Repository.get("plains") is None


def test_entity_registered_under_explicit_name_is_accepted():
    @Entity(name="customer")
    class Client: ...

    @Repository(Client)
    class Clients: ...

    assert Repository.entity(Clients) is Client
