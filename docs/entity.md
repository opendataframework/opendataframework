# Entity

An `Entity` is a named, structured unit of data that the system passes around. It
represents a meaningful piece of information in the domain — a database record, a
configuration object, a sensor reading, a video frame, or any other structured data
that components, repositories, and pipelines work with.

Entities answer one question:

> What does the data look like?

Not where it comes from or how it is processed — that's a [Repository](repository.md)'s
job. Entities are the common language of the application.

---

## When to use Entity

Use `@Entity` when a class represents a structured unit of data that:

* is passed between components, tasks, or pipelines
* has a well-defined shape that the rest of the system depends on
* represents a domain concept worth naming explicitly

Typical examples:

* a user record
* an order
* a sensor reading
* a metric snapshot
* a video frame
* a configuration record

---

## Decorator

The `@Entity` decorator registers the class with the framework as a data structure.
It is a marker — the class is returned unchanged.

### Without arguments

```python
@Entity
@dataclass
class User:
    id: int
    name: str
    email: str
```

### With a name

An optional name can be provided to register the entity under something other than
the kebab-case form of its class name — useful when the class name doesn't match the
domain name you want to look it up by.

```python
@Entity(name="user")
@dataclass
class UserV2:
    id: int
    name: str
    email: str
```

!!! tip "Registering under a name that's already taken"
    Entities are stored in a plain `name → class` dict, keyed by the normalized
    name. If both `User` and `UserV2` above are defined, `UserV2` — being
    decorated second — silently overwrites `User` under the `"user"` key, and
    `Entity.get("user")` returns `UserV2`. There's no error or warning; keep
    explicit names unique across entities you intend to keep.

---

## Defining Entities

The canonical form for an `Entity` is a Python `dataclass`. Dataclasses are lightweight,
require no dependencies, and work naturally with type hints.

### Simple record

```python
@Entity
@dataclass
class User:
    id: int
    name: str
    email: str
```

### Nested structure

```python
@Entity
@dataclass
class Address:
    street: str
    city: str
    country: str


@Entity
@dataclass
class Order:
    id: int
    user_id: int
    address: Address
    total: float
```

### Non-record data

Entities are not limited to database-style records. Any structured unit of data
the system works with can be an entity:

```python
@Entity
@dataclass
class Frame:
    index: int
    timestamp: float
    width: int
    height: int
    data: bytes


@Entity
@dataclass
class Reading:
    sensor_id: str
    timestamp: float
    value: float
    unit: str
```

---

## Relationship to Repository

An `Entity` describes the shape of data. A [Repository](repository.md) manages it —
storing, retrieving, and querying instances of that entity.

```python
@Entity
@dataclass
class User:
    id: int
    name: str
    email: str


@Repository(User)
class Users:

    def get(self, user_id: int) -> User:
        ...

    def save(self, user: User) -> None:
        ...
```

The `@Repository(User)` decorator links the repository to its entity explicitly,
making the relationship visible without requiring inheritance.

!!! tip "Looking up registered entities"
    `Entity` is a namespace — `Entity.get("user")` returns the `User` class (or
    `None` if unregistered), and `dict(Entity.items())` returns every registered
    name → class pair.

---

## What Entity is Not

* **Not a base class.** `User` does not inherit from `Entity`. The decorator marks it;
  inheritance is not involved.

* **Not tied to a database.** An entity represents a structured unit of data — it has
  no implied persistence mechanism. Where and how it is stored is the responsibility
  of a `Repository`.

* **Not a behaviour container.** Entities describe data shape. Business logic belongs
  in a [Component](component.md), [Task](task.md), or [Pipeline](pipeline.md).

---

## Design Notes

**Keep entities focused.** An entity should represent one domain concept. If a class
is growing methods and logic, consider whether that logic belongs in a `Component`
instead.

**Prefer flat structures where possible.** Deeply nested entities are harder to
query and pass around. If nesting grows complex, consider whether the nested type
should be its own entity managed by its own repository.

**Name entities after domain concepts.** `User`, `Order`, `Frame`, `Reading` — not
`UserData`, `OrderRecord`, or `FrameObject`. The entity name is the domain language.
