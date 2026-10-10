"""The ``@Function`` decorator — the framework's marker for plain functions.

A function is to ``@Function`` what a class is to ``@Component``: made known
to the framework, with no execution contract of its own. It exists so an
existing function-based codebase can be adopted without a class refactor
first — the function is returned unchanged, and the ``Context`` gains a way
to call it by name with its managed dependencies filled in.
"""

import functools
import inspect
from collections.abc import Callable, ItemsView
from typing import Self, TypeVar, overload

from opendataframework.namespace import Namespace
from opendataframework.utils import normalize

F = TypeVar("F", bound=Callable[..., object])

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


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

    @overload
    def __new__(cls, _: F) -> F: ...
    @overload
    def __new__(cls, _: str | None = None, *, name: str | None = None) -> Self: ...
    def __new__(cls, _: Callable[..., object] | str | None = None, *, name: str | None = None):
        """Dispatch like ``Namespace.__new__``, but for functions instead of classes.

        Bare decorator — argument is the function itself. Registers it under
        the kebab-case form of its name and returns it unchanged::

            @Function
            def load_data(): ...

        Factory decorator — argument is a name or nothing; returns a
        ``Function`` instance to be applied to the function as a second step::

            @Function(name="loader")
            def load_data(): ...

        Raises:
            TypeError: If ``_`` is a class or not a named callable.
            ValueError: If the function's name is already registered.
        """
        if _ is None or isinstance(_, str):
            return object.__new__(cls)
        cls._require_function(_)
        cls._register(normalize(_.__name__), _)
        return _

    def __call__(self, wrapped: F) -> F:
        """Handle factory decorator usage.

        Registers ``wrapped`` under the explicit name when provided, or the
        kebab-case form of ``wrapped.__name__`` otherwise.

        Args:
            wrapped: The function being decorated.

        Returns:
            The original function, unmodified.

        Raises:
            TypeError: If ``wrapped`` is a class or not a named callable.
            ValueError: If the name is already registered.
        """
        self._require_function(wrapped)
        self._register(self._name or normalize(wrapped.__name__), wrapped)
        return wrapped

    @classmethod
    def _require_function(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless ``wrapped`` is a named callable that is not a class."""
        if isinstance(wrapped, type) or not callable(wrapped) or not hasattr(wrapped, "__name__"):
            kind = "class" if isinstance(wrapped, type) else type(wrapped).__name__
            name = getattr(wrapped, "__name__", repr(wrapped))
            raise TypeError(f"{cls.__name__} can only decorate a function, got {kind} {name!r}")

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
            "not managed by the Context and not supplied by the caller"
        )


def _describe(parameter: inspect.Parameter) -> str:
    """Render a parameter as ``'name' (Annotation)`` for an error message."""
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return repr(parameter.name)
    return f"{parameter.name!r} ({getattr(annotation, '__name__', annotation)})"
