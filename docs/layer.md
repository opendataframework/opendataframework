# Layer

A `Layer` is an architectural grouping that organises components at the organisational
level. It answers one question:

> Which subsystem does this belong to?

Layers separate concerns at the organisational level — `Api`, `Storage`, `Analytics`,
`Messaging` — without affecting how components are wired or executed. A component's
layer and its execution type (`Component`, `Service`, `Task`, `Pipeline`) are
independent concepts.

---

## Two Roles

`Layer` plays two roles in the framework:

**As a user-facing decorator** — applied to a class to declare which subsystem it
belongs to. This is what most application code interacts with.

```python
@Analytics
@Task
class MetricsFetcher:
    ...
```

**As a framework concept** — a `Namespace` subclass in its own right, providing
structured access to the components it contains via `<Layer>.items()`/`<Layer>.get(name)`.

---

## Built-in Layers

The framework ships with a set of common pre-defined layers:

| Layer       | Typical contents                          |
| ----------- | ----------------------------------------- |
| `Api`       | API servers, request handlers, validators |
| `Storage`   | Databases, file systems, caches           |
| `Analytics` | Models, pipelines, metric collectors      |
| `Messaging` | Queues, brokers, event buses              |
| `Monitoring`| Health checks, loggers, tracers           |
| `Security`  | Auth handlers, token validators           |

Built-in layers are pre-defined `@Layer` instances — there is no special treatment
for them. They follow the same rules as any custom layer.

---

## Defining a Layer

A layer is a `Namespace` subclass registered with `@Layer`. The class inherits from
`Namespace` so that it can act as a decorator for the components that belong to it.

### Without a name — framework derives it

```python
@Layer
class MachineLearning(Namespace):
    ...
```

!!! tip "The framework converts the class name automatically"
    `MachineLearning` is registered under the kebab-case form `machine-learning` —
    but `.get()` normalizes its argument, so all three forms below find the same
    entry:

    ```text
    Layer.get("machine-learning")  # kebab-case — the registered key itself
    Layer.get("machine_learning")  # snake_case
    Layer.get("MachineLearning")   # PascalCase — the original class name
    ```

    See [Name Derivation](#name-derivation) below for the full picture, including
    the config key convention.

### With an explicit name — use when the derived name isn't what you want

```python
@Layer("ml")
class MachineLearning(Namespace):
    ...
```

Now the layer is looked up as `Layer.get("ml")` instead of
`Layer.get("machine-learning")`. Use explicit names when brevity or a domain
convention matters more than the derived default.

---

## Using a Layer Decorator

The layer decorator is stacked above the execution type decorator. Layer comes first
(outermost), execution type second:

```python
@Storage
@Service
class Postgres:
    ...

@Analytics
@Task
class MetricsFetcher:
    ...

@Api
@Component
class Validator:
    ...
```

The name identifying a component within its layer belongs on the execution type
decorator — not the layer. The layer says *where* it belongs; the execution type
says *what it is* and optionally *what it is called*:

```python
@Api
@Service("users-api")
class UsersApi:
    ...

@Analytics
@Task("metrics-fetcher")
class MetricsFetcher:
    ...
```

---

## Name Derivation

The framework applies the same automatic name derivation to both layers and
execution types. Given a class name, the framework produces:

| Class name       | snake_case (also accepted by `.get()`) | Config key (kebab-case) |
| ---------------- | --------------------------------------- | ----------------------- |
| `MachineLearning`| `machine_learning`                      | `machine-learning`      |
| `UsersApi`       | `users_api`                             | `users-api`              |
| `MetricsFetcher` | `metrics_fetcher`                       | `metrics-fetcher`       |
| `Postgres`       | `postgres`                              | `postgres`              |

`.get()` normalizes any of these forms to kebab-case before lookup, so
`Layer.get("machine_learning")` and `Layer.get("machine-learning")` both resolve.

An explicit name on the decorator overrides the derived name entirely:

```python
@Layer("ml")
class MachineLearning(Namespace):
    ...
# → Layer.get("ml")  (not Layer.get("machine-learning"))
```

---

## Custom Layers

Custom layers follow exactly the same pattern as built-in layers:

```python
@Layer
class MachineLearning(Namespace):
    ...


@MachineLearning
@Component
class Classifier:
    ...


@MachineLearning
@Task
class ModelTrainer:
    ...


@MachineLearning
@Pipeline
class TrainPipeline:
    ...
```

Accessible by class through the resolved `Context`, or by name through the layer
namespace itself:

```python
project.context.get(Classifier)
project.context.get(ModelTrainer)
project.context.get(TrainPipeline)

MachineLearning.get("classifier")      # → Classifier
dict(MachineLearning.items())          # → {"classifier": Classifier, ...}
```

---

## Inspecting Layer Membership

Two lookup directions are available, depending on what you know:

**`Layer.get(name)`** — given a kebab-case name, return the layer class:

```python
Layer.get("storage")    # → Storage
Layer.get("analytics")  # → Analytics
Layer.get("unknown")    # → None
```

**`<layer>.get(name)`** — given a component name, return the component class:

```python
Storage.get("postgres")          # → Postgres
Analytics.get("metrics-fetcher") # → MetricsFetcher
```

Together, the two-level namespace hierarchy gives structured access without any
reverse-lookup machinery:

```python
dict(Layer.items())              # → {"api": Api, "storage": Storage, …}
dict(Storage.items())            # → {"postgres": Postgres, …}
dict(Analytics.items())          # → {"metrics-fetcher": MetricsFetcher, …}
```

---

## Layer is Independent of Config

`Layer` has no bearing on config structure. Config sections are keyed by
component name alone, in kebab-case, regardless of which layer (if any) a
component belongs to — see [Config structure convention](config.md#config-structure-convention):

```toml
[users-api]
host = "0.0.0.0"
port = 8080

[postgres]
database_url = "postgresql://localhost/mydb"

[metrics-fetcher]
source_url = "https://api.example.com/metrics"

[classifier]
model_path = "models/classifier.pkl"
```

!!! tip "Seeing layers in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's UI
    groups components by their `Layer` when displaying them — a "Storage"
    section, an "Analytics" section, and so on. That's just today's one
    consumer, though — `Layer.get(name)` lookups work the same whether or not
    anything is reading them for display.

---

## Layer and Execution Type are Independent

The layer describes where a component belongs. The execution type describes how it
participates in the system. Any combination is valid:

```python
@Storage
@Service
class Postgres:
    ...

@Analytics
@Task
class MetricsFetcher:
    ...

@Api
@Component
class Validator:
    ...

@Api
@Pipeline
class UserOnboarding:
    ...

@Service
class Scheduler:
    # no layer — belongs directly to the Context
    ...
```

A component tagged with a layer is registered in **both** the execution type namespace
and the layer namespace — two independent views of the same class:

```python
Service.get("postgres")   # → Postgres  (execution type view)
Storage.get("postgres")   # → Postgres  (layer view)
```

---

## What Layer is Not

* **Not an execution contract.** A layer does not define what methods a component
  implements. That is determined by the execution type (`Service`, `Task`, etc.).

* **Not a base class.** Components do not inherit from their layer. The decorator
  marks membership; inheritance is not involved.

* **Not required.** A component without a layer decorator is managed directly by the
  `Context` and accessible via `project.context.get(cls)` just like any other
  component. Layers are organisational — they are not needed for DI or lifecycle
  management to work.

* **No protocol on the layer-defining class.** `class MachineLearning(Namespace): ...`
  inherits from `Namespace` so that `@MachineLearning` works as a decorator. The
  class body is always empty — there is nothing to implement. Classes *tagged* with
  a layer follow the execution type protocol (`Component`, `Service`, `Task`,
  `Pipeline`); the layer itself adds only organisational membership.
