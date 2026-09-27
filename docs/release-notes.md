# Release Notes

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
