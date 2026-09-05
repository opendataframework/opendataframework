# Pipeline

A `Pipeline` is an executable that coordinates multiple [Tasks](task.md) — and
optionally other `Pipelines` — into a single, ordered workflow. Wired through dependency
injection the same way as a [Component](component.md), it represents the execution flow
of a data process from start to finish.

Pipelines answer one question:

> In what order does the work happen?

Unlike a [Task](task.md), a `Pipeline` does not perform work itself. It delegates to the tasks
and pipelines it depends on, defines the order they run in, and optionally aggregates
their results.

---

## When to use Pipeline

Use `@Pipeline` when a process consists of multiple steps that need to run in sequence
or depend on each other's results.

Typical examples:

* ETL workflows
* daily analytics runs
* model training workflows
* deployment pipelines
* ML experiment pipelines

If the work is a single bounded step, use [Task](task.md) instead.

---

## Decorator

The `@Pipeline` decorator registers the class into the `Pipeline` namespace as an
executable orchestration component. The `Context` reads from this namespace at
startup. The class is returned unchanged.

### Without arguments

```python
@Pipeline
class DailyAnalytics:
    ...
```

### With a name

```python
@Pipeline(name="daily-analytics")
class DailyAnalyticsIngestAndReportingPipeline:
    ...
```

### Combined with a Layer

```python
@Analytics
@Pipeline
class DailyAnalytics:
    ...
```

---

## Interface

A `Pipeline` implements a single method — `execute()`. It may return a value or `None`.

```python
@Pipeline
class DailyAnalytics:

    def execute(self):
        # coordinate tasks and sub-pipelines
        # return a result, or None
        ...
```

---

## Dependency Injection

Tasks and sub-pipelines are declared as constructor dependencies. The `Context` resolves
and injects them automatically — including their own dependencies.

```python
@Analytics
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
        self.fetcher.execute()
        self.trainer.execute()
        self.report.execute()
```

---

## Composing Pipelines

A `Pipeline` can depend on other `Pipelines` the same way it depends on `Tasks` — through
the constructor. This allows complex workflows to be built from smaller, reusable pipelines.

```python
@Analytics
@Pipeline
class IngestPipeline:

    def __init__(
        self,
        fetcher: MetricsFetcher,
        validator: Validator,
        metrics: Metrics,
    ):
        self.fetcher = fetcher
        self.validator = validator
        self.metrics = metrics

    def execute(self):
        data = self.fetcher.execute()
        self.validator.validate(data)
        self.metrics.save(data)


@Analytics
@Pipeline
class TrainPipeline:

    def __init__(
        self,
        trainer: ModelTrainer,
        report: ReportGenerator,
    ):
        self.trainer = trainer
        self.report = report

    def execute(self):
        self.trainer.execute()
        self.report.execute()


@Analytics
@Pipeline
class DailyAnalytics:

    def __init__(
        self,
        ingest: IngestPipeline,
        train: TrainPipeline,
    ):
        self.ingest = ingest
        self.train = train

    def execute(self):
        self.ingest.execute()
        self.train.execute()
```

Each sub-pipeline is independently testable and reusable across other pipelines.

!!! tip "fit() mutates the one shared Classifier instance"
    `TrainPipeline`'s `trainer: ModelTrainer` internally calls
    `self.classifier.fit(data)` — see the [Full Example](#full-example) below
    for its body. `Context` creates exactly one `Classifier` instance for the
    whole application lifetime (see
    [Component](component.md#what-component-is-not)), so that call mutates
    the single shared instance, not a private copy. Anything else `Classifier`
    is injected into (a prediction task, an API endpoint) sees the same,
    now-fitted object.

---

## Full Example

A complete analytics pipeline wiring together fetch, train, and report steps —
including the `Task`s it coordinates, in full:

```python
@Analytics
@Task
class MetricsFetcher:

    def __init__(self, config: Config, metrics: Metrics):
        self.config = config
        self.metrics = metrics

    def execute(self):
        data = self._fetch(self.config.source_url)
        self.metrics.save(data)

    def _fetch(self, url):
        ...


@Analytics
@Task
class ModelTrainer:

    def __init__(self, config: Config, classifier: Classifier, metrics: Metrics):
        self.config = config
        self.classifier = classifier
        self.metrics = metrics

    def execute(self):
        data = self.metrics.load(self.config.training_dataset)
        self.classifier.fit(data)


@Analytics
@Task
class ReportGenerator:

    def __init__(self, config: Config, metrics: Metrics):
        self.config = config
        self.metrics = metrics

    def execute(self):
        data = self.metrics.load(self.config.report_period)
        report = self._build(data)
        self._export(report, self.config.output_path)
        return report

    def _build(self, data):
        ...

    def _export(self, report, path):
        ...


@Analytics
@Pipeline
class DailyAnalytics:

    def __init__(
        self,
        fetcher: MetricsFetcher,
        trainer: ModelTrainer,
        report: ReportGenerator,
        config: Config,
    ):
        self.fetcher = fetcher
        self.trainer = trainer
        self.report = report
        self.config = config

    def execute(self):
        self.fetcher.execute()
        self.trainer.execute()
        return self.report.execute()
```

Running it through the `Context`, by class name:

```python
result = project.context.execute("DailyAnalytics")
```

---

## Protocol

`PipelineProtocol` documents the expected interface and is available for type
checking and introspection:

```python
from opendataframework import PipelineProtocol

isinstance(instance, PipelineProtocol)  # True if execute() is present
```

`PipelineProtocol` is `@runtime_checkable`. The `Context` uses it to verify that a
registered class implements `execute()` before calling it.

```python
class PipelineProtocol(Protocol):
    def execute(self): ...
```

---

## Failure Handling

Failure handling within a pipeline is not defined by the framework at this stage.
If a step raises an exception, it propagates naturally. Hooks for logging, retrying,
or aggregating results across steps may be introduced in a future version.

---

## What Pipeline is Not

* **Not a task.** A `Pipeline` does not perform work itself — it delegates to tasks and
  sub-pipelines. If the work is a single step, use [Task](task.md).

* **Not a scheduler.** A `Pipeline` executes when called. Scheduling — running it on a
  timer or trigger — is the responsibility of a [Service](service.md) such as a `Scheduler`.

* **Not a base class.** `DailyAnalytics` does not inherit from `Pipeline`. The decorator
  registers it; inheritance is not involved.

---

## Decision Guide

| I need to...                              | Use         |
| ----------------------------------------- | ----------- |
| Provide a reusable capability             | [Component](component.md) |
| Run a process indefinitely                | [Service](service.md)   |
| Execute a bounded unit of work once       | [Task](task.md)      |
| Coordinate multiple tasks into a workflow | `Pipeline`  |
| Manage persistent data                    | [Repository](repository.md)|
