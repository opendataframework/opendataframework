# Repository

A `Repository` manages `Entities`. It abstracts persistence and data access concerns
away from business logic — components, tasks, and pipelines ask the repository for
data without needing to know where it comes from or how it is stored.

Repositories answer one question:

> Where does the data come from?

The rest of the system should not need to know.

---

## When to use Repository

Use `@Repository` when a class is responsible for:

* querying and retrieving entities
* persisting or updating entities
* abstracting a data source — a database, an external API, a file, a stream

Typical examples:

* a database table wrapper
* an external API client that returns structured data
* a file reader that produces records
* a cache layer over another repository

---

## Decorator

The `@Repository` decorator takes the `Entity` class it manages as an argument. This
makes the relationship between repository and entity explicit and visible.

```python
@Repository(User)
class Users:
    ...
```

### With a name

```python
@Repository(User, name="users")
class Users:
    ...
```

### Combined with a Layer

```python
@Storage
@Repository(User)
class Users:
    ...
```

---

## Interface

A `Repository` has no strictly required methods — only the operations relevant to the
data source need to be implemented. The following are conventional starting points.

`opendataframework.repository` exposes `runtime_checkable` protocols —
`ReadableProtocol`, `WritableProtocol`, and `StreamableProtocol` — so tooling can
detect these capabilities via `isinstance()` without requiring every repository to
implement all of them:

```python
from opendataframework.repository import ReadableProtocol, StreamableProtocol, WritableProtocol

isinstance(users, ReadableProtocol)    # True if `all()` is implemented
isinstance(users, WritableProtocol)    # True if `save()` and `delete()` are implemented
isinstance(webcam, StreamableProtocol) # True if `stream()` is implemented
```

```python
@Repository(User)
class Users:

    def get(self, user_id: int) -> User:
        # retrieve a single entity by identifier
        ...

    def all(self) -> list[User]:
        # retrieve all entities
        ...

    def save(self, user: User) -> None:
        # persist a new or updated entity
        ...

    def delete(self, user_id: int) -> None:
        # remove an entity by identifier
        ...
```

Not all repositories need all four. A read-only data source implements only `get()`
and `all()`. A write-only sink implements only `save()`.

---

## Streaming

Some data sources are live and unbounded — a webcam feed, a sensor reading queue, a
subscription to a message topic. `all()` doesn't fit: there's no "every record", only
entities arriving for as long as something keeps listening. `stream()` is the
repository's answer to that case:

```python
from opendataframework.repository import StreamableProtocol

@Storage
@Repository(Frame)
class Webcam:

    def stream(self) -> Iterator[Frame]:
        while True:
            frame = self._read_next_frame()
            yield frame
```

`StreamableProtocol` is independent of `ReadableProtocol`/`WritableProtocol` — a
repository can be streamable only, readable only, or any combination. Detected the
same way:

```python
isinstance(webcam, StreamableProtocol)  # True if `stream()` is implemented
```

!!! tip "StreamableProtocol only drives lifecycle, not display"
    `StreamableProtocol` only drives the stream's lifecycle — the background
    thread, and whether `start_stream()`/`stop_stream()` are allowed. It says
    nothing about how the UI should *display* what comes out of `stream()`.
    That's a separate, optional declaration — see [View](view.md)'s
    `StreamingVideoView`/`StreamingAudioView`.

### Starting and stopping a stream

Unlike `all()` or `get()`, which run once when called, a stream is something that gets
explicitly started and stopped — the `Context` drives one background thread per
repository that iterates `stream()` and fans each entity out to every current
subscriber, so multiple consumers share a single running feed instead of each
triggering an independent call to `stream()`.

Two more, both optional, hooks bracket that background thread's lifetime:

```python
@Storage
@Repository(Frame)
class Webcam:

    def __init__(self, config: Config):
        self.device = config.get("webcam").get("device", 0)
        self.capture = None

    def open_stream(self):
        # blocking; called once, right before the background thread starts
        self.capture = self._open_device(self.device)

    def close_stream(self):
        # called once the background thread has fully exited — whether that's
        # because streaming was stopped, the source ended on its own (e.g. the
        # device disconnected), or stream() raised
        self.capture.release()
        self.capture = None

    def stream(self) -> Iterator[Frame]:
        while True:
            ok, image = self.capture.read()
            if not ok:
                break
            yield self._encode(image)
```

`open_stream()`/`close_stream()` are **not** the same as `on_start()`/`on_stop()` (see
below): `on_start()`/`on_stop()` run once, for the whole `Project`'s lifetime.
`open_stream()`/`close_stream()` run every time streaming is started and stopped, which
may happen many times over the `Project`'s life — they tie an expensive resource (a
camera handle, a socket) to the stream actually being active, not to the process
being up. A repository streaming from an already-open resource (a queue, a socket
handed in via the constructor) needs neither hook.

---

## Dependency Injection

Like all components, a `Repository` declares its dependencies through the constructor.
The `Context` resolves and injects them automatically.

```python
@Storage
@Repository(User)
class Users:

    def __init__(
        self,
        config: Config,
    ):
        self.config = config
        self.connection = None

    def on_start(self):
        self.connection = self._connect(self.config.database_url)

    def on_stop(self):
        self.connection.close()

    def get(self, user_id: int) -> User:
        ...

    def save(self, user: User) -> None:
        ...

    def _connect(self, url):
        ...
```

---

## Full Examples

### Database repository

```python
@Storage
@Repository(User)
class Users:

    def __init__(
        self,
        config: Config,
    ):
        self.config = config
        self.connection = None

    def on_start(self):
        self.connection = self._connect(self.config.database_url)

    def on_stop(self):
        self.connection.close()

    def get(self, user_id: int) -> User:
        row = self.connection.query(
            "SELECT * FROM users WHERE id = ?", user_id
        )
        return User(**row)

    def all(self) -> list[User]:
        rows = self.connection.query("SELECT * FROM users")
        return [User(**row) for row in rows]

    def save(self, user: User) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO users VALUES (?, ?, ?)",
            user.id, user.name, user.email,
        )

    def delete(self, user_id: int) -> None:
        self.connection.execute(
            "DELETE FROM users WHERE id = ?", user_id
        )

    def _connect(self, url):
        ...
```

### Read-only external source

Not all repositories write. An external API or data stream may be read-only:

```python
@Storage
@Repository(Reading)
class SensorFeed:

    def __init__(
        self,
        config: Config,
    ):
        self.config = config
        self.client = None

    def on_start(self):
        self.client = self._connect(self.config.feed_url)

    def on_stop(self):
        self.client.disconnect()

    def get(self, sensor_id: str) -> Reading:
        raw = self.client.fetch(sensor_id)
        return Reading(**raw)

    def all(self) -> list[Reading]:
        raw = self.client.fetch_all()
        return [Reading(**r) for r in raw]

    def _connect(self, url):
        ...
```

### Live streaming feed

A repository can be stream-only too — no `get()`/`all()`/`save()` at all, just a live
feed, with `open_stream()`/`close_stream()` tying the device to the stream's own
start/stop rather than the whole `Project`'s lifetime:

```python
@Storage
@Repository(Frame)
class Webcam:

    def __init__(
        self,
        config: Config,
    ):
        self.device = config.get("webcam").get("device", 0)
        self.capture = None

    def open_stream(self):
        self.capture = self._open_device(self.device)

    def close_stream(self):
        self.capture.release()
        self.capture = None

    def stream(self) -> Iterator[Frame]:
        while True:
            ok, image = self.capture.read()
            if not ok:
                break
            yield self._encode(image)

    def _open_device(self, device):
        ...

    def _encode(self, image):
        ...
```

### Using a repository in a Task

```python
@Analytics
@Task
class MetricsFetcher:

    def __init__(
        self,
        feed: SensorFeed,
        metrics: Metrics,
    ):
        self.feed = feed
        self.metrics = metrics

    def execute(self):
        readings = self.feed.all()
        for reading in readings:
            self.metrics.save(reading)
        return readings
```

---

## What Repository is Not

* **Not a service.** A `Repository` manages data access — it does not run indefinitely
  or manage an execution environment. If the data source requires a long-running process,
  that process is a `Service` that the repository depends on. A `stream()`
  implementation is still just an iterator — the background thread that keeps it
  running and fans it out to subscribers is the framework's concern, not the
  repository's; the repository author never manages threading directly.

* **Not a base class.** `Users` does not inherit from `Repository`. The decorator
  registers it and links it to its entity; inheritance is not involved.

* **Not responsible for business logic.** A repository retrieves and persists entities.
  Transforming, validating, or acting on that data belongs in a `Component`, `Task`,
  or `Pipeline`.

---

## Design Notes

**One repository per entity type.** A repository manages one kind of entity. If you
find a repository managing two unrelated entities, split it.

**Keep queries in the repository.** Filtering, sorting, and pagination belong in the
repository — not in the components that use it. Components should ask for what they
need, not receive everything and filter themselves.

**Read-only repositories are valid.** Not every data source supports writes. A
repository that only implements `get()` and `all()` is a complete and legitimate
design.

**Streaming is orthogonal, not a replacement.** `stream()` doesn't replace
`get()`/`all()` — a repository can be readable, writable, streamable, or any
combination, since each capability is detected independently via its own protocol.
