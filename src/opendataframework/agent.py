"""The ``@Agent`` decorator — the framework's marker for agentic work.

An agent is a class that pursues a goal it is handed at call time, usually
by driving a model in a loop. The framework owns none of that loop: it
registers the class, injects what the agent may act on through its
constructor, and gives the ``Context`` one method — ``invoke()`` — to call
and log.
"""

from typing import Protocol, runtime_checkable

from opendataframework.namespace import Namespace


@runtime_checkable
class AgentProtocol(Protocol):
    """Expected interface for classes registered with ``@Agent``.

    An agent implements a single method that pursues a goal and returns a
    result. Unlike ``TaskProtocol.execute()``, ``invoke()`` takes arguments —
    whatever the agent's author declares. Being ``@runtime_checkable``, an
    ``isinstance`` check confirms only that ``invoke`` is present, not its
    signature.
    """

    def invoke(self, *args, **kwargs):
        """Pursue the goal described by the arguments and return a result, or ``None``."""
        ...


class Agent(Namespace):
    """Decorator that registers an agentic class with the Context.

    ``@Agent`` marks a class as a managed agent — a finite, explicitly
    invoked unit of work whose steps are decided at run time rather than
    written down in advance. The ``Context`` creates it and injects its
    dependencies like any other class, and calls its ``invoke()`` method by
    name through ``Context.call()``.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected.

    Basic usage — ``invoke()`` takes whatever arguments the agent needs::

        @Agent
        class Librarian:

            def invoke(self, question: str) -> str:
                ...

    With an explicit name::

        @Agent(name="librarian")
        class CatalogueAssistant:
            ...

    Dependency injection — the constructor declares everything the agent may
    act on, so its reach is visible in the dependency graph::

        @Agent
        class Librarian:

            def __init__(self, books: Books, model: Model):
                self.books = books
                self.model = model

            def invoke(self, question: str) -> str:
                ...

        project.context.call("librarian", question="Anything by Herbert?")
        project.context.get(Librarian).invoke("Anything by Herbert?")

    The framework ships no model client and no loop. ``invoke()`` is where an
    agentic library, a provider SDK, or hand-written logic goes; the model
    itself is usually another injected component.

    Looking up registered agents::

        Agent.get("Librarian")   # → Librarian class
        Agent.get("librarian")   # → Librarian class
        dict(Agent.items())      # → all registered agents

    Raises:
        TypeError: If the decorated object is not a class, or is a class that
            does not define ``invoke()``.
    """

    @classmethod
    def _register(cls, key: str, wrapped) -> None:
        """Store ``wrapped`` under ``key``, requiring it to define ``invoke()``.

        Raises:
            TypeError: If ``wrapped`` has no callable ``invoke``.
            ValueError: If ``key`` is already registered in this namespace.
        """
        if not callable(getattr(wrapped, "invoke", None)):
            raise TypeError(
                f"{cls.__name__} can only decorate a class that defines invoke(), "
                f"got {wrapped.__name__!r}"
            )
        super()._register(key, wrapped)
