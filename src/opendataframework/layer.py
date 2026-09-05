"""The ``@Layer`` decorator and the framework's built-in architectural layers.

A layer is a ``Namespace`` whose values are themselves ``Namespace``
subclasses — it groups components into named subsystems (``Api``,
``Storage``, ``Analytics``, ...) with no runtime behavior of its own.
"""

from typing import Self, overload

from opendataframework.namespace import Namespace


class Layer(Namespace):
    """Namespace whose values are themselves ``Namespace`` subclasses.

    ``Layer`` organises components into named architectural subsystems.
    ``Layer._namespace`` maps kebab-case layer names to layer classes — each of
    which is a ``Namespace`` subclass that, in turn, maps component names to
    component classes.

    Defining a layer::

        @Layer
        class MachineLearning(Namespace): ...

        @Layer("ml")
        class MachineLearning(Namespace): ...

    Using a layer as a decorator::

        @MachineLearning
        @Component
        class Classifier: ...

        MachineLearning.get("classifier")  # → Classifier

    Because a layer is a ``Namespace`` subclass, ``@MachineLearning`` works
    exactly like ``@Component`` — no special decorator protocol is required.

    Inspecting registered layers::

        Layer.get("machine-learning")  # → MachineLearning
        dict(Layer.items())            # → all registered layers

    Built-in layers::

        @Storage
        @Service
        class Postgres: ...

        Layer.get("storage")        # → Storage
        Storage.get("postgres")     # → Postgres

    **No protocol on the layer-defining class**

    ``class MachineLearning(Namespace): ...`` inherits from ``Namespace`` so that
    ``@MachineLearning`` works as a decorator. The class body is always empty —
    there is nothing to implement. Classes tagged with a layer follow the execution
    type protocol (``Component``, ``Service``, ``Task``, ``Pipeline``); the layer
    itself adds only organisational membership.

    Raises:
        TypeError: If the decorated class does not inherit from ``Namespace``.
    """

    @overload
    def __new__(cls, _: type[Namespace]) -> type[Namespace]: ...
    @overload
    def __new__(cls, _: str | None = None, *, name: str | None = None) -> Self: ...
    def __new__(cls, _: type | str | None = None, *, name: str | None = None):
        """Dispatch like ``Namespace.__new__``, plus a ``Namespace``-subclass check.

        Bare decorator — argument is the class itself. Validates that it
        inherits from ``Namespace`` (a layer's values must themselves be
        namespaces), then delegates to ``Namespace.__new__`` to register and
        return it unchanged::

            @Layer
            class MachineLearning(Namespace): ...

        Factory decorator — argument is a name or nothing; delegates straight
        to ``Namespace.__new__``::

            @Layer("ml")
            class MachineLearning(Namespace): ...

        Args:
            _: The decorated class (bare form) or an explicit name / ``None``
                (factory form).
            name: Optional name to register under (factory form only).

        Raises:
            TypeError: If ``_`` is a class that does not inherit from
                ``Namespace``.
        """
        if isinstance(_, type):
            if not issubclass(_, Namespace):
                raise TypeError(f"{_.__name__} must inherit from Namespace to be used as a Layer")
            return super().__new__(cls, _)
        return super().__new__(cls, _, name=name)


@Layer
class Api(Namespace):
    """Built-in layer for components exposing external-facing interfaces."""


@Layer
class Storage(Namespace):
    """Built-in layer for components backing data storage."""


@Layer
class Analytics(Namespace):
    """Built-in layer for components computing metrics or aggregates."""


@Layer
class Messaging(Namespace):
    """Built-in layer for components handling queues or event streams."""


@Layer
class Monitoring(Namespace):
    """Built-in layer for components tracking system health or metrics."""


@Layer
class Security(Namespace):
    """Built-in layer for components handling auth, secrets, or policy."""
