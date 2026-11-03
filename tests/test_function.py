import functools
import inspect
import typing
from dataclasses import dataclass
from typing import Annotated

import pytest

from opendataframework.context import Context
from opendataframework.entity import Entity
from opendataframework.function import Function, bind
from opendataframework.namespace import Namespace
from opendataframework.repository import Record, Repository


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


def test_bind_signature_leaves_out_injected_parameters():
    def load(db, path: str, limit: int = 10) -> int: ...

    bound = bind(load, {"db": "postgres"})

    assert str(inspect.signature(bound)) == "(path: str, limit: int = 10) -> int"
    assert str(inspect.signature(load)) == "(db, path: str, limit: int = 10) -> int"


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


def test_bind_missing_string_annotated_argument_names_the_cause():
    def load(path, db):
        return (path, db)

    # What `from __future__ import annotations` leaves behind: a string.
    load.__annotations__ = {"db": "Postgres"}

    with pytest.raises(TypeError) as excinfo:
        bind(load, {})("data.csv")

    message = str(excinfo.value)
    assert "load() is missing 'db' (Postgres)" in message
    assert "String annotation on 'db'" in message
    assert "from __future__ import annotations" in message


def test_bind_missing_argument_without_string_annotation_has_no_hint():
    def load(path: str, limit: int):
        return (path, limit)

    with pytest.raises(TypeError) as excinfo:
        bind(load, {})("data.csv")

    assert "String annotation" not in str(excinfo.value)


# --- Record arguments ---------------------------------------------------------


def _drafts() -> type:
    """Return a registered ``Drafts`` repository for ``Record`` to name."""

    @Entity
    @dataclass
    class Draft:
        id: int
        ref: str

    @Repository(Draft)
    class Drafts: ...

    return Drafts


def test_record_defaults_to_the_id_field():
    Drafts = _drafts()

    assert Record(Drafts).field == "id"
    assert Record(Drafts, field="ref").field == "ref"


def test_record_is_hashable():
    Drafts = _drafts()

    assert hash(Record(Drafts)) == hash(Record(Drafts))
    assert Record(Drafts) == Record(Drafts)


def test_record_argument_is_left_for_the_caller():
    Drafts = _drafts()

    @Function
    def confirm_draft(draft_id: Annotated[int, Record(Drafts)]):
        return draft_id

    with Context(namespaces={Function}) as ctx:
        assert list(ctx.parameters(confirm_draft)) == ["draft_id"]
        assert ctx.call("function.confirm-draft", draft_id=1) == 1


def test_record_survives_in_type_hints():
    Drafts = _drafts()

    def confirm_draft(draft_id: Annotated[int, Record(Drafts, field="ref")]): ...

    hint = typing.get_type_hints(confirm_draft, include_extras=True)["draft_id"]

    assert hint.__metadata__ == (Record(Drafts, field="ref"),)


def test_record_does_not_stop_a_function_in_the_same_annotation_being_injected():
    # No one would write this annotation. It only pins that a Record in
    # Annotated metadata doesn't stop _dependency() scanning the rest of it,
    # so the rule is "a Record is skipped", not "any metadata is skipped".
    Drafts = _drafts()

    @Function
    def load_draft():
        return "draft"

    @Function
    def confirm_draft(draft: Annotated[int, Record(Drafts), load_draft]):
        return draft()

    with Context(namespaces={Function}) as ctx:
        assert list(ctx.parameters(confirm_draft)) == []
        assert ctx.call("function.confirm-draft") == "draft"
