# Open Data Framework

[![PyPI](https://img.shields.io/pypi/v/opendataframework)](https://pypi.org/project/opendataframework/)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-opendataframework.github.io-blue)](https://opendataframework.github.io/opendataframework/)

Lightweight dependency-injection framework for data applications.

This package provides structural abstractions —
`Entity`, `Repository`, `Component`, `Service`, `Task`, `Pipeline`,
`Layer`, `Namespace`, `Context`, `Project`, `Config`, `Logger`, `View`
— with zero third-party dependencies. No UI, no CLI, no MCP server.

> Need the CLI, UI, or MCP server? That's the
> [`odf`](https://opendataframework.github.io/odf/) package, which
> depends on this one.

Full documentation: **[opendataframework.github.io/opendataframework](https://opendataframework.github.io/opendataframework/)**

---

# Why

Most data projects solve the same structural problems repeatedly: how to
wire dependencies, manage component lifecycles, and keep configuration
separate from code. This framework provides that plumbing as a small set
of reusable abstractions — `Entity`, `Repository`, `Component`, `Service`,
`Task`, `Pipeline` — so it doesn't need to be reinvented by hand in every
project.

> Want a ready-made project layout instead? Scaffolding an actual project
> from a template is the [`odf`](https://opendataframework.github.io/odf/)
> package's job — this is what that scaffold is built on.

---

# Getting Started

Install:

```bash
pip install opendataframework
```

A minimal project needs three things: an entity and repository, a config
file, and a main file that starts the `Project`.

Application code (`app.py`):

```python
import sqlite3
from dataclasses import dataclass

from opendataframework import Component, Config, Entity, Repository


@Entity
@dataclass
class User:
    id: int
    name: str


@Component
class SQLite:
    def __init__(self, config: Config):
        self.conn = sqlite3.connect(config.sqlite.path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)"
        )


@Repository(User)
class Users:
    def __init__(self, sqlite: SQLite):
        self.db = sqlite.conn

    def all(self) -> list[User]:
        rows = self.db.execute("SELECT id, name FROM users").fetchall()
        return [User(id=row[0], name=row[1]) for row in rows]

    def save(self, user: User) -> None:
        self.db.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (user.id, user.name))
        self.db.commit()
```

Config file (`config.toml`):

```toml
[sqlite]
path = "app.db"
```

Main file (`main.py`):

```python
from opendataframework import Project

from app import User, Users

project = Project.from_config("config.toml")
project.start()

users = project.context.get(Users)
users.save(User(id=1, name="Ada"))

print(users.all())
```

`project.start()` blocks until every component has completed its
initialisation stage — there is no hidden latency on first access. Adding
a new component means declaring its dependencies in the constructor, not
writing wiring code — a config section is only needed if the component
reads from `Config` itself.

---

# Core Concepts

## Entity

A structured unit of data the system works with.

```python
@Entity
@dataclass
class User:
    id: int
    name: str
```

## Repository

Manages Entities; abstracts persistence away from business logic.

```python
@Repository(User)
class Users:
    def get(self, user_id: int) -> User: ...
    def save(self, user: User) -> None: ...
```

## View

An optional, single declaration a `Repository` attaches to itself: which
representation (table, map, image, video, ...) and field(s) best fit its
data. Metadata only — this package renders nothing itself. See
[View](https://opendataframework.github.io/opendataframework/view/).

```python
@Repository(Store)
class Stores:
    def all(self) -> list[Store]: ...

    def data_view(self) -> LocationView:
        return LocationView(fields=("lat", "lon"))
```

## Component

A `Context`-managed object with no required execution contract — wired in
and given its dependencies through the constructor.

```python
@Component
class Classifier:
    def fit(self, data): ...
    def predict(self, data): ...
```

## Service

A long-running executable, wired through DI the same way as a `Component` but
with a mandatory `setup → run → stop` lifecycle — an API server, worker
process, or scheduler. `run()` blocks by nature; the framework backgrounds it
automatically.

```python
@Service
class Postgres:
    def setup(self): ...
    def run(self): ...
    def stop(self): ...
```

## Task

A finite executable, wired through DI the same way as a `Component` —
performs one bounded unit of work, once.

```python
@Task
class MetricsFetcher:
    def execute(self): ...
```

## Pipeline

Coordinates multiple `Task`s (and optionally other `Pipeline`s) into an
ordered workflow.

```python
@Pipeline
class DailyAnalytics:
    def execute(self): ...
```

## Layer

An organisational grouping — which subsystem a component belongs to
(`Api`, `Storage`, `Analytics`, `Messaging`, `Monitoring`, `Security`, or
custom). Independent of execution type.

```python
@Storage
@Service
class Postgres: ...
```

## Namespace

The base class underlying every framework decorator — `Entity`,
`Component`, `Service`, `Task`, `Pipeline`, `Repository`, and `Layer` are
all `Namespace` subclasses, each with its own independent name → class
mapping. A framework extension point, not something end users subclass
directly. See
[Namespace](https://opendataframework.github.io/opendataframework/namespace/).

## Config

Typed, dot-accessible view over a configuration dict — snake_case and
kebab-case are interchangeable, and nested sections chain naturally.
Resolved automatically into the container by `Project.from_config`.

```python
@Storage
@Service
class Postgres:
    def __init__(self, config: Config):
        self.host = config.postgres.host
```

## Logger

Per-component logging handle, injectable via constructor DI like any
other dependency — writes land in that component's own log file with no
name argument needed.

```python
@Task
class ExportUsers:
    def __init__(self, users: Users, logger: Logger):
        self.users = users
        self.logger = logger

    def execute(self) -> None:
        self.logger.info("export starting")
```

## Context

Registers, resolves, and lifecycles every component in dependency order.
No circular dependencies — restructure with a shared third collaborator
instead.

```python
component = project.context.get(UsersApi)   # typed, by class
```

## Project

The composition root — owns `Context` and configuration, and is the
single entry point for starting and stopping the application.

```python
project = Project.from_config("config.toml")
project.start()
```

Multiple independent `Project` instances are supported in the same
process; there is no global mutable state.

---

# Design Guidelines

* **Prefer composition** — decorators (`@Api @Service`), not inheritance
  from framework base classes.
* **Keep responsibilities focused** — one primary reason to change per
  class.
* **Avoid global mutable state** — framework state belongs to objects.
* **Avoid hidden magic** — dependencies must be visible in constructor
  signatures.

---

# Mental Model

```text
Data is represented by Entities.
Repositories manage data.

Components provide capabilities.
Services run for extended periods.
Tasks execute bounded work.
Pipelines coordinate tasks (and other pipelines).

Layers organize components.
Context manages components and repositories.
Project owns everything.
```

---

# Examples

See [`examples/`](examples/README.md) — small, focused projects each
isolating one core abstraction.

> For the CLI, UI, MCP server, and chat surface 
> built on top of this package, see `odf`.

---

# Development

Requires Python >=3.14, managed with [Poetry](https://python-poetry.org/).

```bash
poetry install       # install dependencies, including dev
poetry run pytest    # run the test suite
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to propose changes.

---

# License

[MIT](LICENSE)
