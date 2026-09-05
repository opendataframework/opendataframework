# Open Data Framework

Lightweight dependency-injection framework for data applications.

!!! info "Looking for the CLI, UI, MCP server, or chat?"
    Those live in the sibling [`odf`](https://opendataframework.github.io/odf/)
    package, which depends on this one. This site covers the core
    framework only — no UI, no CLI, no MCP server.

## Why

Most data projects end up solving the same structural problems repeatedly: how to wire
dependencies, manage component lifecycles, and keep configuration separate from code.
This framework provides that plumbing as a small set of reusable abstractions —
`Entity`, `Repository`, `Component`, `Service`, `Task`, `Pipeline` — so it doesn't need
to be reinvented by hand in every project.

!!! tip "Want a ready-made project layout instead?"
    Scaffolding an actual project from a template is the
    [`odf`](https://opendataframework.github.io/odf/) package's job — this is what
    that scaffold is built on.

## Getting Started

Install:

```bash
pip install opendataframework
```

A minimal project is a config file plus an `app/` package:

```text
.
├── config.toml
├── main.py
└── app/
    ├── __init__.py
    ├── entities.py
    ├── repositories.py
    └── storages.py
```

`app/entities.py` — the data unit:

```python
from dataclasses import dataclass

from opendataframework import Entity


@Entity
@dataclass
class User:
    id: int | None
    name: str
```

`app/storages.py` — a `Component` wired from config, doing the actual I/O:

```python
import sqlite3

from opendataframework import Component, Config


@Component
class SQLite:
    def __init__(self, config: Config) -> None:
        self.conn = sqlite3.connect(config.get("sqlite").get("path"))
        self.conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")
```

`app/repositories.py` — the `Repository`, depending on the storage:

```python
from opendataframework import Repository

from app.entities import User
from app.storages import SQLite


@Repository(User)
class Users:
    def __init__(self, sqlite: SQLite) -> None:
        self.db = sqlite

    def all(self) -> list[User]:
        rows = self.db.conn.execute("SELECT id, name FROM users").fetchall()
        return [User(id=r[0], name=r[1]) for r in rows]

    def save(self, user: User) -> None:
        self.db.conn.execute("INSERT INTO users (id, name) VALUES (?, ?)", (user.id, user.name))
        self.db.conn.commit()
```

Config file (`config.toml`):

```toml
[sqlite]
path = "app.db"
```

Main file (`main.py`):

```python
from opendataframework import Project

from app.entities import User
from app.repositories import Users

project = Project.from_config("config.toml")
project.start()

users = project.context.get(Users)
users.save(User(id=None, name="Ada"))
print(users.all())
```

`project.start()` blocks until every component has completed its initialisation stage —
there is no hidden latency on first access. Adding a new component means declaring its
dependencies in the constructor, not writing wiring code — a config section is only
needed if the component reads from `Config` itself.

!!! tip "Full lifecycle and usage patterns"
    See [Project](project.md).

!!! tip "More worked, runnable projects"
    Each isolating exactly one core abstraction — see [Examples](examples.md).

## Core Concepts

Each concept below has a dedicated doc with the full interface, decorator usage, and
worked examples.

| Abstraction | Role |
|---|---|
| [Entity](entity.md) | Structured data unit (dataclass / ORM model) |
| [Repository](repository.md) | Data access; manages Entities |
| [View](view.md) | Declares which representation and field(s) best fit a Repository's data |
| [Component](component.md) | DI-managed object with no execution contract |
| [Service](service.md) | Long-running Component (worker, backing service) |
| [Task](task.md) | Finite work unit; called explicitly |
| [Pipeline](pipeline.md) | Ordered composition of Tasks/Pipelines |
| [Layer](layer.md) | Decorator that assigns a Component to a subsystem |

Supporting the above are [Context](context.md), [Config](config.md),
[Project](project.md), [Namespace](namespace.md), and [Logger](logger.md) —
the machinery that registers, resolves, and organises everything.

| Machinery | Role |
|---|---|
| [Context](context.md) | Registers, resolves, and lifecycles every component, in dependency order |
| [Config](config.md) | Wraps loaded TOML into the nested object components read via DI |
| [Project](project.md) | Composition root; owns the `Context` and starts/stops the application |
| [Namespace](namespace.md) | Base class behind every decorator (`@Component`, `@Service`, …); not an end-user concept |
| [Logger](logger.md) | Per-component logging handle, injected already bound to its own class name |
