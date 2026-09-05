from opendataframework.component import Component
from opendataframework.namespace import Namespace
from opendataframework.service import Service


def test_service_is_namespace_subclass():
    assert issubclass(Service, Namespace)


def test_service_has_own_namespace():
    assert "_namespace" in Service.__dict__


def test_service_namespace_is_independent_from_component():
    assert Service._namespace is not Component._namespace


def test_bare_decorator():
    class Postgres: ...

    result = Service(Postgres)

    assert result is Postgres
    assert Service.get("postgres") is Postgres


def test_positional_name():
    class Postgres: ...

    result = Service("pg")(Postgres)

    assert result is Postgres
    assert Service.get("pg") is Postgres


def test_keyword_name():
    class Postgres: ...

    result = Service(name="pg-kw")(Postgres)

    assert result is Postgres
    assert Service.get("pg-kw") is Postgres


def test_bare_decorator_returns_class_unchanged():
    class Postgres: ...

    result = Service(Postgres)

    assert result is Postgres


def test_positional_name_returns_class_unchanged():
    class Postgres: ...

    result = Service("pg-unchanged")(Postgres)

    assert result is Postgres


def test_get_returns_none_for_unknown_name():
    assert Service.get("unknown") is None


def test_registration_does_not_leak_to_component():
    class Worker: ...

    Service(Worker)

    assert Component.get("worker") is None
