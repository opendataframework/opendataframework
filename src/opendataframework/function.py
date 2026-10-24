"""The ``@Function`` decorator — the framework's marker for plain functions.

A function is to ``@Function`` what a class is to ``@Component``: made known
to the framework, with no execution contract of its own. It exists so an
existing function-based codebase can be adopted without a class refactor
first — the function is returned unchanged, and the ``Context`` gains a way
to call it by name with its managed dependencies filled in.
"""

import functools
import inspect
from collections.abc import Callable, ItemsView, Iterable
from typing import Protocol

from opendataframework.namespace import Namespace, describe
from opendataframework.utils import normalize

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


class FunctionProtocol(Protocol):
    """Expected interface for functions registered with ``@Function``.

    A function is called with arguments and returns a result — the
    function-shaped counterpart of ``TaskProtocol``. It is a label for type
    hints and for events, not a way to detect a function: any callable would
    match it structurally, so it is deliberately not ``runtime_checkable``
    and ``isinstance()`` against it raises ``TypeError``. The ``Context``
    knows a function by its ``@Function`` registration instead.

    Every call of a registered function made through the ``Context`` —
    injected, ``context.call()``, or ``context.get(func)`` — emits events
    with this protocol (see ``opendataframework.events``)::

        events.subscribe(on_call, protocol=FunctionProtocol)
    """

    def __call__(self, *args, **kwargs) -> object:
        """Run the function with its arguments and return a result."""
        ...


class Function(Namespace):
    """Decorator that registers a plain function with the Context.

    ``@Function`` marks a function as framework-aware. The ``Context`` works
    out which of its parameters are managed dependencies and can then call it
    by name, supplying those itself — so the caller passes only the remaining
    arguments.

    The decorated function is returned unchanged. Calling it directly behaves
    exactly as before: nothing is injected, and every argument must be passed.

    Basic usage::

        @Function
        def load_data(path: str, limit: int = 100) -> list[dict]: ...

    With an explicit name::

        @Function(name="loader")
        def load_data(path: str) -> list[dict]: ...

    Dependency injection — a parameter annotated with a type the ``Context``
    manages is injected; every other parameter is a call argument::

        @Function
        def load_data(path: str, db: Postgres) -> int: ...

        load_data("data.csv", db=fake_db)                    # direct: unchanged
        project.context.call("load-data", path="data.csv")   # db injected
        project.context.get(load_data)("data.csv")           # db injected

    A class asks for a function by naming it in ``Annotated`` — it receives
    the function with its managed dependencies already filled in::

        @Task
        class Refresh:
            def __init__(self, load: Annotated[Callable[..., int], load_data]): ...

    A function has no state and no lifecycle hooks. Reach for a class
    (``@Component``, ``@Task``, ...) once it needs either.

    Looking up registered functions::

        Function.get("load-data")   # → load_data
        Function.get("load_data")   # → load_data
        dict(Function.items())      # → all registered functions

    Raises:
        TypeError: If the decorated object is a class, or is not a named
            callable.
    """

    _namespace: dict[str, Callable[..., object]]

    @classmethod
    def _require(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless ``wrapped`` is a named callable that is not a class."""
        if isinstance(wrapped, type) or not callable(wrapped) or not hasattr(wrapped, "__name__"):
            raise TypeError(f"{cls.__name__} can only decorate a function, got {describe(wrapped)}")

    @classmethod
    def get(cls, name: str) -> Callable[..., object] | None:
        """Look up a registered function by name, in any casing.

        Example::

            @Function
            def load_data(): ...

            Function.get("load-data")  # → load_data
            Function.get("load_data")  # → load_data
            Function.get("unknown")    # → None
        """
        return cls._namespace.get(normalize(name))

    @classmethod
    def items(cls) -> ItemsView[str, Callable[..., object]]:
        """Return all registered name → function pairs."""
        return cls._namespace.items()


def bind(func: Callable[..., object], injected: dict[str, object]) -> Callable[..., object]:
    """Return ``func`` with the ``injected`` parameters filled in on every call.

    The returned callable takes the remaining arguments the way ``func``
    itself would if the injected parameters weren't in its signature:
    positional arguments fill the non-injected positional parameters in
    order, so an injected parameter that comes first doesn't shift them. An
    argument the caller passes explicitly by keyword wins over the injected
    value.

    Its signature says the same: ``inspect.signature()`` of the returned
    callable leaves the injected parameters out, so whatever builds a form or
    a tool schema from it asks only for what a caller can supply.

    Args:
        func: The function to bind.
        injected: Parameter name → value for each parameter to supply.

    Returns:
        A wrapper around ``func``; ``func`` itself is left untouched.

    Raises:
        TypeError: On call, if a required parameter was neither injected nor
            supplied.

    Example:
        >>> def load(db, path, limit=10):
        ...     return (db, path, limit)
        >>> bind(load, {"db": "postgres"})("data.csv")
        ('postgres', 'data.csv', 10)
        >>> str(inspect.signature(bind(load, {"db": "postgres"})))
        '(path, limit=10)'
    """
    try:
        signature = inspect.signature(func)
    except ValueError, TypeError:
        return func
    parameters = list(signature.parameters.values())

    @functools.wraps(func)
    def bound(*args, **kwargs):
        """Call ``func``, filling its injected parameters."""
        positional, keywords = _merge(parameters, injected, args, kwargs)
        _require_arguments(func, signature, positional, keywords)
        return func(*positional, **keywords)

    # Without this, ``inspect.signature`` follows ``__wrapped__`` to ``func``
    # and reports the injected parameters as ones the caller must pass.
    bound.__signature__ = signature.replace(
        parameters=[parameter for parameter in parameters if parameter.name not in injected]
    )
    return bound


def _merge(
    parameters: list[inspect.Parameter],
    injected: dict[str, object],
    args: tuple,
    kwargs: dict[str, object],
) -> tuple[list, dict[str, object]]:
    """Combine the caller's arguments with the injected ones, in ``func``'s own order."""
    positional: list = []
    keywords = dict(kwargs)
    remaining = list(args)
    by_position = True
    for parameter in parameters:
        name = parameter.name
        if parameter.kind in _POSITIONAL:
            if name in kwargs:
                by_position = False
            elif name in injected:
                if by_position:
                    positional.append(injected[name])
                else:
                    keywords[name] = injected[name]
            elif by_position and remaining:
                positional.append(remaining.pop(0))
            else:
                by_position = False
        elif parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            if by_position:
                positional.extend(remaining)
                remaining.clear()
            by_position = False
        elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            if name in injected and name not in kwargs:
                keywords[name] = injected[name]
    # Surplus positionals are passed through so ``func`` raises its own error.
    positional.extend(remaining)
    return positional, keywords


def _require_arguments(
    func: Callable[..., object],
    signature: inspect.Signature,
    positional: list,
    keywords: dict[str, object],
) -> None:
    """Raise a ``TypeError`` naming each required parameter that has no value."""
    try:
        supplied = signature.bind_partial(*positional, **keywords).arguments
    except TypeError:
        # Too many or unknown arguments — ``func`` reports those better itself.
        return
    missing = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind not in _VARIADIC
        and parameter.name not in supplied
    ]
    if missing:
        described = ", ".join(_describe(parameter) for parameter in missing)
        raise TypeError(
            f"{func.__name__}() is missing {described} — "
            f"not managed by the Context and not supplied by the caller{string_hint(missing)}"
        )


def string_hint(parameters: Iterable[inspect.Parameter]) -> str:
    """Return a sentence about the string-annotated ``parameters``, or ``""`` if none is.

    The ``Context`` injects by type, and an annotation that is a string —
    every one under ``from __future__ import annotations`` — is not a type.
    The parameter is then left to the caller, which shows up as a missing
    argument; this names the actual cause.
    """
    names = [parameter.name for parameter in parameters if isinstance(parameter.annotation, str)]
    if not names:
        return ""
    listed = ", ".join(repr(name) for name in names)
    return (
        f". String annotation on {listed}: the Context injects by type and does not read a "
        "string as one — remove `from __future__ import annotations` from the module, or the "
        "quotes around the annotation, to have it injected"
    )


def _describe(parameter: inspect.Parameter) -> str:
    """Render a parameter as ``'name' (Annotation)`` for an error message."""
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return repr(parameter.name)
    return f"{parameter.name!r} ({getattr(annotation, '__name__', annotation)})"
