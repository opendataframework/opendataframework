# Project

The `Project` is the composition root of the framework. It owns the `Context`
and is the single entry point for starting and stopping the application.

---

## Instantiation

### From a config file

The primary way to create a `Project` is from a config file:

```python
project = Project.from_config("config.toml")
```

### From a config directory

For larger projects, config can be split across multiple files in a directory.
The framework merges them into a single configuration:

```python
project = Project.from_config("config/")
```

A typical config directory might look like:

```text
config/
├── storage.toml
├── analytics.toml
├── api.toml
└── data.toml
```

### From a dict

For programmatic use — testing, tooling, dynamic configuration:

```python
project = Project.from_dict({
    "users": {
        "table": "users",
        "schema": "public",
    },
    "postgres": {
        "database_url": "postgresql://localhost/mydb",
    },
})
```

---

## Lifecycle

### Starting

`project.start()` triggers context initialisation — the dependency graph is resolved,
instances are created in dependency order, and the appropriate lifecycle is applied
to each component:

```text
project.start()
    → for each component in dependency order:
        → if Service:  setup() → run() (backgrounded by framework)
        → if Component / Repository:  on_start() (blocking, return quickly)
    → blocks until all components are initialised
    → returns — everything is ready
```

After `project.start()` returns, every component's `setup()`/`on_start()` has
completed — the framework blocks on each in dependency order and waits for it to
return before moving on. There's no hidden latency on first access *as long as*
components do their readiness work there: opening connections, running migrations,
allocating resources. A `Service`'s `run()` is only launched in the background by
this point, not waited on — see [Service](service.md#on_start-vs-setup) for what
belongs in each stage.

```python
project = Project.from_config("config.toml")
project.start()

# everything ready immediately
users = project.context.get(Users).all()
project.context.get(DailyAnalytics).execute()
```

### Stopping

`project.stop()` tears down all components in reverse dependency order:

```text
project.stop()
    → for each component in reverse dependency order:
        → if Service:  stop() (signals background thread to exit, waits)
        → if Component / Repository:  on_stop() (blocking, return quickly)
    → blocks until all components are stopped
```

```python
project.stop()
```

---

## Access

After `project.start()`, `project.context` is the entry point to every resolved
instance:

```python
project.context.get(UsersApi)     # typed, by class — the common case
project.context.instances[UsersApi]  # lower-level dict access, primarily for
                                      # framework extension authors
```

```python
project.context.get(Users).all()
project.context.get(Orders).get(order_id)
project.context.get(MetricsFetcher).execute()
```

`project.context.get(cls)` resolves by class, so the return type is `cls` — an
editor or type checker knows exactly what comes back, unlike a string-keyed
lookup. See [Context](context.md).

---

## Usage Patterns

### Notebook or script

`project.start()` blocks until everything is ready, then returns control. Natural
for notebooks and scripts where you want to query data or run a pipeline:

```python
project = Project.from_config("config.toml")
project.start()

# query data
users = project.context.get(Users).all()

# run a pipeline explicitly
results = project.context.get(DailyAnalytics).execute()

project.stop()
```

### Long-running application

For a long-running application, `project.start()` brings up all services in the
background. Something has to keep the process itself alive afterward:

```python
project = Project.from_config("config.toml")
project.start()
```

!!! tip "Who keeps the process alive"
    A `Service`'s `run()` executes in a daemon thread, which is torn down
    the instant the main thread exits — there's no blocking `project.wait()`
    today, so running this snippet on its own exits immediately and never
    really runs any service. Normally a launcher does this for you — the
    sibling [`odf`](https://opendataframework.github.io/odf/) package's CLI
    (`odf run`), for instance.

---

## Configuration and Environments

Different environments are handled by pointing to different config files or directories:

```python
# development
project = Project.from_config("config/dev/")

# production
project = Project.from_config("config/prod/")
```

This keeps environment differences explicit and visible — a config file is a plain
text artifact that can be read, diffed, and version-controlled without running the
application.

---

## Multiple Projects

Multiple independent `Project` instances are supported within the same process.
Each owns its own `Context` — there is no shared global state between them.

```python
dev = Project.from_config("config/dev/")
prod = Project.from_config("config/prod/")

dev.start()
prod.start()
```

---

## What Project is Not

* **Not an orchestrator.** `Project` does not decide what runs after initialisation.
  Running a pipeline, querying data, or triggering a task is always triggered
  explicitly by application code — whether that's a top-level script, or a class
  that received the dependency via DI (an API handler, a scheduled job) — never
  something `Project` or `Context` invokes on their own.

* **Not a singleton.** Multiple `Project` instances can coexist in the same process.
  Global mutable state at the framework level is avoided by design.

* **Not aware of business logic.** `Project` owns the `Context`, not domain concerns.
  Business logic lives in components, tasks, and pipelines.
