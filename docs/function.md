# Function

A `Function` is a plain Python function made known to the framework. It is to a
function what a [Component](component.md) is to a class: registered and wired through
dependency injection, with no execution contract of its own.

It exists for adoption. An existing codebase written as functions can become
framework-aware one decorator at a time, without a class refactor first — the function
itself, its callers, and its tests stay exactly as they were.

Functions answer one question:

> How do I bring the code I already have into the framework?

---

## When to use Function

Use `@Function` when:

* you are adopting the framework in an existing, function-based project
* a piece of logic is stateless and a class would add nothing but ceremony
* you want a function to be callable by name with arguments — by a UI, a CLI, or an
  MCP server built on top of the framework

Prefer a class — [Component](component.md), [Task](task.md), [Service](service.md) —
as soon as the logic needs state, startup or shutdown hooks, or to be injected into
something else. `@Function` is the on-ramp; classes remain the recommended shape for
code written for the framework from the start.

---

## Decorator

The `@Function` decorator registers the function into the `Function` namespace under
the kebab-case form of its name. The function is returned unchanged.

### Without arguments

```python
@Function
def load_data(path: str) -> list[dict]: ...
```

Registered as `load-data`.

### With a name

```python
@Function(name="loader")
def load_data(path: str) -> list[dict]: ...
```

!!! warning "Only functions can be decorated"
    Applying `@Function` to a class raises `TypeError` at decoration time, as does
    a callable with no name of its own (a `functools.partial`, an instance with
    `__call__`). A function already wrapped by another decorator, such as
    `functools.cache`, is fine.

---

## Dependency Injection

A class separates its dependencies (`__init__`) from its arguments (the method). A
function has one signature for both, so the `Context` splits it by type — the same
rule it applies to constructors:

* a parameter annotated with a type the `Context` manages is **injected**
* every other parameter is a **call argument**, supplied by the caller

```python
@Component
class Postgres: ...


@Function
def load_data(path: str, db: Postgres, limit: int = 100) -> int: ...
```

Here `db` is injected and becomes an edge in the dependency graph; `path` and `limit`
are what a caller passes.

A parameter whose type the framework doesn't manage is simply an argument, whatever
it is:

```python
@Function
def score(model: SklearnModel, threshold: float, db: Postgres) -> float: ...
```

`model` and `threshold` are call arguments; only `db` is injected.

A parameter annotated `Logger` receives a [Logger](logger.md) bound to the function's
own name, as it would for a class.

!!! note "String annotations are not injected"
    As with constructors, only an annotation that is an actual type counts. Under
    `from __future__ import annotations` every annotation is a string, so nothing is
    injected and every parameter stays a call argument.

---

## Calling a Function

There are three ways to call a registered function. Only the first existed before you
added the decorator, and it is unaffected by it.

### Directly

```python
load_data("data.csv", db=fake_db)
```

Nothing is injected, wrapped, or logged — every argument is passed by the caller. This
is why existing callers and tests keep working unchanged.

### By name, through the Context

```python
project.context.call("load-data", path="data.csv")  # db injected
```

`call()` takes the registered name (in any casing — `"load-data"` or `"load_data"`)
and the function's remaining arguments as keywords. It is the counterpart of
`execute()` for a [Task](task.md), with the one difference that a function takes
arguments. This is what a caller holding only a name and a payload uses.

### By function, through the Context

```python
load = project.context.get(load_data)  # db already filled in
load("data.csv")
load("data.csv", limit=10)
```

`get()` returns the function with its managed dependencies bound. Positional arguments
fill the remaining parameters in order, so an injected parameter that happens to come
first doesn't shift them.

Both forms follow the same rules:

* **An explicit argument wins.** Passing `db=fake_db` to `call()` or to the bound
  function overrides the injected value.
* **A missing argument fails clearly.** If a required parameter is neither managed nor
  supplied, a `TypeError` names it and its type:
  `score() is missing 'model' (SklearnModel) — not managed by the Context and not
  supplied by the caller`.
* **Calls are logged.** Start, completion with duration, and any exception go to the
  function's own log, like `execute()` on a `Task`.

Both become usable once `project.start()` returns, and raise `KeyError` for a function
the `Context` hasn't resolved.

---

## Full Example

A script-style module, before:

```python
def restock(inventory, item, quantity):
    inventory.stock[item] = inventory.stock.get(item, 0) + quantity
    return inventory.stock[item]
```

After — one decorator, and a type on the parameter the framework should supply:

```python
@Component
class Inventory:
    def __init__(self) -> None:
        self.stock: dict[str, int] = {}


@Function
def restock(inventory: Inventory, item: str, quantity: int) -> int:
    inventory.stock[item] = inventory.stock.get(item, 0) + quantity
    return inventory.stock[item]
```

```python
project.start()
project.context.call("restock", item="apple", quantity=10)
```

Existing calls such as `restock(inventory, "apple", 10)` still work as written.

---

## Inspecting Functions

`project.context.functions` maps every resolved function to its bound callable. It is
separate from `project.context.instances`, which holds classes only.

`project.context.parameters(func)` returns the parameters a caller must supply — the
signature minus whatever the `Context` injects — as `inspect.Parameter` objects:

```python
project.context.parameters(load_data)
# → {"path": <Parameter "path: str">, "limit": <Parameter "limit: int = 100">}
```

This is what tooling uses to build a form or a tool schema for a function without
re-implementing the injection rule.

---

## What Function is Not

* **Not injectable.** A function consumes dependencies; nothing can depend on it. If
  other code needs it handed in, make it a [Component](component.md).

* **Not stateful, and without a lifecycle.** There is no instance, and no
  `on_start()`/`on_stop()`. State belongs in a component the function takes as a
  parameter.

* **Not a Task.** A [Task](task.md) has an `execute()` contract and takes no arguments.
  A function has no contract and does take arguments. It cannot be a step of a
  [Pipeline](pipeline.md).

* **Not tagged with a Layer.** [Layer](layer.md) decorators apply to classes only.

* **Not awaited.** An `async def` function can be registered, but `call()` returns its
  coroutine as-is; awaiting it is up to the caller.

---

## Decision Guide

| I need to...                                        | Use                       |
| --------------------------------------------------- | ------------------------- |
| Make an existing function known to the framework    | `Function`                |
| Provide a reusable, injectable capability           | [Component](component.md) |
| Execute a bounded unit of work once, no arguments   | [Task](task.md)           |
| Coordinate multiple tasks into a workflow           | [Pipeline](pipeline.md)   |
| Run a process indefinitely                          | [Service](service.md)     |
