"""The ``@Entity`` decorator — the framework's structured-data marker.

An entity is a plain data shape (typically a dataclass) passed between
components, tasks, pipelines, and repositories. It carries no behavior,
no lifecycle, and is not managed by the ``Context``.
"""

from opendataframework.namespace import Namespace


class Entity(Namespace):
    """Decorator that registers a class as a named data structure.

    ``@Entity`` marks a class as a structured unit of data — the common
    language passed between components, tasks, pipelines, and repositories.
    It is a marker only: the decorated class is returned unchanged, no base
    class is added, and no methods are injected.

    Entities are not managed by the ``Context`` and do not participate in
    dependency injection or lifecycle. They are data shapes, not components.

    Basic usage with a dataclass::

        @Entity
        @dataclass
        class User:
            id: int
            name: str
            email: str

    With an explicit name::

        @Entity(name="user")
        @dataclass
        class User:
            id: int
            name: str
            email: str

    Linking an entity to its repository::

        @Repository(User)
        class Users:

            def get(self, user_id: int) -> User: ...
            def save(self, user: User) -> None: ...

    Looking up registered entities::

        Entity.get("user")        # → User class
        dict(Entity.items())      # → all registered entities
    """
