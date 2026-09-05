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
project = Project.from_dict({
    "postgres": {"database-url": "postgresql://localhost/mydb"}
})
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
        self.url = config.get("postgres").database_url
```

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
config.database_url   # "postgresql://localhost/mydb"
config["database-url"]  # same
```

### Nested sections

Accessing a key whose value is a dict returns a nested `Config` object,
so access can be chained:

```toml
[postgres]
database-url = "postgresql://localhost/mydb"
port = 5432
```

```python
config.postgres.database_url
config["postgres"]["port"]
```

---

## Safe access with `get()`

`Config.get(key, default)` returns the value at `key`, or `default` if the
key is absent. It does not raise:

```python
config.get("host", "localhost")   # "localhost" if key absent
```

!!! note "get() does not normalize the key — only attribute access does"
    `normalize()` only runs on the dot-access path. `get()` and `[]` look up
    `key` exactly as given, against whatever casing appears in the loaded
    config. For a `[postgres]` TOML section, `config.get("postgres")` and
    `config["postgres"]` find it, but `config.get("Postgres")` misses —
    silently returning an empty `Config` rather than raising, since a
    missing key with no `default` doesn't error.

If `default` is omitted and the key is absent, `get()` returns an empty
`Config` rather than `None`. This makes scoping into a section safe by
default — a component can grab its own slice of the config and chain
further access onto it without guarding against the section being missing:

```python
cfg = config.get("postgres")

cfg.database_url          # AttributeError if missing
cfg.get("port", 5432)     # 5432 if key absent
```

This lets each component retrieve its own slice without coupling it to the
full config structure, while leaving the full config accessible for
cross-cutting needs:

```python
@Component
class Postgres:
    def __init__(self, config: Config) -> None:
        cfg = config.get("postgres")
        self.url = cfg.database_url
        self.pool_size = cfg.get("pool-size", 10)


@Component
class Observability:
    def __init__(self, config: Config) -> None:
        # reads from multiple sections
        self.log_level = config.get("observability").get("log-level", "INFO")
        self.metrics_port = config.get("observability").get("metrics-port", 9090)
```

---

## Config structure convention

The framework imposes no required structure on the config file. By
convention, each top-level section is keyed by the kebab-case name of the
class it configures — `Postgres` reads `[postgres]`, `UsersApi` reads
`[users-api]` — regardless of whether that class is a `Component`, `Service`,
`Repository`, or anything else:

```toml
[postgres]
database-url = "postgresql://localhost/mydb"
pool-size = 10

[users-api]
host = "0.0.0.0"
port = 8080

[users]
table = "users"
schema = "public"
```

This convention is not enforced — components access whatever key they
declare in their constructor, and nested sections remain reachable via
chained `.get()`/attribute access (e.g. `config.get("outer").get("inner")`)
if a project's config genuinely needs them. Using flat, class-named sections
consistently makes config files predictable and easy to navigate, and keeps
a component's config key closely mirroring the class name already used to
address it elsewhere (e.g. `Context.start("Postgres")`). It is independent
of [Layer](layer.md), which groups components for the UI and has no bearing
on config structure.

!!! tip "Same convention, everywhere"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's
    UI and CLI also address components by this same class-derived name. It's
    a convention, not something `Config` enforces — since `get()`/`[]` don't
    normalize casing, the TOML section key has to match it exactly for
    lookups to find it.

---

## What Config is Not

* **Not a validator.** `Config` does not validate types, required fields, or
  value ranges. Validation is the component's own responsibility.

* **Not injectable into every component automatically.** Only components that
  explicitly declare `config: Config` in their constructor receive it. Components
  that do not need configuration simply omit the parameter.

* **Not mutable.** `Config` provides read-only access. Configuration is set at
  project creation time and does not change at runtime.
