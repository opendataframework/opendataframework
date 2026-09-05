# Service

A `Service` is a long-running executable — wired through dependency injection the same
way as a [Component](component.md), but with a mandatory `setup → run → stop` lifecycle
the `Context` drives automatically. It represents a runtime capability that the framework
starts and keeps alive for the duration of the application.

Services answer one question:

> What needs to keep running?

> **Note:** `Service` here means an executable runtime capability, not a business-logic
> layer some other frameworks name that way. Think process, server, or worker — not
> `UserService` or `OrderService`.

---

## When to use Service

Use `@Service` when a class needs to:

* start up and run indefinitely until explicitly stopped
* manage an execution environment (a server, a container, a connection pool)
* expose a long-lived capability to the rest of the application

If the work is finite and runs to completion, use [Task](task.md) or [Pipeline](pipeline.md) instead.

Typical examples:

* API servers
* database processes
* message queue workers
* schedulers
* agent runtimes
* Docker containers

---

## Decorator

The `@Service` decorator registers the class into the `Service` namespace as a
long-running executable component. The `Context` reads from this namespace at
startup. The class is returned unchanged.

### Without arguments

```python
@Service
class Postgres:
    ...
```

### With a name

```python
@Service("postgres")
class PostgresConnectionPoolManager:
    ...
```

### Combined with a Layer

```python
@Storage
@Service
class Postgres:
    ...
```

```python
@Api
@Service
class UsersApi:
    ...
```

---

## Lifecycle

A `Service` follows a three-stage lifecycle managed by the framework:

```text
setup → run → stop
```

| Method    | Purpose                                                          | Blocking |
| --------- | ---------------------------------------------------------------- | -------- |
| `setup()` | Blocking setup — pull images, run migrations, open connections   | Yes      |
| `run()`   | Block and serve — runs for the lifetime of the application       | Yes*     |
| `stop()`  | Release resources, close connections, shut down gracefully       | Yes      |

!!! tip "Why run() is marked Blocking\* but doesn't stall startup"
    `run()` is blocking by nature — the framework automatically spawns it in a
    background thread so startup can continue to the next component. The
    service author does not need to manage threading.

All three methods must be defined. Stages with no work can be left as ``pass`` (or ``...``).

---

## Framework-Managed Concurrency

The framework knows that `run()` will block. It handles this automatically:

```text
project.start()
    → setup()     ← blocking, framework waits
    → run()       ← framework spawns in background thread, continues to next component
```

The service author implements `run()` as a plain blocking call. Threading is never
the service's responsibility.

```python
@Storage
@Service
class Postgres:

    def setup(self): ...

    def run(self):
        self.pool.serve()   # blocks — framework handles the thread

    def stop(self): ...
```

---

## Interface

```python
@Service
class Postgres:

    def setup(self):
        # blocking setup: pull image, run migrations, open connection pool
        # framework waits for this to return before proceeding
        ...

    def run(self):
        # block and serve for the lifetime of the application
        # the framework spawns this in a background thread automatically
        ...

    def stop(self):
        # signal run() to exit and release resources gracefully
        # example: close connections, flush buffers, shut down server
        ...
```

---

## on_start() vs setup()

`Service` uses `setup()`, `run()`, and `stop()` — not the `on_start()` / `on_stop()`
hooks used by [Component](component.md) and [Repository](repository.md). This is intentional:

* The framework needs to know *which method to background* — it can only do that with
  an explicit contract.
* `on_start()` is a lightweight initialisation hook expected to return quickly.
  `setup()` is the place for heavier blocking work: pulling images, running migrations,
  opening connection pools.

A `Service` may still define `on_start()` / `on_stop()` if it has lightweight
concerns separate from the service lifecycle, but the primary lifecycle is
`setup → run → stop`.

---

## Dependency Injection

Like all components, a `Service` declares its dependencies through the constructor:

```python
@Storage
@Service
class Postgres:

    def __init__(
        self,
        config: Config,
    ):
        self.config = config
        self.pool = None

    def setup(self):
        self._pull_image(self.config.image)
        self.pool = self._create_pool(self.config.database_url)
        self._run_migrations()

    def run(self):
        self.pool.serve()

    def stop(self):
        self.pool.close()

    def _pull_image(self, image):
        ...

    def _create_pool(self, url):
        ...

    def _run_migrations(self):
        ...
```

---

## Full Examples

### API server

```python
@Api
@Service
class UsersApi:

    def __init__(
        self,
        config: Config,
        users: Users,
    ):
        self.config = config
        self.users = users
        self.server = None

    def setup(self):
        self.server = self._create_server(self.config)
        self.server.bind(self.config.host, self.config.port)

    def run(self):
        self.server.serve()

    def stop(self):
        self.server.shutdown()

    def _create_server(self, config):
        ...
```

### Scheduler

```python
import time
from datetime import datetime, timedelta

@Service
class Scheduler:

    def __init__(
        self,
        config: Config,
        pipeline: DailyAnalytics,
    ):
        self.config = config
        self.pipeline = pipeline
        self._running = False

    def setup(self):
        self._running = True

    def run(self):
        while self._running:
            self._wait_for_next_run()
            if self._running:
                self.pipeline.execute()

    def stop(self):
        self._running = False

    def _wait_for_next_run(self):
        # block until the next scheduled run, e.g. once a day at 02:00
        now = datetime.now()
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        # sleep at most 60s at a time, re-checking _running after each nap,
        # so stop() is noticed within a minute rather than only after
        # a single sleep() covering the whole (possibly ~24h) gap
        while self._running and datetime.now() < next_run:
            remaining = (next_run - datetime.now()).total_seconds()
            time.sleep(min(60, remaining))
```

---

## Protocol

`ServiceProtocol` documents the expected interface and is available for type
checking and introspection:

```python
from opendataframework import ServiceProtocol

isinstance(instance, ServiceProtocol)  # True if all three lifecycle methods are defined
```

`ServiceProtocol` is `@runtime_checkable`. The `Context` uses `isinstance` to
distinguish services from components and then calls all three lifecycle stages
unconditionally.

```python
from opendataframework import ServiceProtocol

class ServiceProtocol(Protocol):
    def setup(self) -> None: ...
    def run(self) -> None: ...
    def stop(self) -> None: ...
```

---

## What Service is Not

* **Not a business logic container.** A `Service` manages a runtime capability, not
  domain logic. Business logic belongs in a [Component](component.md), [Task](task.md),
  or [Pipeline](pipeline.md) that the `Service` depends on.

* **Not responsible for its own threading.** `run()` should block naturally. The
  framework spawns it in a background thread and manages concurrency automatically.

* **Not a base class.** `Postgres` does not inherit from `Service`. The decorator
  registers it; inheritance is not involved.

---

## Decision Guide

| I need to...                              | Use         |
| ----------------------------------------- | ----------- |
| Provide a reusable capability             | [Component](component.md) |
| Run a process indefinitely                | `Service`   |
| Execute a bounded unit of work once       | [Task](task.md)      |
| Coordinate multiple tasks into a workflow | [Pipeline](pipeline.md)  |
| Manage persistent data                    | [Repository](repository.md)|
