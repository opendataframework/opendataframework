"""The ``@Task`` decorator — the framework's finite unit-of-work marker.

A task performs a single, bounded piece of work when explicitly called,
as opposed to a ``Service``'s open-ended background execution.
"""

from typing import Protocol, runtime_checkable

from opendataframework.namespace import Namespace


@runtime_checkable
class TaskProtocol(Protocol):
    """Expected interface for classes registered with ``@Task``.

    A task implements a single method that performs a bounded unit of work and
    returns a result or ``None``.
    """

    def execute(self):
        """Perform the task's bounded unit of work and return a result, or ``None``."""
        ...


class Task(Namespace):
    """Decorator that registers a finite executable class with the Context.

    ``@Task`` marks a class as a managed task — a bounded unit of work that
    runs once, optionally produces a result, and completes. The ``Context``
    creates and injects its dependencies automatically.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected.

    Basic usage::

        @Task
        class MetricsFetcher:

            def execute(self):
                ...

    With an explicit name::

        @Task(name="metrics-fetcher")
        class MetricsFetcher:
            ...

    With dependency injection::

        @Task
        class MetricsFetcher:

            def __init__(self, config: Config, metrics: Metrics):
                self.config = config
                self.metrics = metrics

            def execute(self):
                data = self._fetch(self.config.source_url)
                self.metrics.save(data)
                return data

    Looking up registered tasks::

        Task.get("MetricsFetcher")    # → MetricsFetcher class
        Task.get("metrics-fetcher")   # → MetricsFetcher class registered under a custom name
        dict(Task.items())            # → all registered tasks
    """
