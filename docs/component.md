# Component

A `Component` is a Python class registered in the `Component` namespace via the
`@Component` decorator — the foundational building block of the framework. Decorating
a class with `@Component` is what makes it participate in dependency injection; the
`Context` reads this namespace at startup to build the dependency graph and create
instances.

`Component` carries no execution contract. It does not require specific methods to be
implemented. Its role is to be wired into the system, receive its dependencies through
the constructor, and provide whatever capability it encapsulates.

---

## When to use Component

Use `@Component` when a class provides a reusable capability that:

* does not need to run indefinitely (that is a [Service](service.md))
* does not execute a single bounded unit of work (that is a [Task](task.md))
* does not coordinate other tasks (that is a [Pipeline](pipeline.md))

If none of the above apply, it is a `Component`.

Typical examples:

* a model wrapper (fit, predict)
* a data validator
* a feature transformer
* a notification sender
* a configuration reader
* a client wrapper around an external API

---

## Decorator

The `@Component` decorator registers the class into the `Component` namespace at
definition time and marks it for dependency injection and lifecycle participation.
The class itself is returned unchanged — no base class is added, no methods are injected.

### Without arguments

```python
@Component
class Classifier:

    def fit(self, data):
        ...

    def predict(self, data):
        ...
```

### With a name

An optional name can be provided to register the component under something shorter
than the kebab-case form of its class name — useful when the class name is long and
you'd rather look it up by a short alias via `Component.get(...)`.

```python
@Component(name="churn-risk")
class CustomerChurnRiskClassifier:

    def fit(self, data):
        ...

    def predict(self, data):
        ...
```

### Combined with a Layer

`@Component` is often stacked with a layer decorator to indicate which subsystem the
component belongs to. Layer comes first (outermost), component type second:

```python
@Analytics
@Component
class Classifier:

    def fit(self, data):
        ...

    def predict(self, data):
        ...
```

---

## Dependency Injection

Dependencies are declared through the constructor. The `Context` resolves and injects
them automatically when the component is created.

```python
@Analytics
@Component
class Report:

    def __init__(
        self,
        classifier: Classifier,
        metrics: Metrics,
    ):
        self.classifier = classifier
        self.metrics = metrics

    def build(self, data):
        prediction = self.classifier.predict(data)
        self.metrics.save(prediction)
        ...
```

No service locators. No imports of global registries. The constructor signature is the
complete and readable description of what this component needs.

---

## Full Example

A realistic component in a data analytics project:

```python
@Analytics
@Component
class Classifier:

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
    ):
        self.config = config
        self.metrics = metrics
        self.model = self._load_model(config.model_path)

    def fit(self, data):
        self.model.fit(data)
        self.metrics.save_training_run(data)

    def predict(self, data):
        return self.model.predict(data)

    def _load_model(self, path):
        ...
```

---

## Namespace

`Component` is a namespace — a named scope that maps registration names to classes.
Two class methods are available for inspection:

```python
Component.get("Classifier")          # → Classifier class, or None if not registered
Component.get("metrics-classifier")  # → Classifier class registered under a custom name

dict(Component.items())              # → {"classifier": Classifier, ...}
```

!!! tip "get() accepts any name form"
    `.get()` normalizes its argument before looking it up, so PascalCase
    (`"Classifier"`), snake_case (`"metrics_fetcher"`), and kebab-case
    (`"metrics-fetcher"`) all resolve to the same registration — that's why
    `Component.get("Classifier")` finds a class stored under the kebab-case key
    `"classifier"`.

The `Context` uses these to discover registered components at startup. Application
code does not call them directly.

---

## Details

A `Component` may optionally implement `details()` to surface key/value
information about itself — a running service's URL, a port it bound, a
dashboard link. It is independent of `on_start()`/`on_stop()` and is never
called by the `Context`; it's detected structurally and called on demand by
whatever's inspecting the component, so values that only exist after
startup are reflected rather than frozen at resolve time.

```python
@Api
@Service
class Dashboard:

    def __init__(self, config: Config):
        self.port = config.port

    def details(self) -> dict[str, str]:
        return {"UI": f"http://localhost:{self.port}"}
```

`details()` is detected structurally via `DetailsProtocol`
(`opendataframework.component.DetailsProtocol`, `@runtime_checkable`) — no base class or
decorator required:

```python
class DetailsProtocol(Protocol):
    def details(self) -> dict[str, str]: ...
```

A component with no `details()` method simply has nothing to surface here —
this is entirely optional.

!!! tip "Seeing it in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI has a Details button in its object inspector; clicking it calls
    `details()` on demand, via `GET /api/components/{id}/details`, and shows
    the result. That's just today's one consumer, though — nothing here
    depends on it.

---

## Chart

A `Component` may optionally implement `chart()` to render a custom
visualization, backed by whatever Python charting library it likes
(matplotlib, plotly, ...) rather than requiring a JS charting library on
the consumer's side. Like `details()`, it is independent of
`on_start()`/`on_stop()` and is never called by the `Context` — it's
detected structurally and called on demand by whatever's inspecting the
component, so the chart reflects live repository state on every call
rather than being frozen at resolve time.

`chart()` must return a self-contained HTML document — inline image/JS, no
external file references — so a caller can embed it safely:

```python
@Analytics
@Component
class UsersByStore:

    def __init__(self, users: Users, stores: Stores):
        self.users = users
        self.stores = stores

    def chart(self) -> str:
        fig = ...  # build a matplotlib/plotly/... figure from self.users, self.stores
        return f"<html><body><img src='data:image/png;base64,{encoded}'></body></html>"
```

Because the chart lives on a normal DI-managed `Component`, it gets
constructor-injected access to repositories and other components just like
any other component — no separate data-fetching layer is needed.

`chart()` is detected structurally via `ChartProtocol`
(`opendataframework.component.ChartProtocol`, `@runtime_checkable`) — no base class or
decorator required:

```python
class ChartProtocol(Protocol):
    def chart(self) -> str: ...
```

A component with no `chart()` method simply has no chart to show — this is
entirely optional.

!!! tip "Seeing it in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI calls `chart()` on demand, per request to
    `GET /api/components/{id}/chart`, serves the returned string as
    `text/html`, and renders it inside a same-origin `<iframe>` — which is
    why the HTML must be self-contained. That's just today's one consumer,
    though — nothing here depends on it.

---

## What Component is Not

* **Not a base class.** `Classifier` does not inherit from `Component`. The decorator
  registers it; inheritance is not involved.

* **Not an execution unit.** The framework does not call any method on a `Component`
  automatically — it is instantiated and wired, nothing more. If you need the framework
  to call `run()` or `execute()`, use [Service](service.md) or [Task](task.md) instead.

* **Not created more than once.** The `Context` creates exactly one instance per
  registered class and returns that same instance from every `context.get(cls)`
  call — see [Context](context.md#direct-access).

---

## Decision Guide

| I need to...                              | Use         |
| ----------------------------------------- | ----------- |
| Provide a reusable capability             | `Component` |
| Run a process indefinitely                | [Service](service.md)   |
| Execute a bounded unit of work once       | [Task](task.md)      |
| Coordinate multiple tasks into a workflow | [Pipeline](pipeline.md)  |
| Manage persistent data                    | [Repository](repository.md)|
