"""Per-component structured logging.

``LogManager`` owns one log file per ``<namespace>.<name>`` key (see
``opendataframework.namespace.qualified``), scoped to a single
``Context`` — no process-global state, so multiple ``Project`` instances in
the same process never share log files or file handles (see
``docs/context.md`` / ``CLAUDE.md``'s "no global mutable state" constraint).

Each line is a record. By default a file is JSON Lines, ``<key>.jsonl``,
one JSON object per line::

    {"ts": "2026-10-31T10:00:00.123+01:00", "level": "INFO",
     "key": "task.load", "namespace": "task", "name": "load", "source": null,
     "message": "order taken", "fields": {"order_id": 7}}

With ``[project.logging] format = "text"`` it is ``<key>.log`` instead, each
record turned into a readable line by ``render``.

Three ways records get written:

* Automatically, by ``Events`` — every protocol call the framework makes
  (``setup``/``run``/``stop``, ``execute()``, a ``@Function`` call, ...) is
  logged when it starts and when it completes or fails, with its call id and
  its parent's, so a call can be traced across files.
* Automatically, by ``Notifications`` — every publish is logged on the
  publisher's key.
* Explicitly, by component code that declares ``logger: Logger`` in its
  constructor. ``Resolver`` special-cases this type: each consumer receives
  a ``Logger`` already bound to its own key, so ``self.logger.info(x)``
  needs no name argument and still lands in that component's own file.

Which records are kept is set by level thresholds — ``[project.logging]`` in
the project config; see ``LogManager``.

Every notification record is also written to ``history/notifications.jsonl``,
a file that holds nothing else, each line with a ``seq`` number, so the
notification history can be read back newest first without scanning every
component's log — see ``LogManager.notification_history``.
"""

import json
import os
import re
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from opendataframework.utils import kebab

# The ``call_id`` of the protocol call in progress in this thread (or task).
# A ``ContextVar`` holds a separate value per thread, so it is not shared state.
# It lives here, not in ``events``, because ``LogManager.write()`` reads it
# and ``events`` already imports this module.
_current_call: ContextVar[str | None] = ContextVar("opendataframework_call", default=None)


def _current_call_id() -> str | None:
    """Return the ``call_id`` of the protocol call in progress in this thread, if any.

    Set by ``Events.notify()``. Read by ``LogManager.write()``, which records
    it as a record's ``parent``, and by ``opendataframework.notifications``,
    which records it as a notification's.
    """
    return _current_call.get()


# The ``id`` of the notification whose listener is running in this thread, if
# any. A top-level protocol call that starts while it is set records it as its
# ``cause`` — see ``Events.notify()``.
_current_cause: ContextVar[str | None] = ContextVar("opendataframework_cause", default=None)


@contextmanager
def _no_current_call(cause: str | None = None) -> Iterator[None]:
    """Run the block with no current call, so a call made inside it is top-level.

    Used while listeners run — ``Events``' and ``Notifications``' alike — so a
    call a listener makes is not a child of the call that triggered it.

    Args:
        cause: The id of the notification being delivered, so a call the
            listener makes records it as its ``cause``. ``None`` (for an
            ``Events`` listener) clears any cause in effect, so one never
            leaks from a notification's listener into an event's.
    """
    call_token = _current_call.set(None)
    cause_token = _current_cause.set(cause)
    try:
        yield
    finally:
        _current_cause.reset(cause_token)
        _current_call.reset(call_token)


_LINE_RE = re.compile(r"^(\S+ \S+) (\S+)\s+(.*)$")
_ESCAPED_RE = re.compile(r"\\(\\|n)")

LEVELS: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
"""Level names, in increasing severity."""

SOURCES = ("events", "notifications")
"""Framework sources a record can come from, each settable on its own."""

FORMATS = {"json": ".jsonl", "text": ".log"}
"""Log file formats, and the file extension each is written with."""

_DEFAULT_LEVEL = "INFO"
_DEFAULT_BACKUPS = 5
_ROTATION_KEYS = ("max-bytes", "backups", "history-max-bytes", "history-backups")
# The notification history's key in ``_files`` and ``_sizes``. No component key
# can be this: ``check_key()`` rejects a ``/``.
_HISTORY = "history/notifications"
# A file name is at most 255 bytes on common filesystems; a log file's adds
# ``.jsonl`` and a backup's ``.<n>`` to the key.
_MAX_KEY_BYTES = 200
# A filesystem that keeps modification times to the second can report a file's
# ``st_mtime`` up to a second earlier than the ``ts`` of its last record. So a
# backup is skipped as older than ``since`` only when it is older by more than
# this, or a record inside that second would be dropped. Don't remove it as
# unneeded. (2-second filesystems like FAT aren't covered, and aren't where
# logs live.)
_MTIME_SLACK = 1.0
_MAX_HISTORY_LIMIT = 1000
_CURSOR_RE = re.compile(r"^[1-9][0-9]*$")
# How much tail() reads from the end of a file at a time.
_BLOCK_SIZE = 64 * 1024
# The stem of a rotated backup: ``<namespace>.<name>.<n>``.
_BACKUP_RE = re.compile(r"^(?P<base>.+)\.(?P<n>\d+)$")


class LogsUnavailable(ValueError):  # noqa: N818 — it names a state, not a failure
    """Log records can't be read back here: file logging is off, or the format doesn't allow it.

    A ``ValueError``, so callers that catch ``ValueError`` keep working. A bad
    argument stays a plain ``ValueError``, so a caller can tell "this can't be
    read here" from "you asked wrongly".
    """


def check_key(key: object) -> str:
    """Return ``key`` if it is safe as a log file's name.

    Raises:
        ValueError: If ``key`` is not a string, is empty, contains ``/`` or
            ``\\``, starts with ``.``, or its file name would be longer than
            200 bytes in UTF-8.
    """
    if not isinstance(key, str) or not key:
        raise ValueError(f"invalid key {key!r}: must be a non-empty string")
    if "/" in key or "\\" in key:
        raise ValueError(f"invalid key {key!r}: must not contain '/' or '\\'")
    if key.startswith("."):
        raise ValueError(f"invalid key {key!r}: must not start with '.'")
    if len(kebab(key).encode()) > _MAX_KEY_BYTES:
        raise ValueError(
            f"invalid key {key[:40]!r}...: its log file name would pass {_MAX_KEY_BYTES} bytes"
        )
    return key


class LogManager:
    """Owns per-component log files for a single ``Context``.

    When ``log_dir`` is ``None`` (the default), logging is a no-op — writes
    are dropped and ``tail()`` returns an empty list. This keeps the
    framework's default (and its test suite) free of stray files, while
    ``Project.from_config``/``from_dict`` opt in to a real ``log_dir``.

    ``config`` mirrors ``[project.logging]``::

        format = "json"           # "json" (the default) or "text"
        level = "INFO"            # default for every record
        events = "WARNING"        # records Events writes
        notifications = "INFO"    # records Notifications writes

        max-bytes = 10_000_000    # rotate a file before it grows past this; off by default
        backups = 5               # rotated files kept per component
        history-max-bytes = 20_000_000  # the notification history; defaults to max-bytes
        history-backups = 5             # defaults to backups

        [task]                    # a namespace
        level = "INFO"            # every task, every source
        take-orders = "DEBUG"     # one component, every source

    A record is written only if its level is at or above the threshold for
    its component and source. The most specific setting wins:
    ``task.take-orders``, then ``task.level``, then the record's source
    (``events``/``notifications``), then ``level``, then ``INFO``. Level
    names are ``DEBUG``, ``INFO``, ``WARNING`` and ``ERROR``, in any casing.

    With ``max-bytes`` set, a file that a record would grow past it is
    rotated first: ``<key>.jsonl`` becomes ``<key>.1.jsonl``, older backups
    shift up to ``<key>.<backups>.jsonl``, and the oldest beyond that is
    deleted (``.log`` likewise, in the text format). Rotation is safe within
    one process only: two processes writing the same log directory must not
    both rotate. Reading the notification history back while it rotates is
    POSIX-only: on Windows, a rotation fails while a reader has the file open.

    Every notification record is also written to
    ``history/notifications.jsonl``, rotated by ``history-max-bytes`` and
    ``history-backups``, which default to ``max-bytes`` and ``backups``. So
    rotation is off for it too unless one of the two ``max-bytes`` is set,
    and ``history-max-bytes`` alone rotates only the history. It is always
    JSON Lines, whatever the format, and written only when the record passes
    its component's threshold.

    Args:
        log_dir: Directory to write ``<namespace>.<name>.jsonl`` (or
            ``.log``) files under, or ``None`` to disable file logging
            entirely.
        config: Format and level thresholds, as above. ``None`` writes JSON
            Lines and keeps ``INFO`` and up.

    Raises:
        ValueError: If ``config`` has an unknown format or level name, a
            ``max-bytes``, ``backups``, ``history-max-bytes`` or
            ``history-backups`` that isn't a positive integer, or a
            value that is neither a level name nor, for a namespace, a table
            of them.
    """

    def __init__(
        self, log_dir: str | Path | None = None, config: Mapping[str, object] | None = None
    ) -> None:
        """Set the log directory (or ``None`` to disable file logging), format and thresholds."""
        self._dir = Path(log_dir) if log_dir is not None else None
        self._lock = threading.Lock()
        self._files: dict[str, object] = {}
        self._sizes: dict[str, int] = {}
        self._format = "json"
        self._default = LEVELS[_DEFAULT_LEVEL]
        self._sources: dict[str, int] = {}
        self._namespaces: dict[str, dict[str, int]] = {}
        self._max_bytes: int | None = None
        self._backups = _DEFAULT_BACKUPS
        self._history_max_bytes_set: int | None = None
        self._history_backups_set: int | None = None
        # The last ``seq`` written to the history, once recovered (``_ensure_seq``).
        self._seq: int | None = None
        # Whether the history's current file ends in a fragment, with no "\n".
        self._history_torn = False
        for key, value in (config or {}).items():
            if key == "format":
                self._format = _format(value)
            elif key == "max-bytes":
                self._max_bytes = _positive(value, key)
            elif key == "backups":
                self._backups = _positive(value, key)
            elif key == "history-max-bytes":
                self._history_max_bytes_set = _positive(value, key)
            elif key == "history-backups":
                self._history_backups_set = _positive(value, key)
            elif key == "level":
                self._default = _level(value, key)
            elif key in SOURCES:
                self._sources[key] = _level(value, key)
            elif isinstance(value, Mapping):
                self._namespaces[key] = {
                    name: _level(level, f"{key}.{name}") for name, level in value.items()
                }
            else:
                raise ValueError(
                    f"[project.logging] {key} = {value!r}: a namespace takes a table — "
                    f"write {key}.level = {value!r} to set every {key}"
                )

    def threshold(self, component: str, source: str | None = None) -> int:
        """Return the lowest level written for ``component``'s records from ``source``.

        Args:
            component: A ``<namespace>.<name>`` key.
            source: ``"events"``, ``"notifications"``, or ``None`` for any
                other record (a ``Logger`` call, a resolution line, ...).
        """
        namespace, _, name = component.partition(".")
        table = self._namespaces.get(namespace, {})
        if name in table:
            return table[name]
        if "level" in table:
            return table["level"]
        if source in self._sources:
            return self._sources[source]
        return self._default

    def validate(self, namespaces: Iterable[str], keys: Iterable[str]) -> None:
        """Check every namespace and component the config names exists.

        Called by ``Context.open()`` once it has resolved, so a typo fails
        loudly instead of silently setting nothing.

        Args:
            namespaces: The Context's namespace names, as keys start with.
            keys: Every resolved ``<namespace>.<name>`` key.

        Raises:
            ValueError: If the config names a namespace or component that
                does not exist.
        """
        namespaces = set(namespaces)
        names: dict[str, set[str]] = {}
        for key in keys:
            namespace, _, name = key.partition(".")
            names.setdefault(namespace, set()).add(name)
        for namespace, table in self._namespaces.items():
            if namespace not in namespaces:
                valid = ", ".join(
                    ["format", "level", *SOURCES, *_ROTATION_KEYS, *sorted(namespaces)]
                )
                raise ValueError(
                    f"[project.logging] has unknown key {namespace!r}; expected one of: {valid}"
                )
            for name in table:
                if name != "level" and name not in names.get(namespace, set()):
                    valid = ", ".join(["level", *sorted(names.get(namespace, set()))])
                    raise ValueError(
                        f"[project.logging.{namespace}] has unknown key {name!r}; "
                        f"expected one of: {valid}"
                    )

    def write(
        self,
        component: str,
        level: str,
        message: str,
        *,
        source: str | None = None,
        extra: Mapping[str, object] | None = None,
        fields: Mapping[str, object] | None = None,
    ) -> None:
        """Append one record for ``component``, if ``level`` passes its threshold.

        No-op if logging is disabled. While a protocol call is in progress,
        a record whose ``extra`` doesn't name a ``parent`` gets the call's id
        as its ``parent`` — so a ``logger.info()`` inside ``execute()`` says
        which call wrote it. Records written outside any call get none.

        Args:
            component: The ``<namespace>.<name>`` key the record is about.
            level: ``"DEBUG"``, ``"INFO"``, ``"WARNING"`` or ``"ERROR"``.
            message: Human-readable text.
            source: ``"events"`` or ``"notifications"`` for the records those
                write, ``None`` otherwise.
            extra: Framework fields, written at the top level of the record —
                an event's ``call``/``parent``/..., a notification's
                ``topic``/....
            fields: User fields, written nested under ``"fields"``; omitted
                when empty.
        """
        if self._dir is None or LEVELS[level] < self.threshold(component, source):
            return
        record = self._record(component, level, message, source, extra, fields, _now())
        line = self._serialise(record)
        with self._lock:
            self._append_component(component, line)

    def write_notification(
        self, component: str, level: str, message: str, extra: Mapping[str, object]
    ) -> None:
        """Append a notification's record for ``component``, and to the history, if it passes.

        Like ``write(..., source="notifications")``, and the same record is
        also appended to ``history/notifications.jsonl`` with the next
        ``seq``. Both lines carry one ``ts``, taken with ``seq`` under the lock
        that orders the writes, so the history is in ``seq`` order and its
        ``ts`` follows, barring wall-clock steps. The history line is JSON
        whatever the format. No-op if logging is disabled, or the record is
        below ``component``'s threshold for ``notifications`` — then neither
        line is written.

        Args:
            component: The publisher's key.
            level: The log level, ``"INFO"``, ``"WARNING"``, ...
            message: Human-readable text.
            extra: The notification's fields: ``notification``, ``topic``,
                ``summary``, ...
        """
        source = "notifications"
        if self._dir is None or LEVELS[level] < self.threshold(component, source):
            return
        with self._lock:
            ts = _now()
            seq = self._ensure_seq() + 1
            record = self._record(component, level, message, source, extra, None, ts)
            line = self._serialise(record)
            history = json.dumps({**record, "seq": seq}, default=str, ensure_ascii=False)
            self._append_component(component, line)
            if self._history_torn:
                # After a crash mid-write: end the fragment, or this record
                # would be glued onto it and the reader would lose both.
                f = self._files.get(_HISTORY) or self._open(self._history_path, _HISTORY)
                f.write("\n")
                self._sizes[_HISTORY] += 1
                self._history_torn = False
            self._append(
                _HISTORY,
                self._history_path,
                history,
                self._history_max_bytes,
                self._history_backups,
            )
            self._seq = seq

    def tail(self, component: str, lines: int = 300) -> list[dict]:
        """Return the last ``lines`` records for ``component``, oldest first.

        Returns:
            Record dicts, each with at least ``"ts"``, ``"level"`` and
            ``"message"``. In the ``json`` format they are the full records
            (``key``, ``source``, ``call``, ``fields``, ...); in the ``text``
            format only those three, parsed back from each line. A line that
            can't be parsed comes back as ``{"ts": None, "level": "INFO",
            "message": <the raw line>}``. Empty if logging is disabled or
            nothing was ever written for this component.

        Reads backwards from the end of the current file, and into its
        rotated backups only if it needs more lines, so its cost follows
        ``lines``, not the file's size.
        """
        if self._dir is None or lines <= 0:
            return []
        raw: list[str] = []
        with self._lock:
            # Newest first: the current file, then .1, .2, ... only while short.
            for n in range(self._backups + 1):
                path = self._path(component, n)
                if not path.exists():
                    if n == 0:
                        continue
                    break
                raw = _last_lines(path, lines - len(raw)) + raw
                if len(raw) >= lines:
                    break
        parse = _parse_json if self._format == "json" else _parse_line
        return [parse(line) for line in raw]

    def records(self, since: float | datetime | None = None) -> Iterator[dict]:
        """Yield every record in every ``.jsonl`` file, component by component, oldest first.

        Used by ``Context.trace()`` to follow a call across files. A
        component's rotated backups come first, oldest first, then its
        current file. Only the configured ``json`` format is read: ``.log``
        files left from an earlier ``text`` setup are ignored. Lines that
        can't be parsed are skipped.

        Args:
            since: Skip files last written before this time — a
                ``time.time()`` value or a ``datetime``. A trace of a call
                that started at ``since`` needs nothing older. ``None`` (the
                default) reads every file.

        The notification history (``history/``) is never read here: it holds
        only copies of notification records already in these files.

        Raises:
            LogsUnavailable: If file logging is off, or the configured format
                is ``text``, whose lines keep only ``ts``, ``level`` and
                ``message``. A ``ValueError``.
        """
        if self._dir is None:
            raise LogsUnavailable("file logging is off: pass log_dir to read records back")
        if self._format != "json":
            raise LogsUnavailable(
                'records need the "json" log format; [project.logging] sets "text"'
            )
        if not self._dir.exists():
            return
        cutoff = since.timestamp() if isinstance(since, datetime) else since
        for path in self._files_oldest_first():
            if cutoff is not None and path.stat().st_mtime < cutoff:
                continue
            with self._lock:
                raw = path.read_text(encoding="utf-8").splitlines()
            for line in raw:
                record = _parse_json(line)
                if record.get("ts") is not None:
                    yield record

    def for_call(self, call_id: str) -> list[dict]:
        """Return every record written by or during one protocol call, across files.

        That is the call's own event records (``call`` equal to
        ``call_id``) and every record written while it was the current call
        (``parent`` equal to ``call_id``): its log lines, the notifications
        it published, and the start and end of the calls made directly
        inside it. Records are grouped file by file, oldest first in each.

        Raises:
            LogsUnavailable: As ``records()`` does.
        """
        return [
            record
            for record in self.records()
            if record.get("call") == call_id or record.get("parent") == call_id
        ]

    def notification_history(
        self,
        match: Callable[[Mapping[str, object]], bool] | None = None,
        *,
        before: str | float | datetime | None = None,
        since: float | datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return the latest notification records ``match`` accepts, newest first.

        Reads ``history/notifications.jsonl`` and its backups backwards, so
        its cost follows the number of notifications read, never the size of
        the component logs. Safe while notifications are published: a record
        is accepted only if its ``seq`` is below every one read before it and
        at most the last written when the read began, so a rotation
        mid-read, a record written during it, or a line still being written
        never shows.

        Args:
            match: Called with each raw history record (``topic``, ``key``,
                ``notification_level``, ``summary``, ...); ``None`` accepts
                all.
            before: A row's ``cursor``: only rows strictly older than it. Or
                a ``time.time()`` value or ``datetime``: only rows whose
                ``ts`` is strictly earlier.
            since: No row older than this time; the read stops there.
            limit: At most this many rows, 1 to 1000.

        Returns:
            JSON-ready dicts with ``id``, ``key``, ``topic``, ``level`` (the
            notification's level), ``summary``, ``message``, ``subject``,
            ``record``, ``parent``, ``ts`` (ISO 8601) and ``cursor``.

        Raises:
            ValueError: If ``before``, ``since`` or ``limit`` is invalid.
            LogsUnavailable: If file logging is off.
        """
        before_seq, before_ts = _before(before)
        since_ts = _time(since, "since") if since is not None else None
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"invalid limit {limit!r}: expected an integer")
        if not 1 <= limit <= _MAX_HISTORY_LIMIT:
            raise ValueError(f"invalid limit {limit}: must be 1 to {_MAX_HISTORY_LIMIT}")
        if self._dir is None:
            raise LogsUnavailable("file logging is off: pass log_dir to read the history back")
        with self._lock:
            last = self._ensure_seq()
        rows: list[dict] = []
        # Records are accepted only below this: the last seq read, or, until
        # one has been, one past the last written when the read began.
        upper = last + 1
        for n in range(self._history_backups + 1):
            path = self._history_path(n)
            if n and since_ts is not None:
                try:
                    if path.stat().st_mtime < since_ts - _MTIME_SLACK:
                        break  # this backup and every older one predate since
                except FileNotFoundError:
                    continue
            try:
                f = open(path, "rb")
            except FileNotFoundError:
                continue  # never written, or rotation dropped it during the read
            with f:
                first = _seq_of(f.readline())
                if first is not None and first >= min(upper, before_seq or upper):
                    continue  # nothing new in it: newer than the cursor, or already read
                for line in _lines_backwards(f):
                    record = _parse_history(line)
                    if record is None or record["seq"] >= upper:
                        continue
                    upper = record["seq"]
                    if before_seq is not None and record["seq"] >= before_seq:
                        continue
                    if since_ts is not None or before_ts is not None:
                        ts = _timestamp(record.get("ts"))
                        if ts is None:
                            continue
                        if since_ts is not None and ts < since_ts:
                            return rows
                        if before_ts is not None and ts >= before_ts:
                            continue
                    if match is None or match(record):
                        rows.append(_history_row(record))
                        if len(rows) >= limit:
                            return rows
        return rows

    def logger_for(self, component: str) -> Logger:
        """Return a ``Logger`` bound to ``component``'s own log file."""
        return Logger(self, component)

    def close(self) -> None:
        """Close every open file handle. Safe to call even if none were opened."""
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()

    @property
    def _history_max_bytes(self) -> int | None:
        """The history's ``max-bytes``: ``history-max-bytes``, else ``max-bytes``."""
        if self._history_max_bytes_set is not None:
            return self._history_max_bytes_set
        return self._max_bytes

    @property
    def _history_backups(self) -> int:
        """The history's ``backups``: ``history-backups``, else ``backups``."""
        if self._history_backups_set is not None:
            return self._history_backups_set
        return self._backups

    def _record(
        self,
        component: str,
        level: str,
        message: str,
        source: str | None,
        extra: Mapping[str, object] | None,
        fields: Mapping[str, object] | None,
        ts: str,
    ) -> dict[str, object]:
        """Build one record — see ``write()``."""
        namespace, _, name = component.partition(".")
        record: dict[str, object] = {
            "ts": ts,
            "level": level,
            "key": component,
            "namespace": namespace,
            "name": name,
            "source": source,
            "message": message,
            **(extra or {}),
        }
        # Key presence, not truthiness: a top-level event sets parent=None on
        # purpose, and its "completed" record is written while its own call
        # is still current.
        if "parent" not in record:
            parent = _current_call.get()
            if parent is not None:
                record["parent"] = parent
        if fields:
            record["fields"] = dict(fields)
        return record

    def _serialise(self, record: Mapping[str, object]) -> str:
        """Return ``record`` as one line of the configured format."""
        if self._format == "json":
            return json.dumps(record, default=str, ensure_ascii=False)
        return render(record)

    def _append_component(self, component: str, line: str) -> None:
        """Append ``line`` to ``component``'s file, rotating it first if needed. Under the lock."""
        self._append(
            kebab(component),
            lambda n: self._path(component, n),
            line,
            self._max_bytes,
            self._backups,
        )

    def _append(
        self,
        file_key: str,
        path_of: Callable[[int], Path],
        line: str,
        max_bytes: int | None,
        backups: int,
    ) -> None:
        """Append ``line`` to the file ``path_of(0)``, rotating it first if needed. Under the lock.

        Args:
            file_key: The file's key in ``_files`` and ``_sizes``.
            path_of: Returns the file's path, or its ``n``-th backup's.
            line: One record, with no trailing newline.
            max_bytes: Rotate before the file grows past this; ``None``
                never rotates.
            backups: Rotated files kept.
        """
        size = len(line.encode()) + 1
        f = self._files.get(file_key)
        if f is None:
            f = self._open(path_of, file_key)
        if (
            max_bytes is not None
            and self._sizes[file_key] > 0
            and self._sizes[file_key] + size > max_bytes
        ):
            f = self._rotate(path_of, file_key, backups)
        f.write(line + "\n")
        self._sizes[file_key] += size

    def _path(self, component: str, backup: int = 0) -> Path:
        """Return ``component``'s log file, or its ``backup``-th rotated one.

        Raises:
            ValueError: If ``component`` isn't safe as a file name — see
                ``check_key()``.
        """
        suffix = f".{backup}" if backup else ""
        return self._dir / f"{kebab(check_key(component))}{suffix}{FORMATS[self._format]}"

    def _history_path(self, backup: int = 0) -> Path:
        """Return the history file, or its ``backup``-th rotated one. Always JSON Lines."""
        suffix = f".{backup}" if backup else ""
        return self._dir / f"{_HISTORY}{suffix}{FORMATS['json']}"

    def _open(self, path_of: Callable[[int], Path], file_key: str) -> object:
        """Open the file ``path_of(0)`` for appending, and note its size. Under the lock."""
        path = path_of(0)
        path.parent.mkdir(parents=True, exist_ok=True)
        f = open(path, "a", buffering=1, encoding="utf-8")
        self._files[file_key] = f
        self._sizes[file_key] = path.stat().st_size
        return f

    def _rotate(self, path_of: Callable[[int], Path], file_key: str, backups: int) -> object:
        """Shift a file up one backup and reopen an empty current one.

        Under the lock. The backup beyond ``backups`` is overwritten, so at
        most ``backups`` are kept.
        """
        self._files.pop(file_key).close()
        for n in range(backups - 1, 0, -1):
            older = path_of(n)
            if older.exists():
                os.replace(older, path_of(n + 1))
        os.replace(path_of(0), path_of(1))
        if file_key == _HISTORY:
            self._history_torn = False  # the fragment, if any, is a backup's end now
        return self._open(path_of, file_key)

    def _ensure_seq(self) -> int:
        """Return the last ``seq`` written to the history, recovering it once. Under the lock.

        Finds the last line that parses — in the current file, or the newest
        backup if the current file is empty or has none — and notes whether
        the current file ends in a fragment, which the next write then ends
        with a newline. With no record at all, the last ``seq`` is 0.
        """
        if self._seq is not None:
            return self._seq
        self._seq = 0
        for n in range(self._history_backups + 1):
            path = self._history_path(n)
            try:
                f = open(path, "rb")
            except FileNotFoundError:
                continue
            with f:
                end = f.seek(0, os.SEEK_END)
                if n == 0 and end:
                    self._history_torn = _read_block(f, end - 1, 1) != b"\n"
                for line in _lines_backwards(f):
                    record = _parse_history(line)
                    if record is not None:
                        self._seq = record["seq"]
                        return self._seq
        return self._seq

    def _files_oldest_first(self) -> list[Path]:
        """Return every ``.jsonl`` file: per component, backups oldest first, then current."""
        ext = FORMATS["json"]
        found: list[tuple[str, int, Path]] = []
        for path in self._dir.glob(f"*{ext}"):
            stem = path.name.removesuffix(ext)
            backup = _BACKUP_RE.match(stem)
            if backup:
                found.append((backup["base"], -int(backup["n"]), path))
            else:
                found.append((stem, 0, path))
        return [path for _, _, path in sorted(found)]


class Logger:
    """Per-component logging handle, injectable via constructor DI.

    Not registered in any ``Namespace`` — ``Resolver`` special-cases a
    ``logger: Logger`` constructor parameter and supplies an instance already
    bound to the requesting class's own key, rather than a single shared
    instance. Declare it like any other dependency::

        @Task
        class ExportUsers:
            def __init__(self, users: Users, logger: Logger) -> None:
                self.users = users
                self.logger = logger

            def execute(self) -> None:
                self.logger.info("export starting", users=len(self.users.all()))
                ...

    Keyword arguments become the record's ``fields``. ``message`` is
    positional-only, so a field may itself be called ``message``.
    """

    def __init__(self, manager: LogManager, component: str) -> None:
        """Bind this logger to ``component``'s log file on ``manager``."""
        self._manager = manager
        self._component = component

    def debug(self, message: str, /, **fields: object) -> None:
        """Log a DEBUG-level message for this component, with optional ``fields``."""
        self._manager.write(self._component, "DEBUG", message, fields=fields)

    def info(self, message: str, /, **fields: object) -> None:
        """Log an INFO-level message for this component, with optional ``fields``."""
        self._manager.write(self._component, "INFO", message, fields=fields)

    def warning(self, message: str, /, **fields: object) -> None:
        """Log a WARNING-level message for this component, with optional ``fields``."""
        self._manager.write(self._component, "WARNING", message, fields=fields)

    def error(self, message: str, /, **fields: object) -> None:
        """Log an ERROR-level message for this component, with optional ``fields``."""
        self._manager.write(self._component, "ERROR", message, fields=fields)


def render(record: Mapping[str, object]) -> str:
    """Return ``record`` as one readable text line, the way the ``text`` format writes it.

    An event's line ends with its ids — ``[call=<id> parent=<id>]``, with
    ``parent=-`` for a top-level call — and a notification's with
    ``[parent=...]``. User fields follow as
    ``name=value`` pairs. A backslash or newline is escaped, so the result
    is always a single line.

    Example:
        >>> render({"ts": "2026-10-31T10:00:00.123+01:00", "level": "INFO",
        ...         "message": "order taken", "fields": {"order_id": 7}})
        '2026-10-31 10:00:00.123 INFO     order taken order_id=7'
    """
    ts = str(record.get("ts") or "-")[:23].replace("T", " ")
    line = f"{ts} {record.get('level', 'INFO'):<8} {record.get('message', '')}"
    if "call" in record:
        line += f" [call={record['call']} parent={record.get('parent') or '-'}]"
    elif "parent" in record:
        line += f" [parent={record['parent'] or '-'}]"
    fields = record.get("fields") or {}
    if fields:
        line += " " + " ".join(f"{name}={value!r}" for name, value in fields.items())
    return line.replace("\\", "\\\\").replace("\n", "\\n")


def _read_block(f, start: int, size: int) -> bytes:
    """Read ``size`` bytes of ``f`` from ``start``."""
    f.seek(start)
    return f.read(size)


def _last_lines(path: Path, count: int) -> list[str]:
    """Return the last ``count`` lines of ``path``, reading backwards in blocks."""
    if count <= 0:
        return []
    with open(path, "rb") as f:
        end = f.seek(0, os.SEEK_END)
        data = b""
        # One newline more than lines wanted proves the first kept line whole.
        while end > 0 and data.count(b"\n") <= count:
            start = max(0, end - _BLOCK_SIZE)
            data = _read_block(f, start, end - start) + data
            end = start
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if end > 0:
        lines = lines[1:]  # partial: it started before what was read
    return [line.decode("utf-8", errors="replace") for line in lines[-count:]]


def _lines_backwards(f) -> Iterator[bytes]:
    """Yield the non-empty lines of the open binary file ``f``, last first, reading in blocks.

    The first one yielded is whatever follows the last newline — a fragment
    still being written, or a last line with no newline — for the caller to
    reject if it doesn't parse.
    """
    end = f.seek(0, os.SEEK_END)
    head = b""  # the start of a line whose beginning hasn't been read yet
    while end > 0:
        start = max(0, end - _BLOCK_SIZE)
        lines = (_read_block(f, start, end - start) + head).split(b"\n")
        end = start
        head = lines[0]
        for line in reversed(lines[1:]):
            if line:
                yield line
    if head:
        yield head


def _parse_history(line: bytes) -> dict | None:
    """Parse one history line, or return ``None`` if it isn't a whole record with a ``seq``."""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    seq = record.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int):
        return None
    return record


def _seq_of(line: bytes) -> int | None:
    """Return the ``seq`` of one history line, or ``None`` if it doesn't parse."""
    record = _parse_history(line.rstrip(b"\n"))
    return record["seq"] if record is not None else None


def _history_row(record: Mapping[str, object]) -> dict:
    """Return the JSON-ready row ``notification_history()`` gives for a history record."""
    return {
        "id": record.get("notification"),
        "key": record.get("key"),
        "topic": record.get("topic"),
        "level": record.get("notification_level"),
        "summary": record.get("summary"),
        "message": record.get("message"),
        "subject": record.get("subject"),
        "record": record.get("record"),
        "parent": record.get("parent"),
        "ts": record.get("ts"),
        "cursor": str(record["seq"]),
    }


def _before(before: object) -> tuple[int | None, float | None]:
    """Return ``(cursor seq, time)`` from ``notification_history``'s ``before``; one is ``None``.

    Raises:
        ValueError: If ``before`` is a string that isn't a cursor, or neither
            a string nor a time.
    """
    if before is None:
        return None, None
    if isinstance(before, str):
        if not _CURSOR_RE.match(before):
            raise ValueError(f"invalid cursor {before!r}: pass a row's cursor as it was returned")
        return int(before), None
    return None, _time(before, "before")


def _time(value: object, name: str) -> float:
    """Return ``value`` — a ``time.time()`` value or a ``datetime`` — as epoch seconds.

    Raises:
        ValueError: If ``value`` is neither.
    """
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"invalid {name} {value!r}: expected a time.time() value or a datetime")
    return float(value)


def _timestamp(ts: object) -> float | None:
    """Return a record's ISO 8601 ``ts`` as epoch seconds, or ``None`` if it isn't one."""
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except ValueError:
        return None


def _now() -> str:
    """Return the current local time as a record's ``ts``."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _parse_json(line: str) -> dict:
    """Parse one ``json``-format log line back into its record."""
    try:
        record = json.loads(line)
    except ValueError:
        record = None
    if not isinstance(record, dict):
        return {"ts": None, "level": "INFO", "message": line}
    return record


def _parse_line(line: str) -> dict:
    """Parse one ``text``-format log line into ``{"ts", "level", "message"}``."""
    m = _LINE_RE.match(line)
    if not m:
        return {"ts": None, "level": "INFO", "message": _unescape(line)}
    ts, level, message = m.groups()
    return {"ts": ts, "level": level, "message": _unescape(message)}


def _unescape(text: str) -> str:
    """Undo ``render``'s escaping of backslashes and newlines."""
    return _ESCAPED_RE.sub(lambda m: "\n" if m[1] == "n" else "\\", text)


def _level(value: object, key: str) -> int:
    """Return the numeric level ``value`` names, for the ``[project.logging]`` entry ``key``."""
    name = value.upper() if isinstance(value, str) else None
    if name not in LEVELS:
        raise ValueError(
            f"[project.logging] {key} = {value!r}: expected one of {', '.join(LEVELS)}"
        )
    return LEVELS[name]


def _positive(value: object, key: str) -> int:
    """Return ``value`` if it is a positive integer, for the ``[project.logging]`` entry ``key``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"[project.logging] {key} = {value!r}: expected a positive integer")
    return value


def _format(value: object) -> str:
    """Return the log format ``value`` names, for ``[project.logging] format``."""
    name = value.lower() if isinstance(value, str) else None
    if name not in FORMATS:
        raise ValueError(
            f"[project.logging] format = {value!r}: expected one of {', '.join(FORMATS)}"
        )
    return name
