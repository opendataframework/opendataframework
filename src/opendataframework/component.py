"""The ``@Component`` decorator and its optional structural capability protocols.

A component is the framework's default DI-managed class — resolved and
injected by the ``Context`` with no execution contract of its own. The
``*Protocol`` classes below are optional structural hooks a component may
implement to opt into lifecycle callbacks or inspection tooling.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from opendataframework.namespace import ExecutionType


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


@dataclass
class McpTool:
    """One MCP tool a Component exposes, returned from ``mcp_tools()``.

    Attributes:
        name: The tool's local name — namespaced by whatever builds the
            tool surface (today, the sibling ``odf`` package's
            ``McpServer`` prefixes it with the component's kebab-case
            class name) to avoid collisions with the fixed built-in
            tools and with other components' tools.
        description: Human-readable description shown to the MCP client.
            Must not be empty.
        handler: The bound method implementing the tool call. Whoever
            calls the tool — typically a model — sees only its signature,
            so it must be fully typed: every parameter annotated, no
            ``*args``/``**kwargs``, a return annotation, and no annotation
            left as a string.
        structured_output: Whether the handler's return value should be
            reported as structured (JSON) output. ``None`` defers to
            the MCP server's own default behavior, mirroring how this
            field is expected to be forwarded verbatim by whatever
            registers the tool.

    Raises:
        ValueError: If ``description`` is empty.
        TypeError: If ``handler`` is not callable, has no readable
            signature, or is not fully typed.
    """

    name: str
    description: str
    handler: Callable[..., object]
    structured_output: bool | None = None

    def __post_init__(self) -> None:
        _require_tool(self)


def _require_tool(tool: McpTool) -> None:
    """Raise unless ``tool`` has a description and a fully typed handler.

    A tool is offered to a caller that sees nothing but its description
    and the handler's signature, so both are checked where the tool is
    created rather than left to surface as a poor schema.

    Raises:
        ValueError: If the description is empty.
        TypeError: If the handler is not callable, has no readable
            signature, or is not fully typed — naming every problem found.
    """
    if not tool.description.strip():
        raise ValueError(f"MCP tool {tool.name!r} has an empty description")
    if not callable(tool.handler):
        raise TypeError(f"MCP tool {tool.name!r}: handler {tool.handler!r} is not callable")
    try:
        signature = inspect.signature(tool.handler)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"MCP tool {tool.name!r}: the handler's signature cannot be read ({exc}) — "
            "wrap it in a function with annotated parameters"
        ) from exc
    problems: list[str] = []
    strings = False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            problems.append(f"*{parameter.name} is not allowed")
        elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
            problems.append(f"**{parameter.name} is not allowed")
        elif parameter.annotation is inspect.Parameter.empty:
            problems.append(f"parameter {parameter.name!r} is not annotated")
        elif isinstance(parameter.annotation, str):
            problems.append(f"parameter {parameter.name!r} has a string annotation")
            strings = True
    if signature.return_annotation is inspect.Signature.empty:
        problems.append("the return value is not annotated")
    elif isinstance(signature.return_annotation, str):
        problems.append("the return value has a string annotation")
        strings = True
    if not problems:
        return
    hint = (
        " — remove `from __future__ import annotations` from the module, or the quotes "
        "around the annotation"
        if strings
        else ""
    )
    raise TypeError(
        f"MCP tool {tool.name!r}: the handler must be fully typed, but "
        f"{'; '.join(problems)}{hint}"
    )


@runtime_checkable
class McpToolsProtocol(Protocol):
    """Capability interface for a Component's optional custom MCP tools.

    Independent of ``DetailsProtocol``/``ChartProtocol``/
    ``OnStartProtocol``/``OnStopProtocol``. Never invoked by ``Context``
    — detected structurally via ``isinstance(instance, McpToolsProtocol)``
    and consumed on demand by whatever builds an MCP tool surface. (Today,
    that's the sibling ``odf`` package's ``McpServer``, which registers
    each returned ``McpTool`` under
    ``<kebab(cls.__name__)>.<tool.name>``, alongside its six fixed
    built-in tools.)
    """

    def mcp_tools(self) -> list[McpTool]:
        """Return the component's custom MCP tools, in addition to the fixed built-in surface."""
        ...


class Component(ExecutionType):
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
