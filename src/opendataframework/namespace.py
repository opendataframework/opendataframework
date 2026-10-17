"""The ``Namespace`` base class underlying every framework decorator.

``Entity``, ``Component``, ``Service``, ``Task``, ``Pipeline``, ``Agent``,
``Function``, ``Repository``, and ``Layer`` all subclass ``Namespace`` to get the same
name → object registration and dual bare/factory decorator dispatch, each
maintaining its own independent name-to-object mapping.

``Namespace`` itself registers any named class or function. What a particular
decorator accepts is narrowed one level down: ``ClassNamespace`` takes classes
only, and ``ExecutionType`` — the base of ``Component``, ``Repository``,
``Service``, ``Task``, ``Pipeline`` and ``Agent`` — additionally lets a class
carry only one of them.
"""

from collections.abc import Callable, ItemsView
from typing import Self, TypeVar, overload

from opendataframework.utils import kebab, normalize

C = TypeVar("C")
F = TypeVar("F", bound=Callable[..., object])


class Namespace:
    """Base class for framework namespaces.

    A ``Namespace`` subclass is a decorator that registers user-defined classes
    and functions under a named scope. Each subclass maintains its own
    independent mapping of name → object, making it a self-contained namespace
    in the Python sense.

    Names are derived from class and function names using kebab-case, matching
    the config key convention. Explicit names are stored as-is.

    Subclasses support two decoration styles:

    Bare decorator (name derived from class name in kebab-case)::

        class Analytics(Namespace): ...

        @Analytics
        class MetricsFetcher: ...

        Analytics.get("metrics-fetcher")  # → MetricsFetcher

    Factory decorator (explicit name)::

        @Analytics(name="metrics-classifier")
        class Classifier: ...

        Analytics.get("metrics-classifier")  # → Classifier

    The decorated object is always returned unchanged — no base class is added
    and no methods are injected.

    A plain ``Namespace`` subclass takes a class or a named function; anything
    else raises ``TypeError`` at decoration time. The framework's own
    decorators are narrower — see ``ClassNamespace`` and ``ExecutionType``
    below, and ``Function`` and ``Layer`` in their own modules. Each states
    what it accepts by overriding ``_require``.

    Attributes:
        _namespace: Per-subclass mapping of registered name → object. Assigned
            automatically when each subclass is defined; never shared between
            sibling subclasses.
    """

    _namespace: dict[str, type | Callable[..., object]]

    def __init_subclass__(cls, **kwargs) -> None:
        """Assign a fresh namespace dict to every subclass on definition."""
        super().__init_subclass__(**kwargs)
        cls._namespace = {}

    @overload
    def __new__(cls, _: type[C]) -> type[C]: ...
    @overload
    def __new__(cls, _: F) -> F: ...
    @overload
    def __new__(cls, _: str | None = None, *, name: str | None = None) -> Self: ...
    def __new__(cls, _: type | Callable[..., object] | str | None = None, *, name=None):
        """Dispatch between the two decorator call shapes, typed separately per shape.

        ``Namespace`` supports two ways of decorating a class, and each takes
        a structurally different argument — so each gets its own ``@overload``
        above, letting a type checker resolve ``@Analytics`` and
        ``@Analytics(name=...)`` to two different result types instead of one
        blurry union. This method (unannotated, no ``@overload``) is the real
        implementation; a type checker never uses it to check call sites, only
        to confirm it actually satisfies the overloads declared above it.

        The function overload is declared here, on the base, so a type checker
        accepts a function wherever one is valid (``@Function``, a layer). It
        therefore also accepts ``@Component def f`` — that one is caught at
        decoration time instead, by ``_require``.

        Bare decorator — argument is the class itself, matches the first
        overload (``_: type[C]) -> type[C]``). Registers it immediately and
        returns it unchanged, short-circuiting before ``__init__`` runs::

            @Analytics
            class MetricsFetcher: ...

            # reveal_type(MetricsFetcher) -> type[MetricsFetcher], not Analytics

        Factory decorator — argument is a name or nothing, matches the second
        overload (``_: str | None = None, ...) -> Self``). Returns an
        ``Analytics`` instance instead, which is then called on the class as a
        second step (``Namespace.__call__``, not this method)::

            @Analytics(name="metrics-classifier")
            class Classifier: ...

            # reveal_type(Analytics(name="x")) -> Analytics
            # reveal_type(Classifier) -> type[Classifier], from __call__ below

        Raises:
            TypeError: If ``_`` is not something this namespace accepts (see
                ``_require``) — e.g. ``@Component`` applied to a function.
            ValueError: If the name is already registered in this namespace.
        """
        if _ is None or isinstance(_, str):
            return super().__new__(cls)
        cls._require(_)
        cls._register(cls._key(_), _)
        return _

    def __init__(self, _: type | str | None = None, *, name: str | None = None) -> None:
        """Store the explicit name for factory decorator usage.

        Accepts the name either as a positional string argument or as the
        ``name`` keyword argument::

            @Service("postgres")           # positional
            @Component(name="classifier")  # keyword

        Args:
            _: When a string, used as the registration name (positional form).
                When a type, ignored — ``__new__`` short-circuits before
                ``__init__`` is reached in the bare-decorator case.
            name: Optional name to register the class under (keyword form).
                Ignored when ``_`` is already a string.
        """
        self._name = _ if isinstance(_, str) else name

    @overload
    def __call__(self, wrapped: type[C]) -> type[C]: ...
    @overload
    def __call__(self, wrapped: F) -> F: ...
    def __call__(self, wrapped):
        """Handle factory decorator usage.

        Registers ``wrapped`` under the explicit name when provided, or the
        kebab-case form of ``wrapped.__name__`` otherwise. Returns ``wrapped``
        unchanged.

        Args:
            wrapped: The class or function being decorated.

        Returns:
            The original object, unmodified.

        Raises:
            TypeError: If ``wrapped`` is not something this namespace accepts
                (see ``_require``).
            ValueError: If the name is already registered in this namespace.
        """
        self._require(wrapped)
        self._register(self._name or self._key(wrapped), wrapped)
        return wrapped

    @staticmethod
    def _key(wrapped) -> str:
        """Return the name ``wrapped`` is registered under when none is given."""
        name = wrapped.__name__
        return kebab(name) if isinstance(wrapped, type) else normalize(name)

    @classmethod
    def _register(cls, key: str, wrapped) -> None:
        """Store ``wrapped`` under ``key``, refusing to overwrite an existing entry.

        Raises:
            ValueError: If ``key`` is already registered in this namespace, or
                ``wrapped`` already is under another name — an object has one
                name per namespace, so its ``qualified`` key is unique.
        """
        if key in cls._namespace:
            existing = cls._namespace[key]
            raise ValueError(
                f"Duplicate registration for {key!r} in {cls.__name__}: "
                f"{existing.__name__} and {wrapped.__name__}"
            )
        for name, member in cls._namespace.items():
            if member is wrapped:
                raise ValueError(
                    f"{wrapped.__name__} is already registered in {cls.__name__} as "
                    f"{name!r}, so it cannot also be registered as {key!r}"
                )
        cls._namespace[key] = wrapped

    @classmethod
    def _require(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless this namespace accepts ``wrapped``.

        The base accepts a class or a named function. Subclasses override
        this to narrow it — it is the one place a decorator says what it may
        be applied to.
        """
        if not callable(wrapped) or not hasattr(wrapped, "__name__"):
            raise TypeError(
                f"{cls.__name__} can only decorate a class or a function, got {describe(wrapped)}"
            )

    @classmethod
    def get(cls, name: str) -> type | Callable[..., object] | None:
        """Look up a registered class or function by name.

        Args:
            name: The registration name to look up.

        Returns:
            The registered object, or ``None`` if nothing is registered under
            that name.

        Example::

            @Analytics
            class MetricsFetcher: ...

            Analytics.get("metrics-fetcher")  # → MetricsFetcher
            Analytics.get("unknown")          # → None
        """
        return cls._namespace.get(normalize(name))

    @classmethod
    def items(cls) -> ItemsView[str, type | Callable[..., object]]:
        """Return all registered name → object pairs.

        Returns:
            A view of ``(name, object)`` pairs for everything registered in
            this namespace.

        Example::

            @Analytics
            class MetricsFetcher: ...

            @Analytics(name="metrics")
            class Metrics: ...

            dict(Analytics.items())
            # {"metrics-fetcher": MetricsFetcher, "metrics": Metrics}
        """
        return cls._namespace.items()


def qualified(namespace: type[Namespace], name: str) -> str:
    """Return the key a registered object is addressed by: ``<namespace>.<name>``.

    A name is unique within its namespace, so the pair is unique across all
    of them — ``task.loader`` and ``agent.loader`` never collide.

    Example::

        qualified(Task, "load-job")  # → "task.load-job"
    """
    return f"{kebab(namespace.__name__)}.{name}"


def parse(key: str) -> str:
    """Normalize a ``<namespace>.<name>`` key, in any casing, to its ``qualified`` form.

    Splits on the first dot, so an explicit name that itself contains a dot
    still parses: ``"Task.LoadJob"`` → ``"task.load-job"``.

    Raises:
        ValueError: If ``key`` has no namespace part.
    """
    namespace, dot, name = key.partition(".")
    if not dot or not namespace or not name:
        raise ValueError(
            f"{key!r} is not a key — address a registered object as "
            "<namespace>.<name>, e.g. 'task.load-job' or 'agent.librarian'"
        )
    return f"{normalize(namespace)}.{normalize(name)}"


def describe(wrapped: object) -> str:
    """Render ``wrapped`` as ``<kind> '<name>'`` for an error message."""
    kind = "class" if isinstance(wrapped, type) else type(wrapped).__name__
    return f"{kind} {getattr(wrapped, '__name__', repr(wrapped))!r}"


class ClassNamespace(Namespace):
    """A ``Namespace`` that registers classes only.

    Base of ``Entity`` and ``Layer``, and — through ``ExecutionType`` — of
    every decorator that turns a class into something the ``Context`` manages.
    Not a decorator in its own right.
    """

    _namespace: dict[str, type]

    @classmethod
    def _require(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless ``wrapped`` is a class."""
        if not isinstance(wrapped, type):
            raise TypeError(f"{cls.__name__} can only decorate a class, got {describe(wrapped)}")

    @classmethod
    def get(cls, name: str) -> type | None:
        """Look up a registered class by name, in any casing."""
        return cls._namespace.get(normalize(name))

    @classmethod
    def items(cls) -> ItemsView[str, type]:
        """Return all registered name → class pairs."""
        return cls._namespace.items()


class ExecutionType(ClassNamespace):
    """A ``ClassNamespace`` whose classes carry exactly one execution type.

    Base of ``Component``, ``Repository``, ``Service``, ``Task``, ``Pipeline``
    and ``Agent``. An execution type says how the ``Context`` treats a class,
    so a class takes one of them — ``@Component @Task class X`` raises at
    decoration time rather than leaving it to chance which contract applies.
    Not a decorator in its own right.
    """

    @classmethod
    def _require(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless ``wrapped`` is a class with no other execution type.

        A function gets a message that names ``@Function`` — the one decorator
        built for it.
        """
        if not isinstance(wrapped, type) and callable(wrapped):
            raise TypeError(
                f"{cls.__name__} can only decorate a class, got {describe(wrapped)} — "
                "to register a function, use @Function"
            )
        super()._require(wrapped)
        for other in ExecutionType.__subclasses__():
            if other is not cls and any(wrapped is member for member in other._namespace.values()):
                raise TypeError(
                    f"{wrapped.__name__} is already registered as a {other.__name__} — a class "
                    f"takes one execution type, so @{cls.__name__} cannot be added to it"
                )
