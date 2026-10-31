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
"""

import json
import re
import threading
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path

from opendataframework.utils import kebab

_LINE_RE = re.compile(r"^(\S+ \S+) (\S+)\s+(.*)$")
_ESCAPED_RE = re.compile(r"\\(\\|n)")

LEVELS: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
"""Level names, in increasing severity."""

SOURCES = ("events", "notifications")
"""Framework sources a record can come from, each settable on its own."""

FORMATS = {"json": ".jsonl", "text": ".log"}
"""Log file formats, and the file extension each is written with."""

_DEFAULT_LEVEL = "INFO"


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

        [task]                    # a namespace
        level = "INFO"            # every task, every source
        take-orders = "DEBUG"     # one component, every source

    A record is written only if its level is at or above the threshold for
    its component and source. The most specific setting wins:
    ``task.take-orders``, then ``task.level``, then the record's source
    (``events``/``notifications``), then ``level``, then ``INFO``. Level
    names are ``DEBUG``, ``INFO``, ``WARNING`` and ``ERROR``, in any casing.

    Args:
        log_dir: Directory to write ``<namespace>.<name>.jsonl`` (or
            ``.log``) files under, or ``None`` to disable file logging
            entirely.
        config: Format and level thresholds, as above. ``None`` writes JSON
            Lines and keeps ``INFO`` and up.

    Raises:
        ValueError: If ``config`` has an unknown format or level name, or a
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
        self._format = "json"
        self._default = LEVELS[_DEFAULT_LEVEL]
        self._sources: dict[str, int] = {}
        self._namespaces: dict[str, dict[str, int]] = {}
        for key, value in (config or {}).items():
            if key == "format":
                self._format = _format(value)
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
                valid = ", ".join(["format", "level", *SOURCES, *sorted(namespaces)])
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

        No-op if logging is disabled.

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
        namespace, _, name = component.partition(".")
        record: dict[str, object] = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "level": level,
            "key": component,
            "namespace": namespace,
            "name": name,
            "source": source,
            "message": message,
            **(extra or {}),
        }
        if fields:
            record["fields"] = dict(fields)
        if self._format == "json":
            line = json.dumps(record, default=str, ensure_ascii=False)
        else:
            line = render(record)
        file_name = kebab(component)
        with self._lock:
            f = self._files.get(file_name)
            if f is None:
                self._dir.mkdir(parents=True, exist_ok=True)
                f = open(self._path(component), "a", buffering=1)
                self._files[file_name] = f
            f.write(line + "\n")

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
        """
        if self._dir is None:
            return []
        path = self._path(component)
        if not path.exists():
            return []
        with self._lock:
            raw = path.read_text().splitlines()
        parse = _parse_json if self._format == "json" else _parse_line
        return [parse(line) for line in raw[-lines:]]

    def records(self) -> Iterator[dict]:
        """Yield every record in every log file, file by file, oldest first in each.

        Used by ``Context.trace()`` to follow a call across files. Lines
        that can't be parsed are skipped.

        Raises:
            ValueError: If file logging is off, or the format is ``text``,
                whose lines keep only ``ts``, ``level`` and ``message``.
        """
        if self._dir is None:
            raise ValueError("file logging is off: pass log_dir to read records back")
        if self._format != "json":
            raise ValueError('records need the "json" log format; [project.logging] sets "text"')
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob(f"*{FORMATS['json']}")):
            with self._lock:
                raw = path.read_text().splitlines()
            for line in raw:
                record = _parse_json(line)
                if record.get("ts") is not None:
                    yield record

    def logger_for(self, component: str) -> Logger:
        """Return a ``Logger`` bound to ``component``'s own log file."""
        return Logger(self, component)

    def close(self) -> None:
        """Close every open file handle. Safe to call even if none were opened."""
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()

    def _path(self, component: str) -> Path:
        """Return ``component``'s log file, with the extension of the format."""
        return self._dir / f"{kebab(component)}{FORMATS[self._format]}"


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

    An event's line ends with its ids shortened to 8 characters —
    ``[call=b71d04aa parent=3f9a1c2e]``, ``parent=-`` for a top-level call —
    and a notification's with ``[parent=...]``. User fields follow as
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
        line += f" [call={_short(record['call'])} parent={_short(record.get('parent'))}]"
    elif "parent" in record:
        line += f" [parent={_short(record['parent'])}]"
    fields = record.get("fields") or {}
    if fields:
        line += " " + " ".join(f"{name}={value!r}" for name, value in fields.items())
    return line.replace("\\", "\\\\").replace("\n", "\\n")


def _short(call_id: object) -> str:
    """Return a call id shortened to its first 8 characters, or ``-`` for none."""
    return str(call_id)[:8] if call_id else "-"


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


def _format(value: object) -> str:
    """Return the log format ``value`` names, for ``[project.logging] format``."""
    name = value.lower() if isinstance(value, str) else None
    if name not in FORMATS:
        raise ValueError(
            f"[project.logging] format = {value!r}: expected one of {', '.join(FORMATS)}"
        )
    return name
