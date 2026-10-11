"""The ``@Layer`` decorator and the framework's built-in architectural layers.

A layer is a ``Namespace`` whose values are themselves ``Namespace``
subclasses — it groups components into named subsystems (``Api``,
``Storage``, ``Analytics``, ...) with no runtime behavior of its own.
"""

from opendataframework.namespace import ClassNamespace, Namespace, describe


class Layer(ClassNamespace):
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

    Because a layer is a ``Namespace`` subclass, ``@MachineLearning`` is
    applied like ``@Component`` — no special decorator protocol is required.

    A layer tags what is already registered: a class under an execution type
    (``@Component``, ``@Service``, ...) or a function under ``@Function``. So
    the layer goes on top, and a bare class or function raises ``TypeError``::

        @MachineLearning
        @Function
        def score(model: Model) -> float: ...

        @MachineLearning
        class Classifier: ...        # TypeError — no execution type under it

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

    @classmethod
    def _require(cls, wrapped: object) -> None:
        """Raise ``TypeError`` unless ``wrapped`` is a ``Namespace`` subclass.

        A layer's values must themselves be namespaces.
        """
        super()._require(wrapped)
        if not issubclass(wrapped, Namespace):
            raise TypeError(f"{wrapped.__name__} must inherit from Namespace to be used as a Layer")

    @classmethod
    def _register(cls, key: str, wrapped) -> None:
        """Store the layer class and give it the rule for what it may tag.

        A layer's body is empty, so the rule cannot be written on the layer
        itself — it is set here, when the class becomes a layer.
        """
        super()._register(key, wrapped)
        wrapped._require = classmethod(_require_registered)


def _namespaces() -> list[type[Namespace]]:
    """Return every ``Namespace`` subclass defined so far, at any depth."""
    found: list[type[Namespace]] = []
    stack = list(Namespace.__subclasses__())
    while stack:
        namespace = stack.pop()
        if namespace not in found:
            found.append(namespace)
            stack.extend(namespace.__subclasses__())
    return found


def _require_registered(cls: type[Namespace], wrapped: object) -> None:
    """Raise ``TypeError`` unless ``wrapped`` is already registered outside the layers.

    The ``_require`` of every layer: a layer is an organisational tag, so it
    accepts only what some other namespace — an execution type, ``Function``
    — has registered. That makes the layer decorator the outer one.
    """
    layers = set(Layer._namespace.values())
    for namespace in _namespaces():
        if namespace is Layer or namespace in layers:
            continue
        if any(wrapped is member for member in namespace._namespace.values()):
            return
    raise TypeError(
        f"{cls.__name__} is a layer and can only tag a registered class or function, "
        f"got {describe(wrapped)} — put an execution type under it (@Component, "
        f"@Service, ...; @Function for a function), with @{cls.__name__} on top"
    )


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
