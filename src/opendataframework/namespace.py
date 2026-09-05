"""The ``Namespace`` base class underlying every framework decorator.

``Entity``, ``Component``, ``Service``, ``Task``, ``Pipeline``,
``Repository``, and ``Layer`` all subclass ``Namespace`` to get the same
name → class registration and dual bare/factory decorator dispatch, each
maintaining its own independent name-to-class mapping.
"""

from collections.abc import ItemsView
from typing import Self, TypeVar, overload

from opendataframework.utils import kebab, normalize

C = TypeVar("C")


class Namespace:
    """Base class for framework namespaces.

    A ``Namespace`` subclass is a decorator that registers user-defined classes
    under a named scope. Each subclass maintains its own independent mapping of
    name → class, making it a self-contained namespace in the Python sense.

    Names are derived from class names using kebab-case, matching the config
    key convention. Explicit names are stored as-is.

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

    The decorated class is always returned unchanged — no base class is added
    and no methods are injected.

    Attributes:
        _namespace: Per-subclass mapping of registered name → class. Assigned
            automatically when each subclass is defined; never shared between
            sibling subclasses.
    """

    _namespace: dict[str, type]

    def __init_subclass__(cls, **kwargs) -> None:
        """Assign a fresh namespace dict to every subclass on definition."""
        super().__init_subclass__(**kwargs)
        cls._namespace = {}

    @overload
    def __new__(cls, _: type[C]) -> type[C]: ...
    @overload
    def __new__(cls, _: str | None = None, *, name: str | None = None) -> Self: ...
    def __new__(cls, _: type | str | None = None, *, name: str | None = None):
        """Dispatch between the two decorator call shapes, typed separately per shape.

        ``Namespace`` supports two ways of decorating a class, and each takes
        a structurally different argument — so each gets its own ``@overload``
        above, letting a type checker resolve ``@Analytics`` and
        ``@Analytics(name=...)`` to two different result types instead of one
        blurry union. This method (unannotated, no ``@overload``) is the real
        implementation; a type checker never uses it to check call sites, only
        to confirm it actually satisfies both overloads declared above it.

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
        """
        if isinstance(_, type):
            cls._namespace[kebab(_.__name__)] = _
            return _
        return super().__new__(cls)

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

    def __call__(self, wrapped: type[C]) -> type[C]:
        """Handle factory decorator usage.

        Registers ``wrapped`` under the explicit name when provided, or the
        kebab-case form of ``wrapped.__name__`` otherwise. Returns ``wrapped``
        unchanged.

        Args:
            wrapped: The class being decorated.

        Returns:
            The original class, unmodified.
        """
        self.__class__._namespace[self._name or kebab(wrapped.__name__)] = wrapped
        return wrapped

    @classmethod
    def get(cls, name: str) -> type | None:
        """Look up a registered class by name.

        Args:
            name: The registration name to look up.

        Returns:
            The registered class, or ``None`` if no class is registered under
            that name.

        Example::

            @Analytics
            class MetricsFetcher: ...

            Analytics.get("metrics-fetcher")  # → MetricsFetcher
            Analytics.get("unknown")          # → None
        """
        return cls._namespace.get(normalize(name))

    @classmethod
    def items(cls) -> ItemsView[str, type]:
        """Return all registered name → class pairs.

        Returns:
            A view of ``(name, class)`` pairs for every class registered in
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
