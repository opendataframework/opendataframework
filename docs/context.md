# Context

The `Context` is the framework's dependency-injection and lifecycle engine. It
manages the full lifecycle of application components — registering them, resolving
their dependencies, creating instances in the correct order, and coordinating
startup and shutdown.

Everything the framework does flows through the `Context`. `Project` owns it and
exposes `project.context.get(cls)` to fetch any resolved instance by its class.

!!! tip "Minimal, self-contained example"
    Any registered class works — here's a plain `Component`, defined and
    fetched:

    ```python
    @Component
    class Classifier:
        def predict(self, data): ...


    project = Project.from_config("config.toml")
    project.start()

    classifier = project.context.get(Classifier)
    classifier.predict(data)
    ```

---

## Responsibilities

| Responsibility        | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| Registration          | Tracks all components declared with framework decorators     |
| Dependency resolution | Builds the dependency graph from constructor signatures      |
| Instance creation     | Creates instances in dependency order                        |
| Lifecycle management  | Drives the lifecycle of every component in the correct order |

!!! note "Registration is global; instances are per-Context"
    Every class registered with a framework decorator becomes part of the
    shared namespace the moment its module is imported — every `Project`'s
    `Context` instantiates it, regardless of that project's config. A
    `[section]` in `config.toml` only supplies values a constructor reads via
    `config: Config`; it doesn't determine which classes get built. What
    isn't shared is state: each `Project` owns its own `Context`, so its
    instances stay separate from any other `Project` in the same process.

---

## How it Works

The `Context` operates as an internal engine — components are registered via decorators
at class definition time, and the `Context` does the rest when the `Project` starts.
Most end users never interact with it directly.

```text
Decorators register components at definition time
    → @Component, @Service, @Task, @Pipeline, @Repository

project.start() triggers context initialisation
    → Context builds the dependency graph from constructor signatures
    → For each component in dependency order:
        → if Service:                     setup() → run() (backgrounded by framework)
        → if Component/Repository defines on_start(): called directly, blocking
        → otherwise:                      instantiated only
    → project.start() returns — everything is ready

project.stop() triggers context teardown
    → For each component in reverse dependency order:
        → if Service:                     stop() (signals background thread to exit)
        → if Component/Repository defines on_stop(): called directly, blocking
        → otherwise:                      no teardown
```

---

## Dependency Graph

The `Context` derives the dependency graph automatically from constructor signatures.
No explicit dependency declarations are needed.

```python
@Api
@Service
class UsersApi:

    def __init__(self, users: Users):
        self.users = users


@Storage
@Repository(User)
class Users:

    def __init__(self, postgres: Postgres):
        self.postgres = postgres


@Storage
@Service
class Postgres:

    def __init__(self, config: Config):
        self.config = config
```

The `Context` resolves the full graph:

```text
Config      ← no dependencies, initialised first
    ↓
Postgres    ← depends on Config
    ↓
Users       ← depends on Postgres
    ↓
UsersApi    ← depends on Users
```

---

## Startup Order

Startup runs in dependency order — dependencies first, dependents after.

For each component, the framework applies the appropriate lifecycle:

```text
Config
    → instantiated        ← Component, no lifecycle

Postgres
    → setup()             ← Service lifecycle, blocking
    → run()               ← backgrounded by framework, continues to next

Users
    → instantiated        ← Repository (no on_start() defined here)

UsersApi
    → setup()             ← Service lifecycle, blocking
    → run()               ← backgrounded by framework
```

`project.start()` blocks until all components have completed their initialisation
stage. After it returns, everything is ready — no hidden latency, no partial state.

**Readiness** — services should complete all setup work inside `setup()`. The framework
waits for `setup()` to return before proceeding to the next component, so any service
that opens connections or runs migrations in `setup()` is guaranteed to be ready before
dependents start.

**Component/Repository startup hook** — if `Users` (or any `Component`/`Repository`)
defines `on_start()`, it's called at this same point in dependency order, blocking,
right where "instantiated" appears above. It's optional and independent of `on_stop()`
— see `docs/repository.md` for the full pattern (connections, file handles, and
similar lightweight setup that should happen once, at `Project` start).

---

## Shutdown Order

Shutdown runs in reverse dependency order — dependents are stopped before their
dependencies.

```text
UsersApi    → stop()      ← Service stopped first
Users       → (none)      ← Repository (no on_stop() defined here)
Postgres    → stop()      ← Service stopped last
Config      → (none)      ← Component, no lifecycle
```

This ensures no component is stopped while something that depends on it is still running.

**Component/Repository shutdown hook** — if `Users` (or any `Component`/`Repository`)
defines `on_stop()`, it's called at this same point in reverse dependency order,
blocking.

---

## Circular Dependencies

Circular dependencies indicate a design problem and are not supported. If `A` depends
on `B` and `B` depends on `A`, the `Context` cannot determine a valid initialisation
order.

!!! tip "Raises ValueError"
    Detecting a cycle raises `ValueError`, naming the classes involved:
    `Circular dependency detected among: A, B`. This surfaces at
    `project.start()`, not at class-definition time — decorators only
    register classes, they don't check the graph.

The fix is to introduce a third collaborator that both can depend on, or replace one
of the dependencies with an event or callback:

```python
# problem
class A:
    def __init__(self, b: B): ...

class B:
    def __init__(self, a: A): ...  # circular

# solution — extract shared concern into C
class A:
    def __init__(self, c: C): ...

class B:
    def __init__(self, c: C): ...
```

---

## Direct Access

`project.context.get(cls)` fetches any resolved instance by its class — the
intended entry point for top-level application code, scripts, and notebooks:

```python
users = project.context.get(Users)
users.all()
```

`project.context.instances` is the lower-level, untyped dict backing `get()` —
primarily useful for framework extension authors:

```python
# use the context directly — useful in extensions and tooling
with project.context as ctx:
    component = ctx.instances[UsersApi]
```

`get(cls)` relies on every registered class being a per-`Context` singleton —
exactly one instance per class, stored in `instances`. `Logger` is the one
constructor dependency that breaks this: it isn't registered in any
namespace and has no slot in `instances` at all, so `context.get(Logger)`
doesn't work — see [Logger](logger.md#not-a-singleton-special-cased-resolution).

---

## By Name — Single-Component Control

Beyond `get(cls)`, `Context` exposes a by-name control surface — every
method below looks up a resolved instance by its class name (e.g.
`"Postgres"`, not the `Postgres` class itself) and raises `KeyError` if no
resolved instance matches that name. This is the mechanism a UI, CLI, or
MCP server built on top of the framework uses to control one component at
a time without importing its class:

**Services** — start, stop, or check a single `Service` independent of the
normal dependency-order startup/shutdown driven by `project.start()`/
`project.stop()`:

```python
project.context.start("Postgres")       # no-op if already running
project.context.stop("Postgres")        # no-op if not running
project.context.is_running("Postgres")  # → bool
```

Each raises `TypeError` if the matched instance isn't a `Service`.

**Streams** — start, stop, check, or attach to a `StreamableProtocol`
repository's background stream (see [Repository](repository.md)):

```python
project.context.start_stream("Webcam")       # spawns the background thread
project.context.stop_stream("Webcam")        # no-op if not streaming
project.context.is_streaming("Webcam")       # → bool

for frame in project.context.iter_stream("Webcam"):
    ...  # one subscriber; detaches when the stream stops or iteration ends
```

`start_stream()`/`stop_stream()` mirror `start()`/`stop()` for services and
raise `TypeError` if the matched instance isn't `StreamableProtocol`.
`iter_stream()` only attaches to an already-running stream — it doesn't
start one itself, and raises `KeyError` if the stream isn't currently
running.

**Tasks and Pipelines** — execute a single resolved `Task` or `Pipeline`
by name:

```python
project.context.execute("DailyAnalytics")  # → whatever execute() returns
```

Raises `TypeError` if the matched instance is neither.

**Logs** — read back a component's recent log lines (see
[Logger](logger.md)):

```python
project.context.tail_logs("Postgres", lines=300)
# → [{"ts": ..., "level": ..., "message": ...}, ...], oldest first
```

---

## What Context is Not

* **Not a service locator for internal wiring.** Components should declare
  dependencies through their constructor, not look them up from the `Context` at
  runtime — `project.context.get(cls)` is for top-level and cross-cutting access,
  not a replacement for dependency injection between components.

* **Not directly called by end users during startup.** Registration and wiring
  happen through decorators and constructor signatures; the `Context` resolves
  and drives lifecycle as an internal engine. `project.context.get(cls)` is the
  entry point end users reach for only after `project.start()` returns — and
  even then, it's not something that should be used directly in most cases:
  most dependency logic belongs inside a class that receives it via
  constructor injection, not in code that pulls it from the `Context`
  directly.

* **Not responsible for threading.** The framework handles `Service.run()`, and a
  streamable `Repository`'s `stream()`, in background threads automatically. Neither
  the service/repository author nor the context caller needs to manage this directly.
