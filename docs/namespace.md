# Namespace

`Namespace` is the base class for all framework decorator types. Subclassing it
produces a named scope — a decorator that registers user-defined classes and functions
under a `name → object` mapping and exposes that mapping for inspection.

[Component](component.md), [Service](service.md), [Task](task.md), [Pipeline](pipeline.md), and [Agent](agent.md) are all `Namespace` subclasses.
[Function](function.md) is one too — the one that registers functions rather than classes.
Each maintains its own independent mapping, and each says what it may be applied to —
see [What each decorator accepts](#what-each-decorator-accepts).

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
Component.get("Classifier")  # → Classifier, or None
Component.get("metrics-classifier")  # → Classifier registered under a custom name

dict(Component.items())  # → {"classifier": Classifier, ...}
```

These are used by the `Context` at startup to discover registered classes and
build the dependency graph. Application code does not call them directly.

---

## How it works

Each `Namespace` subclass carries its own `_namespace` dict — assigned
automatically via `__init_subclass__` when the subclass is defined. It is never
shared between sibling subclasses.

The dual-use decorator protocol is implemented through `__new__` and `__call__`:

- **Bare usage** — `__new__` detects a class or function argument, writes directly
  into `_namespace`, and returns it. Instance creation is bypassed entirely.
- **Factory usage** — `__new__` returns a `Namespace` instance; `__init__` stores
  the explicit name; `__call__` writes into `_namespace` when the instance is
  applied to the class.

!!! warning "Duplicate names raise"
    Registering two classes under the same name within one `Namespace`
    subclass raises `ValueError`, naming both classes — whether the collision
    comes from two bare decorators (two classes that happen to kebab-case to
    the same name), two factory decorators with the same explicit `name=`,
    or one of each. This happens at class-definition time (when the
    decorator runs), not at `Context`/`Project` start time. It previously
    silently overwrote the first registration with the second — that
    behavior is no longer supported; rename one of the classes, or give one
    an explicit `name=`.

### Names are unique per namespace, keys everywhere

Uniqueness is checked within one `Namespace` subclass only, so the same name
can be registered in several: a `@Task class Loader`, an `@Agent class Loader`
and a `@Function def loader` coexist. Each object also has exactly one name in a
namespace — registering it twice under different names raises `ValueError`.

Together that makes `<namespace>.<name>` unique, and it is what the
[Context](context.md#by-key-single-component-control) addresses everything by —
`"task.loader"`, `"agent.loader"`, `"function.loader"` — and what each log file
is named after. `qualified(Task, "loader")` builds a key and `parse("Task.Loader")`
normalizes one; both live in `opendataframework.namespace`.

---

## What each decorator accepts

A plain `Namespace` subclass registers any named class or function. The framework's own
decorators are narrower, and each raises `TypeError` at decoration time — in both the
bare and the factory form — when applied to something else:

| Decorator | Accepts |
| --------- | ------- |
| A plain `Namespace` subclass | A class, or a named function |
| `@Component`, `@Repository`, `@Service`, `@Task`, `@Pipeline`, `@Agent` | A class that has no other execution type |
| `@Entity` | A class |
| `@Function` | A function |
| `@Layer` | A `Namespace` subclass |
| A layer (`@Storage`, a custom one, ...) | A class or function that is already registered |

Three consequences worth knowing:

```python
@Component
def load_data(): ...  # TypeError — to register a function, use @Function


@Component
@Task
class Refresh: ...  # TypeError — a class takes one execution type


@Storage
class Warehouse: ...  # TypeError — a layer tags what an execution type registered
```

An execution type says how the `Context` treats a class, so a class carries exactly one.
A [Layer](layer.md) is an organisational tag on top of that, which is why it goes
outermost and why it has nothing to tag on a bare class or function.

`Component` and `Function` are separate namespaces, so a class `LoadData` and a function
`load_data` can coexist — each is `load-data` in its own mapping. Tagged with the same
layer they would collide there, as two same-named classes do.

!!! note "Type checkers"
    A type checker accepts a function under any of these decorators, because the function
    overload is declared once, on `Namespace`. `@Component def f` is therefore caught when
    the module is imported rather than in the editor.

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
