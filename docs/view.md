# View

A `Repository` may optionally implement `data_view()` to say two things about
its data: which kind of representation fits it — a name, like `TableView`,
`LocationView`, `DocumentView` — and which field(s) on the entity are the
ones worth looking at. That's all it is: a small piece of self-describing
metadata a repository attaches to itself.

`opendataframework` has zero third-party dependencies and renders nothing
itself — `data_view()` doesn't draw a table or open a map, it just answers
the question a renderer would need answered:

> Given a repository that already exposes data somehow, what's the single
> best representation of one of its records, and which field(s) does that
> representation hinge on?

!!! tip "Seeing it in practice"
    If you're running a project through `odf`'s UI, `data_view()` is what
    that UI reads to decide how a repository's data shows up when you open
    it — as a table, a map, a video player, and so on. That's just today's
    one consumer, though: the declaration is metadata a repository carries
    regardless of whether `odf` — or anything else — is reading it.

This is independent of `ReadableProtocol`/`WritableProtocol`/
`StreamableProtocol` (see [Repository](repository.md)) — those still gate
whether the underlying operation (`all()`/`save()`/`delete()`/`stream()`) is
actually allowed. `data_view()` never decides that; it only describes which
single representation best fits the data once it's already accessible.

See [`examples/06-logger-and-view/`](examples.md) for a full runnable
project built around this.

---

## Why a single view

A repository picks exactly **one** view — there is no mixing. A repository
whose data is best shown on a map doesn't also carry a raw-table
representation of the same records; the map's marker popups already show
every field. This keeps each repository's self-description unambiguous: one
capability, one representation.

!!! tip "A consumer may still offer a table fallback"
    "Exactly one view" is about what a repository *declares* — a consumer is
    still free to layer a fallback on top. The sibling `odf` package's UI
    does this for `LocationView`/`TimeseriesView`: alongside the declared
    map or timeline, it offers a one-click toggle to the same plain table
    that any readable dataclass-entity repository gets by default when it
    implements no `data_view()` at all (see [below](#the-default-table)).
    That toggle isn't a second `data_view()` — the repository still declared
    one view — it's the consumer choosing to render that declaration two
    ways.

---

## The default: table

A repository doesn't need to implement `data_view()` at all. A
`ReadableProtocol` repository with a dataclass entity is represented as a
plain table by default — every field as a column, in declaration order:

```python
@Storage
@Repository(User)
class Users:

    def all(self) -> list[User]: ...
    def save(self, user: User) -> None: ...
    def delete(self, user_id: int) -> None: ...
```

`Users` needs no `data_view()` — it just gets the default table, exactly as
if `ReadableProtocol`/`WritableProtocol` were the only things that mattered.

A repository only implements `data_view()` when it wants something other
than the default table, or wants to override which columns show:

```python
from opendataframework import DataViewProtocol, TableView

@Storage
@Repository(User)
class Users:

    def all(self) -> list[User]: ...

    def data_view(self) -> TableView:
        return TableView(fields=("id", "name"))  # hide email from the table
```

`data_view()` is detected structurally via `DataViewProtocol`
(`opendataframework.view.DataViewProtocol`, `@runtime_checkable`) — no base
class or decorator required:

```python
class DataViewProtocol(Protocol):
    def data_view(self) -> DataView: ...
```

---

## The `DataView` family

`DataView` is a closed set of variants, each pointing at its field(s)
generically — `field: str` for one field, `fields: tuple[str, ...]` for
several. The meaning comes from which variant it is, not from the attribute
name — the variant *is* the "view name" from the description above.

| Variant | Fields | Typical representation | Repository shape |
|---|---|---|---|
| `TableView` | `fields: tuple[str, ...] \| None` | rows and columns (the implicit default) | `ReadableProtocol` |
| `ImageView` | `field: str` | a still image per record | `ReadableProtocol` |
| `VideoView` | `field: str` | a bounded, seekable clip per record | `ReadableProtocol` |
| `StreamingVideoView` | `field: str` | a live feed | `StreamableProtocol` |
| `AudioView` | `field: str` | a bounded, seekable clip per record | `ReadableProtocol` |
| `StreamingAudioView` | `field: str` | a live feed | `StreamableProtocol` |
| `DocumentView` | `field: str` | an arbitrary JSON-shaped value per record | `ReadableProtocol` |
| `LocationView` | `fields: (lat_field, lon_field)` | one point per record | `ReadableProtocol` |
| `TimeseriesView` | `field: str` (the timestamp field) | the entity's other numeric fields against a timestamp | `ReadableProtocol` |

Every variant except `TableView` needs exactly the repository capability its
"Repository shape" column names — a `StreamingVideoView`/`StreamingAudioView`
repository must implement `stream()` (`StreamableProtocol`) for a live
representation to be meaningful at all; everything else needs `all()`
(`ReadableProtocol`) to list records. How each variant actually gets
rendered — a table widget, a map component, a video player — is entirely up
to whatever's consuming `data_view()`; this package only carries the
declaration.

---

## Examples

### Location — a map, not a table

```python
from opendataframework import LocationView, Repository, Storage

@Storage
@Repository(Store)
class Stores:

    def all(self) -> list[Store]: ...
    def save(self, store: Store) -> None: ...
    def delete(self, store_id: int) -> None: ...

    def data_view(self) -> LocationView:
        return LocationView(fields=("lat", "lon"))
```

`Stores` declares itself as location data, not tabular data — no separate
table representation alongside it. A consumer like `odf`'s UI turns this
into one marker per record, with each record's fields available on click,
the same fields that would have shown as table columns.

### Streaming video — a live feed

```python
from opendataframework import Repository, Storage, StreamingVideoView

@Storage
@Repository(Frame)
class Webcam:

    def open_stream(self) -> None: ...
    def close_stream(self) -> None: ...
    def stream(self) -> Iterator[Frame]: ...

    def data_view(self) -> StreamingVideoView:
        return StreamingVideoView(field="data")
```

`Webcam` is stream-only — no `all()`/`save()`. Its `data_view()` names which
of `Frame`'s fields (`data: bytes`) holds each encoded JPEG frame;
`StreamableProtocol` (unchanged, see [Repository](repository.md)) is what
actually drives the background thread that produces them.

### Document — arbitrary JSON, not a stringified cell

```python
from opendataframework import DocumentView, Repository, Storage

@Storage
@Repository(WebhookEvent)
class WebhookEvents:

    def all(self) -> list[WebhookEvent]: ...

    def data_view(self) -> DocumentView:
        return DocumentView(field="payload")
```

Given `WebhookEvent(id, received_at, payload: dict)`, this names `payload`
as the field worth rendering as a collapsible JSON tree — instead of a
consumer stringifying an arbitrary nested `dict` into an unreadable table
cell.

---

## Replay — scrubbing over time

A repository may separately implement `replay_field()` to say that its
records can be scrubbed through over time, by naming which timestamp field
drives that. This is independent of `data_view()` — a `LocationView`,
`VideoView`, or `AudioView` repository describes *what* representation fits
its data; `replay_field()` separately says *whether* (and by which field)
that representation can be replayed chronologically.

```python
from opendataframework import LocationView, Repository, Storage

@Storage
@Repository(Ping)
class Pings:

    def all(self) -> list[Ping]: ...

    def data_view(self) -> LocationView:
        return LocationView(fields=("lat", "lon"))

    def replay_field(self) -> str:
        return "recorded_at"
```

`Pings` declares both: `LocationView` fixes its representation as a map,
and `replay_field()` says the map can be scrubbed through time using
`recorded_at`. A consumer like `odf`'s UI turns this into a timeline
scrubber alongside the map.

`replay_field()` is detected structurally via `ReplayProtocol`
(`opendataframework.view.ReplayProtocol`, `@runtime_checkable`) — no base
class or decorator required, mirroring `DataViewProtocol`:

```python
class ReplayProtocol(Protocol):
    def replay_field(self) -> str: ...
```

A `TimeseriesView` repository is always replayable already — it names its
own timestamp field via `field` — so `replay_field()` only adds an
affordance for `LocationView`/`VideoView`/`AudioView`-backed repositories. A
repository with no `replay_field()` simply gets no replay affordance.

---

## What a `data_view()` is not

* **Not UI code.** `opendataframework` has zero third-party dependencies and
  renders nothing — `data_view()` is metadata a repository declares about
  itself, consumed by whatever renders it (today, the sibling `odf`
  package's UI). Nothing here imports or knows about `odf`.

* **Not a data-access capability.** It never gates whether `all()`/`save()`/
  `delete()`/`stream()` may be called — `ReadableProtocol`/`WritableProtocol`/
  `StreamableProtocol` still do that, completely independent of what
  `data_view()` returns.

* **Not composable.** A repository returns exactly one `DataView`. If a
  repository's data genuinely needs two different presentations, that's a
  sign it should be two repositories.

* **Not required.** Most repositories need no `data_view()` at all — the
  implicit table default, unchanged from before this protocol existed,
  covers the common case.
