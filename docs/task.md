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
class MetricsFetcher: ...
```

### With a name

```python
@Task(name="metrics-fetcher")
class DailySalesMetricsFetcher: ...
```

### Combined with a Layer

```python
@Analytics
@Task
class MetricsFetcher: ...
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
        self.config = config.task.metrics_fetcher
        self.metrics = metrics

    def execute(self):
        data = self._fetch(self.config.source_url)
        self.metrics.save(data)
        return data

    def _fetch(self, url): ...
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
        self.config = config.task.metrics_fetcher
        self.metrics = metrics

    def execute(self):
        data = self._fetch(self.config.source_url)
        self.metrics.save(data)
        return data

    def _fetch(self, url): ...
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
        self.config = config.task.model_trainer
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
        self.config = config.task.report_generator
        self.metrics = metrics

    def execute(self):
        data = self.metrics.load(self.config.report_period)
        report = self._build(data)
        self._export(report, self.config.output_path)
        return report

    def _build(self, data): ...

    def _export(self, report, path): ...
```

---

## Using a Task

A `Task` is resolved and executed through the `Context`, by its [key](context.md#by-key-single-component-control):

```python
data = project.context.execute("task.metrics-fetcher")
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

Every `execute()` call is also reported as an
[event](events.md#which-protocols-emit-events), as a `TaskProtocol` call.

---

## Task, Function or Agent?

The `Context` can run all three by key. What separates them is who decides the input:

| Who decides the input                                                              | Use                     | Run with                      |
| ---------------------------------------------------------------------------------- | ----------------------- | ----------------------------- |
| Nobody at call time: it is fixed when the project is assembled, through the constructor and [Config](config.md) | `Task`                  | `context.execute(key)`        |
| The caller, on every call                                                          | [Function](function.md) | `context.call(key, **kwargs)` |
| The caller, who hands over a goal; the steps are decided at run time               | [Agent](agent.md)       | `context.call(key, **kwargs)` |

`execute()` takes no arguments on purpose. Because a task needs nothing from its
caller, anything can run it (a pipeline, a scheduler, the CLI, a UI) without knowing
anything about it. A task that took arguments would be a function written as a class,
and choosing between the two would come down to taste.

### When the work needs per-run input

Sooner or later a task wants a value that changes between runs, such as the day to
backfill or the tenant to reprocess. Don't change `Config` at run time or set a
module-level variable to get it there. Both are hidden dependencies, and the second is
global state. Instead, choose by where the value comes from:

* **The caller picks it each time.** The work is a [Function](function.md). A task can
  still cover the usual case by injecting the function and passing the value itself:

    ```python
    @Function
    def backfill_orders(orders: Orders, day: date) -> int: ...


    @Task
    class DailyOrders:
        def __init__(self, backfill: Annotated[Callable[[date], int], backfill_orders]):
            self.backfill = backfill

        def execute(self) -> int:
            return self.backfill(date.today() - timedelta(days=1))
    ```

    ```python
    project.context.execute("task.daily-orders")  # the scheduled run: yesterday
    project.context.call("function.backfill-orders", day=date(2026, 10, 1))  # a one-off
    ```

* **It differs per deployment or environment.** It's configuration. Start the project
  from a different config path (see [Config](config.md)).

* **It follows from what earlier runs did**, such as a watermark, a cursor or the last
  day processed. It's state. Keep it in a [Repository](repository.md) that the task
  reads at the start of `execute()` and updates at the end.

---

## What Task is Not

* **Not called with arguments.** `execute()` takes none, and `Context.execute()` passes
  none. Work that needs input from its caller is a [Function](function.md); see
  [Task, Function or Agent?](#task-function-or-agent).

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
| Execute a bounded unit of work once, no arguments | `Task` |
| Call a unit of work with arguments        | [Function](function.md) |
| Coordinate multiple tasks into a workflow | [Pipeline](pipeline.md)  |
| Work towards a goal handed over at call time | [Agent](agent.md) |
| Manage persistent data                    | [Repository](repository.md)|
