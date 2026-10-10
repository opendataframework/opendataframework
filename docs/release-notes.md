# Release Notes

## 0.3.0 (unreleased)

### Added

- **Agent**: added `@Agent`, an execution type for goal-driven work whose steps are decided
  at run time — typically by a language model. An agent is a class with a single `invoke()`
  method whose signature is its author's to choose; everything it may act on is declared
  through its constructor like any other dependency, so it can also be injected into a
  `Pipeline`, a `Service`, or another agent. `context.call("librarian", question=...)`
  invokes one by registered name, `context.parameters(Librarian)` returns the parameters of
  its `invoke()`, and every invocation is logged like a `Task`'s `execute()`. `@Agent` on a
  class without `invoke()` raises `TypeError` at decoration time. `AgentProtocol` documents
  the interface. The framework still ships no model client and no agent loop — `invoke()` is
  where a library or provider SDK of your choice goes. See [Agent](agent.md).
- **Function**: added `@Function`, a marker that makes a plain function known to the
  framework the way `@Component` does a class — so an existing function-based codebase can
  be adopted without a class refactor first. The function is returned unchanged, and direct
  calls behave exactly as before. Through the `Context`, parameters annotated with a managed
  type are injected and the rest are call arguments: `context.call("load-data", path=...)`
  calls by registered name, `context.get(load_data)` returns the function with its
  dependencies bound, `context.functions` lists what was resolved, and
  `context.parameters(func)` returns the parameters a caller must supply. A class — or
  another function — asks for one by naming it in its signature,
  `Annotated[Callable[..., int], load_data]`, and receives it with its dependencies bound
  and its calls logged; the function then takes part in dependency ordering and cycle
  detection. Functions have no lifecycle and aren't in `context.instances`. See
  [Function](function.md).
- **View**: added `ContentMetadata`/`ContentMetadataProtocol` so a `Repository` whose view
  points at content (`ImageView`/`VideoView`/`AudioView`/`DocumentView`) can declare, per
  record, that content's `filename` and `content_type` via an optional
  `content_metadata(entity)` method, detected structurally like `DataViewProtocol`/
  `ReplayProtocol`. The values needn't be entity fields — a repository may derive them or
  return constants. Existing views are unchanged. Using this to label, type and offer
  content for download happens on the `odf` side. See [View](view.md).

### Changed

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
