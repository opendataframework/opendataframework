"""The ``@Pipeline`` decorator — the framework's task-orchestration marker.

A pipeline coordinates tasks and sub-pipelines into an ordered workflow;
unlike a ``Task``, it performs no work itself, only delegation.
"""

from typing import Protocol, runtime_checkable

from opendataframework.namespace import Namespace


@runtime_checkable
class PipelineProtocol(Protocol):
    """Expected interface for classes registered with ``@Pipeline``.

    A pipeline implements a single method that coordinates tasks and
    sub-pipelines, returning a result or ``None``.
    """

    def execute(self):
        """Coordinate the pipeline's tasks/sub-pipelines and return a result, or ``None``."""
        ...


class Pipeline(Namespace):
    """Decorator that registers an orchestration class with the Context.

    ``@Pipeline`` marks a class as a managed pipeline — an ordered composition
    of tasks and sub-pipelines that runs as a single workflow. Unlike a
    ``Task``, a pipeline does not perform work itself; it delegates to the
    tasks and pipelines it depends on.

    The decorated class is returned unchanged. No base class is added and no
    methods are injected.

    Basic usage::

        @Pipeline
        class DailyAnalytics:

            def execute(self):
                ...

    With an explicit name::

        @Pipeline(name="daily-analytics")
        class DailyAnalytics:
            ...

    Composing tasks via dependency injection::

        @Pipeline
        class DailyAnalytics:

            def __init__(
                self,
                fetcher: MetricsFetcher,
                trainer: ModelTrainer,
                report: ReportGenerator,
            ):
                self.fetcher = fetcher
                self.trainer = trainer
                self.report = report

            def execute(self):
                data = self.fetcher.execute()
                model = self.trainer.execute()
                return self.report.execute()

    Composing sub-pipelines::

        @Pipeline
        class FullWorkflow:

            def __init__(self, ingest: IngestPipeline, train: TrainPipeline):
                self.ingest = ingest
                self.train = train

            def execute(self):
                self.ingest.execute()
                return self.train.execute()

    Looking up registered pipelines::

        Pipeline.get("DailyAnalytics")    # → DailyAnalytics class
        Pipeline.get("daily-analytics")   # → DailyAnalytics class registered under a custom name
        dict(Pipeline.items())            # → all registered pipelines
    """
