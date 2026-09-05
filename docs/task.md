# Task

A `Task` is a finite executable — wired through dependency injection the same way as a
[Component](component.md), but with a single `execute()` contract the `Context` calls
once. It represents a bounded unit of work that runs once, produces a result, and
completes. Unlike a [Service](service.md), it does not run indefinitely. Unlike a
[Pipeline](pipeline.md), it does not coordinate other tasks.

Tasks answer one question:

> What work needs doing, once?

---

## When to use Task

Use `@Task` when a class needs to:

* perform a single, well-defined unit of work
* optionally produce a result
* run to completion and stop

Typical examples:

* fetching data from an external source
* generating a report
* training or evaluating a model
* sending a notification
* exporting data to storage

---

## Decorator

The `@Task` decorator registers the class into the `Task` namespace as a finite
executable component. The `Context` reads from this namespace at startup. The class
is returned unchanged.

### Without arguments

```python
@Task
class MetricsFetcher:
    ...
```

### With a name

```python
@Task(name="metrics-fetcher")
class DailySalesMetricsFetcher:
    ...
```

### Combined with a Layer

```python
@Analytics
@Task
class MetricsFetcher:
    ...
```

---

## Interface

A `Task` implements a single method — `execute()`. It may return a value or `None`.

```python
@Task
class MetricsFetcher:

    def execute(self):
        # perform the work
        # return a result, or None if the task has only side effects
        ...
```

---

## Dependency Injection

Like all components, a `Task` declares its dependencies through the constructor:

```python
@Analytics
@Task
class MetricsFetcher:

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
    ):
        self.config = config
        self.metrics = metrics

    def execute(self):
        data = self._fetch(self.config.source_url)
        self.metrics.save(data)
        return data

    def _fetch(self, url):
        ...
```

---

## Full Examples

### Data collection

```python
@Analytics
@Task
class MetricsFetcher:

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
    ):
        self.config = config
        self.metrics = metrics

    def execute(self):
        data = self._fetch(self.config.source_url)
        self.metrics.save(data)
        return data

    def _fetch(self, url):
        ...
```

### Model training

```python
@Analytics
@Task
class ModelTrainer:

    def __init__(
        self,
        config: Config,
        classifier: Classifier,
        metrics: Metrics,
    ):
        self.config = config
        self.classifier = classifier
        self.metrics = metrics

    def execute(self):
        data = self.metrics.load(self.config.training_dataset)
        self.classifier.fit(data)
```

### Report generation

```python
@Analytics
@Task
class ReportGenerator:

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
    ):
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
```

---

## Using a Task

A `Task` is resolved and executed through the `Context`, by class name:

```python
data = project.context.execute("MetricsFetcher")
```

Or directly within a `Pipeline` that coordinates multiple tasks:

```python
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
        return self.report.execute()
```

---

## Protocol

`TaskProtocol` documents the expected interface and is available for type checking
and introspection:

```python
from opendataframework import TaskProtocol

isinstance(instance, TaskProtocol)  # True if execute() is present
```

`TaskProtocol` is `@runtime_checkable`. The `Context` uses it to verify that a
registered class implements `execute()` before calling it.

```python
class TaskProtocol(Protocol):
    def execute(self): ...
```

---

## What Task is Not

* **Not a long-running process.** A `Task` runs to completion. If the work needs to run
  indefinitely, use a [Service](service.md).

* **Not an orchestrator.** If the work involves coordinating multiple tasks, use a
  [Pipeline](pipeline.md).

* **Not required to return a value.** `execute()` may return `None` when the task
  produces only side effects — saving to storage, sending a notification, writing a file.

* **Not a base class.** `MetricsFetcher` does not inherit from `Task`. The decorator
  registers it; inheritance is not involved.

---

## Decision Guide

| I need to...                              | Use         |
| ----------------------------------------- | ----------- |
| Provide a reusable capability             | [Component](component.md) |
| Run a process indefinitely                | [Service](service.md)   |
| Execute a bounded unit of work once       | `Task`      |
| Coordinate multiple tasks into a workflow | [Pipeline](pipeline.md)  |
| Manage persistent data                    | [Repository](repository.md)|
