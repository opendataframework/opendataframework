"""The ``@Repository`` decorator and its structural capability protocols.

A repository is the framework's data-access boundary — it links a managed
class to the entity it manages and is resolved/injected by the ``Context``
like any other component. Which operations a repository supports
(``all()``, ``save()``/``delete()``, ``stream()``, ...) is detected
structurally via the ``*Protocol`` classes below, not declared through
inheritance.
"""

from collections.abc import Iterator
from typing import Any, Protocol, TypeVar, runtime_checkable

from opendataframework.namespace import C, Namespace

E = TypeVar("E")


@runtime_checkable
class ReadableProtocol(Protocol[E]):
    """Capability interface for repositories that support querying.

    A repository implementing ``all()`` can be listed. Tooling (e.g. the dev
    UI) uses ``isinstance(repo, ReadableProtocol)`` to detect this capability
    without requiring every repository to implement it — per
    ``docs/repository.md``, read-only and write-only repositories are
    equally valid.
    """

    def all(self) -> list[E]:
        """Return every entity managed by this repository."""
        ...


@runtime_checkable
class WritableProtocol(Protocol[E]):
    """Capability interface for repositories that support mutation.

    ``save()`` both creates and updates — pass an entity with an unset
    identifier to create, or an existing entity to update. Tooling uses
    ``isinstance(repo, WritableProtocol)`` to detect this capability.
    """

    def save(self, entity: E) -> None:
        """Create ``entity`` if its identifier is unset, otherwise update it."""
        ...

    def delete(self, id: Any) -> None:
        """Delete the entity matching ``id``."""
        ...


@runtime_checkable
class StreamableProtocol(Protocol[E]):
    """Capability interface for repositories backed by a live, unbounded feed.

    Unlike ``all()``, ``stream()`` has no notion of "every record" — it
    yields entities as they arrive (webcam frames, sensor readings, a queue
    subscription) for as long as the caller keeps iterating. Tooling uses
    ``isinstance(repo, StreamableProtocol)`` to detect this capability, the
    same way it detects ``Readable``/``Writable``.
    """

    def stream(self) -> Iterator[E]:
        """Yield entities as they arrive, for as long as the caller keeps iterating."""
        ...


@runtime_checkable
class OpenStreamProtocol(Protocol):
    """Capability interface for a stream's optional resource-acquisition hook.

    Independent of ``CloseStreamProtocol`` — see there. ``StreamManager``
    uses ``isinstance(instance, OpenStreamProtocol)`` to call this once,
    blocking, before spawning the background thread that drives
    ``stream()`` — the streaming analogue of a ``Service``'s ``setup()``
    ahead of its backgrounded ``run()``. A repository streaming from an
    already-open resource (a queue, a socket handed in via the constructor)
    needs neither hook.
    """

    def open_stream(self) -> None:
        """Acquire the resource ``stream()`` will read from, once, before streaming starts."""
        ...


@runtime_checkable
class CloseStreamProtocol(Protocol):
    """Capability interface for a stream's optional resource-release hook.

    Independent of ``OpenStreamProtocol`` — see there. ``StreamManager``
    uses ``isinstance(instance, CloseStreamProtocol)`` to call this once the
    background thread driving ``stream()`` has fully exited — whether that's
    because ``stop_stream()`` was called, the source exhausted itself (e.g.
    a device disconnecting), or ``stream()`` raised.
    """

    def close_stream(self) -> None:
        """Release the resource ``stream()`` read from, once the background thread has exited."""
        ...


class Repository(Namespace):
    """Decorator that registers a class as a data-access repository.

    ``@Repository(Entity)`` links a repository class to the entity it manages
    and registers it for dependency injection. The entity relationship is
    explicit and inspectable — no inheritance required.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected. The interface (``get``, ``all``, ``save``,
    ``delete``, etc.) is defined by the repository itself — only the
    operations relevant to the data source need to be implemented.

    Basic usage::

        @Repository(User)
        class Users:

            def get(self, user_id: int) -> User: ...
            def save(self, user: User) -> None: ...

    With an explicit name::

        @Repository(User, name="users")
        class Users: ...

    Combined with a layer::

        @Storage
        @Repository(User)
        class Users: ...

    Dependencies are declared through the constructor and injected
    automatically by the ``Context``::

        @Storage
        @Repository(User)
        class Users:

            def __init__(self, postgres: Postgres):
                self.postgres = postgres

    Looking up registered repositories::

        Repository.get("users")          # → Users class
        Repository.entity(Users)         # → User class
        dict(Repository.items())         # → all registered repositories
    """

    _entity_map: dict[type, type] = {}

    def __new__(cls, entity: type, *, name: str | None = None) -> Repository:
        """Always return a ``Repository`` instance for factory decorator use.

        Bypasses ``Namespace.__new__``'s bare-decorator branch — the first
        argument is always an entity class, never the class being decorated.

        Args:
            entity: The ``Entity`` class this repository manages.
            name: Optional explicit registration name.

        Returns:
            A new ``Repository`` instance to be used as a decorator.
        """
        return object.__new__(cls)

    def __init__(self, entity: type, *, name: str | None = None) -> None:
        """Store the managed entity and optional registration name.

        Args:
            entity: The ``Entity`` class this repository manages.
            name: Optional explicit registration name. Defaults to the
                kebab-case form of the decorated class name.
        """
        super().__init__(name=name)
        self._entity = entity

    def __call__(self, wrapped: type[C]) -> type[C]:
        """Register the repository class and record its entity relationship.

        Args:
            wrapped: The repository class being decorated.

        Returns:
            The original class, unmodified.
        """
        super().__call__(wrapped)
        self.__class__._entity_map[wrapped] = self._entity
        return wrapped

    @classmethod
    def entity(cls, repository_cls: type) -> type | None:
        """Return the entity class managed by ``repository_cls``.

        Args:
            repository_cls: A registered repository class.

        Returns:
            The entity class passed to ``@Repository(...)``, or ``None`` if
            ``repository_cls`` is not registered.

        Example::

            @Repository(User)
            class Users: ...

            Repository.entity(Users)  # → User
        """
        return cls._entity_map.get(repository_cls)
