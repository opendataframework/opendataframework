"""The ``@Component`` decorator and its optional structural capability protocols.

A component is the framework's default DI-managed class — resolved and
injected by the ``Context`` with no execution contract of its own. The
``*Protocol`` classes below are optional structural hooks a component may
implement to opt into lifecycle callbacks or inspection tooling.
"""

from typing import Protocol, runtime_checkable

from opendataframework.namespace import Namespace


@runtime_checkable
class OnStartProtocol(Protocol):
    """Capability interface for a ``Component``/``Repository``'s optional startup hook.

    Independent of ``OnStopProtocol`` — a class may define one, both, or
    neither; unlike ``ServiceProtocol``, nothing requires them to come as a
    pair. ``Context``'s ``Lifecycle`` uses
    ``isinstance(instance, OnStartProtocol)`` to call this once, in
    dependency order, during ``Context.open()``. Expected to return quickly.
    """

    def on_start(self) -> None:
        """Run blocking startup work, once, in dependency order during ``Context.open()``."""
        ...


@runtime_checkable
class OnStopProtocol(Protocol):
    """Capability interface for a ``Component``/``Repository``'s optional shutdown hook.

    Independent of ``OnStartProtocol`` — see there. ``Context``'s
    ``Lifecycle`` uses ``isinstance(instance, OnStopProtocol)`` to call this
    once, in reverse dependency order, during ``Context.close()``. Expected
    to return quickly.
    """

    def on_stop(self) -> None:
        """Run blocking teardown work, once, in reverse order during ``Context.close()``."""
        ...


@runtime_checkable
class DetailsProtocol(Protocol):
    """Capability interface for a Component's optional key/value details.

    Independent of ``OnStartProtocol``/``OnStopProtocol``. Unlike those, this
    is never called by ``Context`` during startup/shutdown — it's detected
    structurally via ``isinstance(instance, DetailsProtocol)`` and called on
    demand by whatever's inspecting the component, so values that only exist
    after startup (an assigned port, a generated URL) are reflected rather
    than frozen at resolve time. (Today, that's the sibling ``odf``
    package's UI.)
    """

    def details(self) -> dict[str, str]:
        """Return the component's current key/value details, computed fresh on each call."""
        ...


@runtime_checkable
class ChartProtocol(Protocol):
    """Capability interface for a Component's optional custom chart.

    Independent of ``DetailsProtocol``/``OnStartProtocol``/``OnStopProtocol``.
    Like ``details()``, ``chart()`` is never called by ``Context`` — it's
    detected structurally via ``isinstance(instance, ChartProtocol)`` and
    called on demand by whatever's inspecting the component, so the chart is
    rebuilt from live repository state on every call rather than frozen at
    resolve time.

    The component is free to use whatever Python charting library it likes
    (matplotlib, plotly, ...) — it just has to return a self-contained HTML
    document (inline image/JS, no external references), safe for a caller to
    embed verbatim. Keeping charting at the component level — rather than
    requiring a JS charting library on the consumer's side — means a chart
    keeps normal constructor-injected access to repositories and other
    components. (Today, the sibling ``odf`` package's UI is that caller: it
    serves the HTML from ``GET /api/components/{id}/chart`` and renders it
    in a same-origin ``<iframe>``.)
    """

    def chart(self) -> str:
        """Return a self-contained HTML document rendering the component's chart."""
        ...


class Component(Namespace):
    """Decorator that registers a class with the Context for dependency injection.

    ``@Component`` marks a class as a managed component — the ``Context``
    resolves its dependencies automatically from the constructor signature and
    calls its optional lifecycle hooks at the appropriate stage.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected.

    Basic usage::

        @Component
        class Classifier:

            def fit(self, data): ...
            def predict(self, data): ...

    With an explicit name::

        @Component(name="metrics-classifier")
        class Classifier:

            def fit(self, data): ...
            def predict(self, data): ...

    Dependency injection — dependencies are declared through the constructor
    and resolved automatically by the ``Context``::

        @Component
        class Report:

            def __init__(self, classifier: Classifier, metrics: Metrics):
                self.classifier = classifier
                self.metrics = metrics

    Looking up registered components::

        Component.get("Classifier")          # → Classifier class
        Component.get("metrics-classifier")  # → Classifier class (named)
        dict(Component.items())              # → all registered components
    """
