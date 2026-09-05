# Namespace

`Namespace` is the base class for all framework decorator types. Subclassing it
produces a named scope — a decorator that registers user-defined classes under a
`name → class` mapping and exposes that mapping for inspection.

[Component](component.md), [Service](service.md), [Task](task.md), and [Pipeline](pipeline.md) are all `Namespace` subclasses.
Each maintains its own independent mapping; registering a class with `@Component`
does not affect `Service`, and vice versa.

---

## When to use Namespace

`Namespace` is a framework extension point, not an end-user concept. Inherit from
it when adding a new first-class decorator type to the framework — a new kind of
managed object that the `Context` should be aware of.

End users work with the concrete subclasses (`@Component`, `@Service`, etc.) and
never interact with `Namespace` directly.

---

## Defining a Namespace

Subclassing `Namespace` is all that is required. Each subclass automatically
receives its own empty `_namespace` dict at definition time:

```python
from opendataframework.namespace import Namespace

class Component(Namespace): ...
class Service(Namespace): ...
```

Both decorators are now independent. Registering a class with `@Component` does
not appear in `Service._namespace`.

---

## Decorator protocol

Every `Namespace` subclass supports two decoration styles out of the box.

### Bare decorator

```python
@Component
class Classifier: ...
```

The class is registered under its own `__name__`. The class itself is returned
unchanged — no base class is added, no methods are injected.

### Factory decorator

```python
@Component(name="metrics-classifier")
class Classifier: ...
```

The class is registered under the explicit name. Again, the class is returned
unchanged.

---

## Inspection

`Namespace` exposes two class methods for reading the mapping:

```python
Component.get("Classifier")         # → Classifier, or None
Component.get("metrics-classifier") # → Classifier registered under a custom name

dict(Component.items())             # → {"classifier": Classifier, ...}
```

These are used by the `Context` at startup to discover registered classes and
build the dependency graph. Application code does not call them directly.

---

## How it works

Each `Namespace` subclass carries `_namespace: dict[str, type]` — assigned
automatically via `__init_subclass__` when the subclass is defined. It is never
shared between sibling subclasses.

The dual-use decorator protocol is implemented through `__new__` and `__call__`:

- **Bare usage** — `__new__` detects a class argument, writes directly into
  `_namespace`, and returns the class. Instance creation is bypassed entirely.
- **Factory usage** — `__new__` returns a `Namespace` instance; `__init__` stores
  the explicit name; `__call__` writes into `_namespace` when the instance is
  applied to the class.

---

## What Namespace is Not

* **Not an end-user API.** Application code uses `@Component`, `@Service`, etc.
  `Namespace` is for framework contributors adding new decorator types.

* **Not a global registry.** Each subclass owns its mapping independently. There
  is no single registry that spans all types — `Context` reads from each namespace
  separately.

* **Not inherited by user classes.** `Classifier` does not inherit from
  `Component` or `Namespace`. The decorator registers it; inheritance is not
  involved.
