# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`opendataframework` is the **core framework** package of Open Data
Framework (ODF) — the structural abstractions with zero third-party
dependencies: `Entity`, `Repository`, `Component`, `Service`, `Task`,
`Pipeline`, `Layer`, `Namespace`, `Context`, `Project`, `Config`,
`Logger`, `View`. No UI, no CLI, no MCP server live here.

## Commands

```bash
# Install dependencies (including dev)
poetry install

# Run all tests
poetry run pytest

# Run a single test file
poetry run pytest tests/path/to/test_file.py

# Run a single test
poetry run pytest tests/path/to/test_file.py::test_name
```

Requires Python >=3.14, managed with Poetry. The virtual environment is
at `.venv/`. There is no `docs` or `ui`/`mcp`/`chat` extras group here —
those belong to the sibling `odf` package.

## Architecture

### Mental model

```
Project                  ← composition root; owns everything
└── Context               ← DI container: registers, resolves, and lifecycles components
    └── [Component/Service/Task/Pipeline/Repository]
        └── optionally tagged with a [Layer] (Api, Storage, Analytics, …)
```

`project.context.get(cls)` gives typed access to any resolved instance by class.

### Core abstractions (in dependency order)

| Abstraction | Role | Lifecycle |
|---|---|---|
| `Entity` | Structured data unit (dataclass / ORM model) | none |
| `Repository` | Data access; manages Entities | `on_start()` / `on_stop()` |
| `Component` | DI-managed object with no execution contract | `on_start()` / `on_stop()` |
| `Service` | Long-running Component (worker, backing service) | `setup()` → `run()` → `stop()`; `run()` is backgrounded by the framework |
| `Task` | Finite work unit; called explicitly | `execute()` |
| `Pipeline` | Ordered composition of Tasks/Pipelines | `execute()` |
| `Layer` | Decorator that assigns a Component to a subsystem (`@Api`, `@Storage`, …) | — |

(No `@Api`/`@Service`-backed HTTP server ships in this package — that's
the `odf` package's job. `Layer` tags like `@Api` are still valid here,
they're just an organisational grouping with no runtime behavior of
their own.)

### Decorator usage

```python
@Storage          # Layer decorator (optional, organisational grouping)
@Service          # Execution type
class Postgres:
    def __init__(self, config: Config): ...

@Repository(User) # Declares managed entity
class Users:
    def __init__(self, postgres: Postgres): ...
```

Dependencies are declared only through constructor signatures — the
`Context` builds the dependency graph automatically. No explicit wiring
needed.

### Lifecycle sequence

`project.start()` drives startup in dependency order (leaves first). For each component:
- `Component`/`Repository`: `on_start()` (blocking, must return quickly)
- `Service`: `setup()` (blocking) → `run()` (backgrounded; framework continues after `setup()` returns)

`project.stop()` runs teardown in reverse order.

`project.context.get(cls)` becomes usable only after `project.start()` returns.

### Configuration

```python
project = Project.from_config("config.toml")   # single file
project = Project.from_config("config/prod/")  # directory
```

Different environments → different config paths. No environment flag.

### Key design constraints

- **No circular dependencies.** The `Context` cannot resolve them; restructure using a shared third collaborator.
- **No global mutable state.** Multiple `Project` instances in the same process must be supported.
- **No framework inheritance.** Use decorators and composition; never inherit from framework base classes.
- **No hidden dependencies.** All dependencies must appear in `__init__` signatures.
- **Don't execute pipelines/tasks inside `on_start()`.** It blocks the entire startup sequence.
- **Zero third-party dependencies, and it needs to stay that way.** If a
  change seems to need a new PyPI package, it almost certainly belongs in
  `odf` instead (see below), not here.

## Relationship to `odf`

This package is the **upstream** of a two-repo split (see the original
monorepo's `todo.md` #45 for the full history — an earlier plan staged a
third, unified `docs` repo, since retired in favor of the per-package
docs described below):

- **`odf`** (sibling repo) — CLI (`odf init`/`odf run`), MCP server,
  UI server, chat. Depends on `opendataframework` as a real
  package dependency; imports core symbols via
  `from opendataframework import ...`. This repo has **zero** knowledge
  of `odf` — no imports of it anywhere, not even lazy or
  `TYPE_CHECKING`-only ones. `Project` here is a pure DI composition root
  (`start()`/`stop()` just open/close the `Context`); all UI/MCP
  /chat orchestration lives on the `odf` side, in `odf.server.Server` — a
  wrapper that composes an `opendataframework.Project` and adds
  `start(ui=, mcp=, chat=)` on top of it. If a change here seems to need
  knowledge of `odf`, it belongs in that wrapper instead — flag it rather
  than reintroducing the import.

## Docs

`docs/` holds this package's own mkdocs-material narrative documentation
(`docs/entity.md`, `docs/repository.md`, `docs/view.md`,
`docs/component.md`, `docs/service.md`, `docs/task.md`, `docs/pipeline.md`,
`docs/layer.md`, `docs/namespace.md`, `docs/context.md`, `docs/project.md`,
`docs/config.md`, `docs/logger.md` — one page per module in
`src/opendataframework/`, plus `docs/index.md`/`docs/examples.md`),
built with `mkdocs.yml` at the repo root and deployed to GitHub Pages by
`.github/workflows/docs.yml` on every push to `main`
(`https://opendataframework.github.io/opendataframework/`). It links out
to the sibling `odf` package's own separately-deployed docs site
(`https://opendataframework.github.io/odf/`) rather than bundling that
content here — each package's docs redeploy independently, on its own
push, with no cross-repo CI needed. Changing a core abstraction's public
behavior should come with a matching update to the relevant page here in
the same change, since there's no separate docs repo to flag it to
anymore.

## Examples

`examples/` holds small, focused projects, each isolating one core
abstraction — read `examples/README.md` first. They're a more reliable
source of "how is this actually used" than inventing new usage from the
source alone.
