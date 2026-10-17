# Config

`Config` is the framework's configuration abstraction. It wraps a nested
dictionary — typically loaded from TOML — and exposes it through attribute
and item access with automatic name normalisation. Components that need
configuration declare `config: Config` as a constructor dependency and
receive it via DI.

---

## Loading

### From a file

```python
project = Project.from_config("config.toml")
```

### From a directory

All `*.toml` files in the directory are loaded in alphabetical order and
deep-merged. Later files override earlier ones for scalar values; nested
dicts are merged recursively.

```python
project = Project.from_config("config/prod/")
```

A typical layout:

```text
config/
├── analytics.toml
├── api.toml
├── data.toml
└── storage.toml
```

### From a dict

Primarily for testing or programmatic configuration:

```python
project = Project.from_dict(
    {"component": {"postgres": {"database-url": "postgresql://localhost/mydb"}}}
)
```

---

## Receiving config in a component

Any component that declares `config: Config` in its constructor receives
the full project config automatically:

```python
from opendataframework import Component, Config


@Component
class Postgres:
    def __init__(self, config: Config) -> None:
        self.url = config.component.postgres.database_url
```

By convention it reads its own section, `[component.postgres]` — see
[Config structure convention](#config-structure-convention).

Only components that need configuration have to declare this dependency.
Components that do not need it simply omit it.

---

## Accessing values

### Attribute access

Both snake_case and kebab-case names are accepted interchangeably:

```toml
database-url = "postgresql://localhost/mydb"
```

```python
config.database_url  # "postgresql://localhost/mydb"
config["database-url"]  # same
```

This works in both directions: keys in the file are normalised too, so
`database_url = "..."` in TOML is found by `config.database_url`,
`config["database-url"]` and `config.get("database_url")` alike. Two keys
in the same table that normalise to the same name (e.g. `database_url` and
`database-url`) raise a `ValueError` rather than one silently winning.

### Nested sections

Accessing a key whose value is a dict returns a nested `Config` object,
so access can be chained:

```toml
[component.postgres]
database-url = "postgresql://localhost/mydb"
port = 5432
```

A dotted TOML header is a table inside a table, so this is reached in two
steps:

```python
config.component.postgres.database_url
config["component"]["postgres"]["port"]
```

---

## Safe access with `get()`

`Config.get(key, default)` returns the value at `key`, or `default` if the
key is absent. It does not raise:

```python
config.get("host", "localhost")  # "localhost" if key absent
```

!!! note "get() and [] normalize the key too"
    `normalize()` runs on every access path — attribute, `[]`, and `get()`
    alike. For a `[component.postgres]` TOML section,
    `config.component.postgres`, `config["component"]["postgres"]`, and
    `config.get("Component").get("Postgres")` all find it.

If `default` is omitted and the key is absent, `get()` returns an empty
`Config` rather than `None`. This makes scoping into a section safe by
default — a component can grab its own slice of the config and chain
further access onto it without guarding against the section being missing:

```python
cfg = config.get("component").get("postgres")

cfg.database_url  # AttributeError if missing
cfg.get("port", 5432)  # 5432 if key absent
```

This lets each component retrieve its own slice without coupling it to the
full config structure, while leaving the full config accessible for
cross-cutting needs:

```python
@Component
class Postgres:
    def __init__(self, config: Config) -> None:
        cfg = config.component.postgres
        self.url = cfg.database_url
        self.pool_size = cfg.get("pool-size", 10)


@Component
class Observability:
    def __init__(self, config: Config) -> None:
        cfg = config.component.observability
        self.log_level = cfg.get("log-level", "INFO")
        # reads another component's section too
        self.database_url = config.component.postgres.database_url
```

---

## Config structure convention

The framework imposes no required structure on the config file. By
convention, a class reads the section named after its
[key](context.md#by-key-single-component-control), `<namespace>.<name>` — the
same key the `Context` addresses it by and its log file is named after. A
`@Service class Postgres` reads `[service.postgres]`, an
`@Repository(User) class Users` reads `[repository.users]`:

```toml
[service.postgres]
database-url = "postgresql://localhost/mydb"
pool-size = 10

[service.users-api]
host = "0.0.0.0"
port = 8080

[repository.users]
table = "users"
schema = "public"
```

```python
@Service
class Postgres:
    def __init__(self, config: Config) -> None:
        cfg = config.service.postgres
        ...
```

A name is unique only within its namespace, so the namespace keeps two
same-named classes apart here too: a `@Task class Loader` reads
`[task.loader]` and an `@Agent class Loader` reads `[agent.loader]`.

This convention is not enforced — components access whatever key they
declare in their constructor, and nested sections remain reachable via
chained `.get()`/attribute access (e.g. `config.get("outer").get("inner")`)
if a project's config genuinely needs them. Using the key
consistently makes config files predictable and easy to navigate, and means
a class has one name everywhere: `[service.postgres]` in config,
`Context.start("service.postgres")`, `logs/service.postgres.log`. The section
moves with the namespace — changing `@Component` to `@Service` moves
`[component.postgres]` to `[service.postgres]`. It is independent
of [Layer](layer.md), which is an organisational grouping and has no bearing
on config structure.

!!! tip "Same convention, everywhere"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI and CLI also address components by this same key. It's a convention,
    not something `Config` enforces — but since every access path
    normalizes casing, `config.service.postgres` finds the section however
    the TOML header itself is cased.

---

## The `[project]` section is reserved

Unlike every other section (which is a convention, not enforced),
`[project]` is read directly by `Project.from_config()`/`Project.from_dict()`
itself, before any `Config` object exists — so its keys must be written
exactly as shown, not normalized like the accessors above:

```toml
[project]
log-dir = "logs"   # see Logger
app = "app"        # see Project — imports the app package
```

See [Project](project.md#pointing-at-the-app-package) and
[Logger](logger.md) for what each key does.

---

## What Config is Not

* **Not a validator.** `Config` does not validate types, required fields, or
  value ranges. Validation is the component's own responsibility.

* **Not injectable into every component automatically.** Only components that
  explicitly declare `config: Config` in their constructor receive it. Components
  that do not need configuration simply omit the parameter.

* **Not mutable.** `Config` provides read-only access. Configuration is set at
  project creation time and does not change at runtime. `Config` deep-copies
  the dict it's given at construction time, so mutating a dict you passed to
  `Project.from_dict()` after the fact has no effect on the `Config` a
  component already received.
