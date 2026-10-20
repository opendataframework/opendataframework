# Release Notes

## 0.4.0

### Added

- **View**: `TimeseriesView` gains two optional fields. `fields` selects which numeric
  fields to plot — `None`, the default, plots every numeric field other than `field` and
  `group`, as before. `group` names a field whose distinct values each get their own line
  (e.g. `run_id`), so runs can be compared on one chart. `field` may be any field records
  are ordered by, not only a timestamp (e.g. a training `step`). Existing
  `TimeseriesView(field=...)` declarations are unchanged. Rendering the new fields happens
  on the `odf` side. See [View](view.md#timeseries-comparing-runs-on-one-chart).

## 0.3.0

### Added

- **Agent**: added `@Agent`, an execution type for goal-driven work whose steps are decided
  at run time — typically by a language model. An agent is a class with a single `invoke()`
  method whose signature is its author's to choose; everything it may act on is declared
  through its constructor like any other dependency, so it can also be injected into a
  `Pipeline`, a `Service`, or another agent. `context.call("agent.librarian", question=...)`
  invokes one by key, `context.parameters(Librarian)` returns the parameters of
  its `invoke()`, and every invocation is logged like a `Task`'s `execute()`. `@Agent` on a
  class without `invoke()` raises `TypeError` at decoration time. `AgentProtocol` documents
  the interface. The framework still ships no model client and no agent loop — `invoke()` is
  where a library or provider SDK of your choice goes. See [Agent](agent.md).
- **Function**: added `@Function`, a marker that makes a plain function known to the
  framework the way `@Component` does a class — so an existing function-based codebase can
  be adopted without a class refactor first. The function is returned unchanged, and direct
  calls behave exactly as before. Through the `Context`, parameters annotated with a managed
  type are injected and the rest are call arguments: `context.call("function.load-data", path=...)`
  calls by key, `context.get(load_data)` returns the function with its
  dependencies bound, `context.functions` lists what was resolved, and
  `context.parameters(func)` returns the parameters a caller must supply. A class — or
  another function — asks for one by naming it in its signature,
  `Annotated[Callable[..., int], load_data]`, and receives it with its dependencies bound
  and its calls logged — and with a signature that leaves the injected parameters out, so
  it can be handed to a library that builds a tool schema from a callable; the function
  then takes part in dependency ordering and cycle detection. Functions have no lifecycle and aren't in `context.instances`. See
  [Function](function.md).
- **View**: added `ContentMetadata`/`ContentMetadataProtocol` so a `Repository` whose view
  points at content (`ImageView`/`VideoView`/`AudioView`/`DocumentView`) can declare, per
  record, that content's `filename` and `content_type` via an optional
  `content_metadata(entity)` method, detected structurally like `DataViewProtocol`/
  `ReplayProtocol`. The values needn't be entity fields — a repository may derive them or
  return constants. Existing views are unchanged. Using this to label, type and offer
  content for download happens on the `odf` side. See [View](view.md).
- **Layer**: a function registered with `@Function` can now be tagged with a layer
  (`@Storage @Function def load_data(...)`), like a class. See [Layer](layer.md).
- **Context**: a required parameter that is not injected because its annotation is a
  string (every annotation under `from __future__ import annotations`) now fails with a
  `TypeError` that names the string annotation as the cause, for a constructor and for a
  function called through the `Context`. String annotations are still not injected.

### Changed

- **Namespace** (breaking): each decorator now states what it may be applied to, and
  raises `TypeError` at decoration time otherwise. Two cases were accepted before:
  a class under two execution types (`@Component @Task class X`) — a class takes one —
  and a layer on a class no execution type has registered (`@Storage class X`, or
  `@Component @Storage class X` with the layer underneath). To migrate, keep a single
  execution type on the class and put the layer above it. `@Component` and the other
  execution types on a function still raise, and now point to `@Function`. A plain
  `Namespace` subclass accepts a function as well as a class. See
  [Namespace](namespace.md#what-each-decorator-accepts).
- **Context** (breaking): async is not supported, and now says so. An `async def`
  function registered with `@Function`, or an `async def` `execute()`, `invoke()`,
  `setup()`/`run()`/`stop()`, `on_start()`/`on_stop()` or repository stream method, makes
  `project.start()` raise `TypeError` naming it. These were previously called without
  being awaited — a hook that silently never ran, or a call logged as complete before it
  started. To migrate, make it synchronous, or keep it out of the `Context` and call it
  yourself. See [Context](context.md#what-context-is-not).
- **Component** (breaking): an `McpTool` now requires a described, fully typed handler,
  and raises when it is created otherwise — `ValueError` for an empty `description`,
  `TypeError` for a handler with an unannotated parameter, `*args`/`**kwargs`, no return
  annotation, or an annotation left as a string. A caller, typically a model, sees
  nothing of a tool but its description and signature, and a handler without them was
  accepted and offered with a schema that said little. To migrate, annotate the handler's
  parameters and return value (`-> None` counts), replace a lambda with a method or a
  function, and remove `from __future__ import annotations` from the handler's module.
  See [Component](component.md#mcp-tools).
- **Context** (breaking): everything addressed by a string is now addressed by a key,
  `<namespace>.<name>` — `execute("task.load-job")`, `call("agent.librarian", ...)`,
  `start("service.postgres")`, `start_stream("repository.webcam")`,
  `tail_logs("component.cache")` and the rest. The name is the registered one (kebab-case
  class or function name, or the explicit `name=`), and keys are accepted in any casing.
  A name is only unique within its namespace, and the bare names used before collided
  across them: with a `@Component class Loader` and a `@Task class Loader`,
  `execute("Loader")` could find the component and raise `TypeError`, a `@Function` and an
  `@Agent` sharing a name could not be `call()`ed at all, and every same-named object
  wrote to one log file. Now each is reachable, and log files are named
  `<namespace>.<name>.log` (`logs/task.loader.log`). `context.key(obj)` returns the key
  of a class or function you hold. A string without a namespace raises `ValueError`, and
  the `ValueError` `call()` raised for a function and an agent sharing a name is gone. To
  migrate, prefix every name passed to the `Context` with its namespace, and point
  anything reading log files at the new names. See
  [Context](context.md#by-key-single-component-control).
- **Namespace** (breaking): registering one object under two names in the same
  namespace (`@Task("a") @Task("b") class X`) now raises `ValueError`, so every object
  has exactly one key. See [Namespace](namespace.md#names-are-unique-per-namespace-keys-everywhere).
- **Repository** (breaking): `@Repository(...)` now requires its argument to be a class
  registered with `@Entity`, and raises `TypeError` at decoration time otherwise. The docs
  always described the argument as the `Entity` class, but any class was accepted — so
  `@Repository` written directly above the repository class (entity left out) took that
  class for its own entity, registered nothing, and left the repository silently missing
  from the `Context`. To migrate, add `@Entity` to the entity class; for a type you don't
  own, call `Entity(SomeType)` once or wrap it in a small entity class. See
  [Repository](repository.md).

### Fixed

- **Context**: a class that declared the same dependency under two constructor parameters
  (`def __init__(self, source: Db, target: Db)`) failed at `project.start()` with a
  misleading `Circular dependency detected among: Sync`. It still fails — the `Context`
  holds a single `Db`, so both parameters would receive the same object — but now with a
  `ValueError` that says so and names the class, the dependency and the parameters.
- **Config**: key normalisation only applied to the name being looked up, not to the keys
  in the data, so a key written as `exclude_years` (or `ExcludeYears`) in TOML couldn't be
  found by any access path. `config.exclude_years` and `config["exclude_years"]` raised,
  and `config.get("exclude_years", default)` silently returned the default. `Config` now
  normalises its keys to kebab-case on construction (recursively through nested tables),
  so snake_case/kebab-case/PascalCase are interchangeable on both sides. Two keys in the
  same table that normalise to the same name (e.g. `exclude_years` and `exclude-years`)
  now raise `ValueError` instead of one silently shadowing the other. See [Config](config.md).
- **Namespace**: applying a decorator (`@Component`, `@Task`, `@Service`, ...) to a function
  instead of a class registered nothing and raised nothing — the bare form silently rebound
  the function's name to a namespace instance, and the factory form registered the function
  as if it were a class. Both now raise `TypeError` at decoration time, naming the namespace
  and the offending object. `@Repository` applied directly to a function (entity left out)
  raises the same way. See [Namespace](namespace.md).

### Docs

- Config sections in the docs and examples now follow a class's key: a `@Service class
  Postgres` reads `[service.postgres]` as `config.service.postgres`, instead of a flat
  `[postgres]`. The section, the `Context` key and the log file now share one name, and
  same-named classes in different namespaces no longer share a section. This is a
  convention, not a `Config` change — any structure still works. See
  [Config](config.md#config-structure-convention).
- A `Task`'s `execute()` takes no arguments, by design, and the docs no longer suggest
  giving it an optional parameter to receive the previous step's result, as the 0.2.0
  notes did. Work whose input the caller decides is a [Function](function.md); a value
  that differs per deployment is config, and one that follows from earlier runs is state
  kept in a repository. A pipeline passes a task's result on to a function or a component
  method, not to another task. See
  [Task, Function or Agent?](task.md#task-function-or-agent).
- Corrected pages that had fallen behind 0.3.0: [Entity](entity.md) no longer says a
  duplicate name silently overwrites (it has raised since 0.2.0), [Agent](agent.md) and
  [Component](component.md) describe how a server such as `odf`'s offers agents and
  functions as tools without `mcp_tools()`, and [Service](service.md) examples read their
  own config section.

## 0.2.0

### Added

- **Project**: `Project.from_dict()` now imports the module named under `[project] app`
  (if present) before constructing the `Context` — equivalent to writing `import app` by
  hand before calling `from_config()`/`from_dict()`. `from_config()` gets this for free
  since it delegates to `from_dict()`. Fails fast on a missing/broken module (`ImportError`
  propagates uncaught). See [Project](project.md).
- **Config**: `Config.get()` and `Config[]` now run the key through `normalize()`, same as
  `__getattr__`, so snake_case/kebab-case/PascalCase are interchangeable on every access
  path — including looking a section up by its class-derived name (e.g.
  `config.get("Postgres")` for a `[postgres]` TOML section). See [Config](config.md).
- **Component**: added `McpTool`/`McpToolsProtocol` so a `Component` can expose its own MCP
  tools via an optional `mcp_tools()` method, detected structurally like
  `DetailsProtocol`/`ChartProtocol`. Wiring this into an actual MCP server happens on the
  `odf` side. See [Component](component.md).

### Fixed

- **Namespace**: registering two classes under the same name (via kebab-casing or an
  explicit name) used to silently overwrite the earlier registration. Both registration
  paths now raise `ValueError` naming both colliding classes. See [Namespace](namespace.md).
- **Config**: `Config.__init__` previously stored the given dict by reference, so mutating
  the original dict after passing it to `Project.from_dict()` would silently leak through —
  contradicting the documented read-only/immutable contract. `Config` now owns a deep copy
  instead. See [Config](config.md).

### Changed

- **View**: renamed `ReplayProtocol.replay_field` to `field`, aligning with the generic
  `field`/`fields` naming convention used by every other `View` variant. See [View](view.md).

### Docs

- Clarified that a `Task`'s `execute()` can already accept an optional parameter to receive
  the previous step's return value directly within a `Pipeline`'s own `execute()` — no
  framework change needed, just previously undocumented. The only fixed zero-arg contract
  is `Context.execute(name)`, the external CLI/UI/MCP entry point. See [Pipeline](pipeline.md).
- Fixed the Startup/Shutdown Order diagrams in [Context](context.md), which mislabeled
  `Config` as a `Component`. `Config` isn't decorated with `@Component` and is pre-seeded
  before resolution starts, so `Lifecycle` never iterates over it.
