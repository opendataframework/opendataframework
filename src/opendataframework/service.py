"""The ``@Service`` decorator — the framework's long-running executable marker.

A service is a component with a mandatory three-stage lifecycle
(``setup`` → ``run`` → ``stop``); the ``Context`` backgrounds ``run()`` in
a thread automatically so a service author never manages threading.
"""

from typing import Protocol, runtime_checkable

from opendataframework.namespace import Namespace


@runtime_checkable
class ServiceProtocol(Protocol):
    """Expected interface for classes registered with ``@Service``.

    All three methods must be defined. The ``Context`` uses
    ``isinstance(instance, ServiceProtocol)`` to distinguish services from
    components and calls every stage unconditionally.

    ``run()`` is blocking by nature. The framework spawns it in a background
    thread automatically; the service author never manages threading directly.
    """

    def setup(self) -> None:
        """Run blocking setup work once, before ``run()`` starts."""
        ...

    def run(self) -> None:
        """Block and serve; run by the framework in a background thread."""
        ...

    def stop(self) -> None:
        """Release resources and shut down gracefully."""
        ...


class Service(Namespace):
    """Decorator that registers a long-running executable class with the Context.

    ``@Service`` marks a class as a managed service — the ``Context`` drives its
    three-stage lifecycle: ``setup → run → stop``. All three methods must be
    defined; stages with no work can be left as ``pass`` (or ``...``).

    ``run()`` is blocking by nature. The framework automatically spawns it in a
    background thread so startup can continue to the next component. The service
    author never manages threading directly.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected.

    Basic usage::

        @Service
        class Postgres:

            def setup(self):
                self.pool = self._create_pool()

            def run(self):
                self.pool.serve()

            def stop(self):
                self.pool.close()

    With an explicit name (positional)::

        @Service("postgres")
        class Postgres:
            ...

    With an explicit name (keyword)::

        @Service(name="postgres")
        class Postgres:
            ...

    Lifecycle contract::

        setup()  — blocking setup: pull images, run migrations, open connections
        run()    — block and serve (framework runs this in a background thread)
        stop()   — release resources and shut down gracefully

    Looking up registered services::

        Service.get("Postgres")   # → Postgres class
        Service.get("postgres")   # → Postgres class registered under a custom name
        dict(Service.items())     # → all registered services
    """
