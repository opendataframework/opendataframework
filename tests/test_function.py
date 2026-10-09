import functools

import pytest

from opendataframework.function import Function, bind
from opendataframework.namespace import Namespace


def test_function_is_namespace_subclass():
    assert issubclass(Function, Namespace)


def test_bare_decorator_registers_under_kebab_name():
    @Function
    def load_data(): ...

    assert Function.get("load-data") is load_data


def test_factory_decorator_registers_under_custom_name():
    @Function(name="loader")
    def load_data(): ...

    assert Function.get("loader") is load_data
    assert Function.get("load-data") is None


def test_factory_decorator_without_name_uses_function_name():
    @Function()
    def load_data(): ...

    assert Function.get("load-data") is load_data


def test_decorator_returns_function_unchanged():
    def load_data(path):
        return path

    assert Function(load_data) is load_data
    assert load_data("data.csv") == "data.csv"


def test_get_accepts_snake_case():
    @Function
    def load_data(): ...

    assert Function.get("load_data") is load_data


def test_items_returns_all_registered():
    @Function
    def first(): ...

    @Function
    def second(): ...

    registered = dict(Function.items())

    assert registered["first"] is first
    assert registered["second"] is second


def test_duplicate_name_raises():
    @Function
    def load_data(): ...

    with pytest.raises(ValueError, match="Duplicate registration for 'load-data'"):

        @Function
        def load_data(): ...  # noqa: F811


def test_bare_decorator_on_class_raises():
    with pytest.raises(TypeError, match="Function can only decorate a function, got class 'Users'"):

        @Function
        class Users: ...

    assert Function.get("users") is None


def test_factory_decorator_on_class_raises():
    with pytest.raises(TypeError, match="Function can only decorate a function, got class 'Users'"):

        @Function(name="users")
        class Users: ...

    assert Function.get("users") is None


def test_unnamed_callable_raises():
    with pytest.raises(TypeError, match="Function can only decorate a function, got partial"):
        Function(functools.partial(print))


def test_wrapped_callable_is_accepted():
    @Function
    @functools.cache
    def load_config(): ...

    assert Function.get("load-config") is load_config


# --- bind ---------------------------------------------------------------------


def test_bind_fills_injected_parameter():
    def load(path, db):
        return (path, db)

    assert bind(load, {"db": "postgres"})("data.csv") == ("data.csv", "postgres")


def test_bind_does_not_modify_the_function():
    def load(path, db):
        return (path, db)

    bound = bind(load, {"db": "postgres"})

    assert bound is not load
    assert load("data.csv", "sqlite") == ("data.csv", "sqlite")


def test_bind_positional_arguments_skip_a_leading_injected_parameter():
    def load(db, path, limit=10):
        return (db, path, limit)

    assert bind(load, {"db": "postgres"})("data.csv", 5) == ("postgres", "data.csv", 5)


def test_bind_fills_keyword_only_parameter():
    def load(path, *, db):
        return (path, db)

    assert bind(load, {"db": "postgres"})("data.csv") == ("data.csv", "postgres")


def test_bind_explicit_keyword_wins_over_injected():
    def load(db, path):
        return (db, path)

    assert bind(load, {"db": "postgres"})(path="data.csv", db="sqlite") == ("sqlite", "data.csv")


def test_bind_passes_var_positional_through():
    def load(db, *paths):
        return (db, paths)

    assert bind(load, {"db": "postgres"})("a.csv", "b.csv") == ("postgres", ("a.csv", "b.csv"))


def test_bind_missing_argument_names_parameter_and_type():
    class Model: ...

    def score(model: Model, threshold, db):
        return threshold

    with pytest.raises(TypeError) as excinfo:
        bind(score, {"db": "postgres"})()

    message = str(excinfo.value)
    assert "score() is missing 'model' (Model), 'threshold'" in message
    assert "not managed by the Context" in message


def test_bind_surplus_argument_raises_the_functions_own_error():
    def load(db, path):
        return (db, path)

    with pytest.raises(TypeError, match="takes 2 positional arguments but 3 were given"):
        bind(load, {"db": "postgres"})("a.csv", "b.csv")


def test_bind_returns_uninspectable_callable_as_is():
    class Opaque:
        __signature__ = "not a signature"

        def __call__(self):
            return 1

    opaque = Opaque()

    assert bind(opaque, {}) is opaque
