"""A repository's optional single data-representation declaration.

Independent of ``ReadableProtocol``/``WritableProtocol``/``StreamableProtocol``
(``opendataframework.repository``) — those still gate whether the underlying operation
(``all()``/``save()``/``delete()``/``stream()``) is actually allowed.
``DataViewProtocol`` answers a narrower question: given a repository that
already exposes data somehow, what's the single best representation of one
of its records, and which field(s) does that representation hinge on? A
repository picks exactly one — there is no mixing of views. This package
renders nothing itself; the declaration is metadata, consumed by whatever's
on the other end (e.g. the sibling ``odf`` package's UI).

Every variant points at its field(s) generically (``field``/``fields``),
never with a domain-specific attribute name — the meaning comes from which
``View`` subclass it is, not from the attribute name. A variant may also
name a field by its role in the representation (``TimeseriesView.group``),
never by what it means in the domain (``run_id``).

A view says nothing about the content itself, though. A repository whose
view points at content (``ImageView``/``VideoView``/``AudioView``/
``DocumentView``) may separately implement ``ContentMetadataProtocol`` to
declare, per record, what that content is called and which format it's in.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TableView:
    """Rows and columns. The implicit default for a ``ReadableProtocol``
    repository with a dataclass entity — a repository only needs to return
    this explicitly to override which columns show.

    Attributes:
        fields: The columns to show, in order. ``None`` means every entity
            field, in declaration order.
    """

    fields: tuple[str, ...] | None = None


@dataclass
class ImageView:
    """A single still image per record.

    Attributes:
        field: The entity's ``bytes`` field holding the encoded image.
    """

    field: str


@dataclass
class VideoView:
    """A bounded, seekable video clip per record — the repository is
    ``ReadableProtocol``, not a live feed.

    Attributes:
        field: The entity's ``bytes`` field holding the encoded clip.
    """

    field: str


@dataclass
class StreamingVideoView:
    """A live video feed — the repository is ``StreamableProtocol``.

    Attributes:
        field: The streamed entity's ``bytes`` field holding each frame.
    """

    field: str


@dataclass
class AudioView:
    """A bounded, seekable audio clip per record — the repository is
    ``ReadableProtocol``, not a live feed.

    Attributes:
        field: The entity's ``bytes`` field holding the encoded clip.
    """

    field: str


@dataclass
class StreamingAudioView:
    """A live audio feed — the repository is ``StreamableProtocol``.

    Attributes:
        field: The streamed entity's ``bytes`` field holding each chunk.
            Each chunk must be a complete, independently decodable clip
            (e.g. a whole WAV file), not a raw fragment — unlike
            ``StreamingVideoView``'s MJPEG multipart stream, browsers have
            no multipart delivery support for ``<audio>``, so a consumer
            (e.g. the UI) must serve one chunk per request and chain
            playback client-side instead of holding one multiplexed
            connection open.
    """

    field: str


@dataclass
class DocumentView:
    """An arbitrary JSON-shaped value per record, rendered as a collapsible
    tree instead of a stringified table cell.

    Attributes:
        field: The entity's field holding the JSON-shaped value (e.g. a
            ``dict``).
    """

    field: str


@dataclass
class LocationView:
    """Records plotted on a map, one marker per record, popup showing the
    record's fields — replaces the table entirely.

    Attributes:
        fields: ``(lat_field, lon_field)``, by position.
    """

    fields: tuple[str, str]


@dataclass
class TimeseriesView:
    """A line chart — the entity's numeric fields plotted against an
    ordering field, optionally one line per group.

    Attributes:
        field: The entity's ordering field, plotted as the x axis — a
            timestamp, or any field records are ordered by (e.g. a
            training ``step``).
        fields: The numeric fields to plot, in order. ``None`` means every
            numeric entity field other than ``field`` and ``group``.
        group: A field whose distinct values each get their own line (e.g.
            ``run_id``), so groups can be compared on one chart. ``None``
            means all records form a single line.
    """

    field: str
    fields: tuple[str, ...] | None = None
    group: str | None = None


DataView = (
    TableView
    | ImageView
    | VideoView
    | StreamingVideoView
    | AudioView
    | StreamingAudioView
    | DocumentView
    | LocationView
    | TimeseriesView
)


@dataclass
class ContentMetadata:
    """What one record's content is called and which format it's in.

    A declaration, not a guarantee — nothing here inspects the content, so
    a consumer should treat these as hints: check them against the content
    where it can, rely on them where it can't, and never let them override
    its own rules for what is safe to render.

    Attributes:
        filename: The content's file name, extension included (e.g.
            ``"report.pdf"``). ``None`` means not declared.
        content_type: The content's MIME type (e.g. ``"image/png"``).
            ``None`` means not declared.
    """

    filename: str | None = None
    content_type: str | None = None


@runtime_checkable
class DataViewProtocol(Protocol):
    """Capability interface for a repository's optional data-representation declaration.

    Detected structurally via ``isinstance(instance, DataViewProtocol)`` and
    called on demand by whatever's inspecting the repository, mirroring
    ``ChartProtocol``/``DetailsProtocol`` (``opendataframework.component``). A
    repository with no ``data_view()`` falls back to the implicit default: a
    ``TableView`` if it's ``ReadableProtocol`` with a dataclass entity, no
    view otherwise — unchanged from before this protocol existed. (Today,
    that's the sibling ``odf`` package's UI.)
    """

    def data_view(self) -> DataView:
        """Return the single ``DataView`` best representing this repository's records."""
        ...


@runtime_checkable
class ReplayProtocol(Protocol):
    """Capability interface for a repository's optional replay-over-time field.

    Independent of ``DataViewProtocol`` — a repository's ``LocationView``/
    ``VideoView``/``AudioView`` declares which representation fits it;
    ``ReplayProtocol`` separately declares whether (and by which timestamp
    field) its records can be scrubbed through over time. Detected
    structurally via ``isinstance(instance, ReplayProtocol)`` and called on
    demand by whatever's inspecting the repository, mirroring
    ``ChartProtocol``/``DetailsProtocol`` (``opendataframework.component``) and
    ``DataViewProtocol`` above. (Today, the sibling ``odf`` package's UI is
    what offers a timeline scrubber for this.) A repository with no
    ``field()`` gets no such affordance — this only matters for
    ``LocationView``/``VideoView``/``AudioView``-backed repositories; a
    ``TimeseriesView`` repository is always replayable since it already
    names its own ordering field via ``field``.
    """

    def field(self) -> str:
        """Return the entity's timestamp field records can be scrubbed through over time by."""
        ...


@runtime_checkable
class ContentMetadataProtocol(Protocol):
    """Capability interface for a repository's optional per-record content metadata.

    ``DataViewProtocol`` answers, once per repository, which representation
    fits its records and which field holds the content.
    ``ContentMetadataProtocol`` answers a per-record question about that
    same content: what is it called, and which format is it in? It only
    matters for a repository whose view points at content — ``ImageView``/
    ``VideoView``/``AudioView``/``DocumentView``.

    The metadata needn't live on the entity: a repository may take it from
    entity fields, derive it from the record's key, or return a constant
    for content that's always the same format. Detected structurally via
    ``isinstance(instance, ContentMetadataProtocol)`` and called on demand
    by whatever's inspecting the repository, mirroring ``DataViewProtocol``/
    ``ReplayProtocol`` above. (Today, the sibling ``odf`` package's UI is
    what would label, type and offer the content for download with this.)
    A repository with no ``content_metadata()`` declares nothing — a
    consumer is left to work the content out for itself, unchanged from
    before this protocol existed.
    """

    def content_metadata(self, entity: object) -> ContentMetadata:
        """Return the ``ContentMetadata`` describing the given record's content."""
        ...
