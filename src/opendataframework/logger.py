"""Per-component file logging.

``LogManager`` owns one log file per ``<namespace>.<name>`` key (see
``opendataframework.namespace.qualified``), scoped to a single
``Context`` — no process-global state, so multiple ``Project`` instances in
the same process never share log files or file handles (see
``docs/context.md`` / ``CLAUDE.md``'s "no global mutable state" constraint).

Three ways log lines get written:

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

Which lines are kept is set by level thresholds — ``[project.logging]`` in
the project config; see ``LogManager``.
"""

import re
import threading
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from opendataframework.utils import kebab

_LINE_RE = re.compile(r"^(\S+ \S+) (\S+)\s+(.*)$")

LEVELS: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
"""Level names, in increasing severity."""

SOURCES = ("events", "notifications")
"""Framework sources a line can come from, each settable on its own."""

_DEFAULT_LEVEL = "INFO"


class LogManager:
    """Owns per-component log files for a single ``Context``.

    When ``log_dir`` is ``None`` (the default), logging is a no-op — writes
    are dropped and ``tail()`` returns an empty list. This keeps the
    framework's default (and its test suite) free of stray files, while
    ``Project.from_config``/``from_dict`` opt in to a real ``log_dir``.

    A line is written only if its level is at or above the threshold for its
    component and source. ``levels`` mirrors ``[project.logging]``::

        level = "INFO"            # default for every line
        events = "WARNING"        # lines Events writes
        notifications = "INFO"    # lines Notifications writes

        [task]                    # a namespace
        level = "INFO"            # every task, every source
        take-orders = "DEBUG"     # one component, every source

    The most specific setting wins: ``task.take-orders``, then
    ``task.level``, then the line's source (``events``/``notifications``),
    then ``level``, then ``INFO``. Level names are ``DEBUG``, ``INFO``,
    ``WARNING`` and ``ERROR``, in any casing.

    Args:
        log_dir: Directory to write ``<namespace>.<name>.log`` files under, or
            ``None`` to disable file logging entirely.
        levels: Level thresholds, as above. ``None`` keeps ``INFO`` and up.

    Raises:
        ValueError: If ``levels`` has an unknown level name, or a value
            that is neither a level name nor, for a namespace, a table of them.
    """

    def __init__(
        self, log_dir: str | Path | None = None, levels: Mapping[str, object] | None = None
    ) -> None:
        """Set the log directory (or ``None`` to disable file logging) and thresholds."""
        self._dir = Path(log_dir) if log_dir is not None else None
        self._lock = threading.Lock()
        self._files: dict[str, object] = {}
        self._default = LEVELS[_DEFAULT_LEVEL]
        self._sources: dict[str, int] = {}
        self._namespaces: dict[str, dict[str, int]] = {}
        for key, value in (levels or {}).items():
            if key == "level":
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
        """Return the lowest level written for ``component``'s lines from ``source``.

        Args:
            component: A ``<namespace>.<name>`` key.
            source: ``"events"``, ``"notifications"``, or ``None`` for any
                other line (a ``Logger`` call, a resolution line, ...).
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
        """Check every namespace and component ``levels`` names exists.

        Called by ``Context.open()`` once it has resolved, so a typo fails
        loudly instead of silently setting nothing.

        Args:
            namespaces: The Context's namespace names, as keys start with.
            keys: Every resolved ``<namespace>.<name>`` key.

        Raises:
            ValueError: If ``levels`` names a namespace or component that
                does not exist.
        """
        namespaces = set(namespaces)
        names: dict[str, set[str]] = {}
        for key in keys:
            namespace, _, name = key.partition(".")
            names.setdefault(namespace, set()).add(name)
        for namespace, table in self._namespaces.items():
            if namespace not in namespaces:
                valid = ", ".join(["level", *SOURCES, *sorted(namespaces)])
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

    def write(self, component: str, level: str, message: str, source: str | None = None) -> None:
        """Append one log line for ``component``, if ``level`` passes its threshold.

        No-op if logging is disabled. ``source`` is ``"events"`` or
        ``"notifications"`` for the lines those write, ``None`` otherwise.
        """
        if self._dir is None or LEVELS[level] < self.threshold(component, source):
            return
        name = kebab(component)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} {level:<8} {message}\n"
        with self._lock:
            f = self._files.get(name)
            if f is None:
                self._dir.mkdir(parents=True, exist_ok=True)
                f = open(self._dir / f"{name}.log", "a", buffering=1)
                self._files[name] = f
            f.write(line)

    def tail(self, component: str, lines: int = 300) -> list[dict]:
        """Return the last ``lines`` entries for ``component`` as parsed dicts.

        Returns:
            A list of ``{"ts": str | None, "level": str, "message": str}``,
            oldest first. Empty if logging is disabled or nothing was ever
            written for this component.
        """
        if self._dir is None:
            return []
        path = self._dir / f"{kebab(component)}.log"
        if not path.exists():
            return []
        with self._lock:
            raw = path.read_text().splitlines()
        return [_parse_line(line) for line in raw[-lines:]]

    def logger_for(self, component: str) -> Logger:
        """Return a ``Logger`` bound to ``component``'s own log file."""
        return Logger(self, component)

    def close(self) -> None:
        """Close every open file handle. Safe to call even if none were opened."""
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()


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
                self.logger.info("export starting")
                ...
    """

    def __init__(self, manager: LogManager, component: str) -> None:
        """Bind this logger to ``component``'s log file on ``manager``."""
        self._manager = manager
        self._component = component

    def debug(self, message: str) -> None:
        """Log a DEBUG-level message for this component."""
        self._manager.write(self._component, "DEBUG", message)

    def info(self, message: str) -> None:
        """Log an INFO-level message for this component."""
        self._manager.write(self._component, "INFO", message)

    def warning(self, message: str) -> None:
        """Log a WARNING-level message for this component."""
        self._manager.write(self._component, "WARNING", message)

    def error(self, message: str) -> None:
        """Log an ERROR-level message for this component."""
        self._manager.write(self._component, "ERROR", message)


def _parse_line(line: str) -> dict:
    """Parse one ``tail()`` log line into ``{"ts", "level", "message"}``."""
    m = _LINE_RE.match(line)
    if not m:
        return {"ts": None, "level": "INFO", "message": line}
    ts, level, message = m.groups()
    return {"ts": ts, "level": level, "message": message}


def _level(value: object, key: str) -> int:
    """Return the numeric level ``value`` names, for the ``[project.logging]`` entry ``key``."""
    name = value.upper() if isinstance(value, str) else None
    if name not in LEVELS:
        raise ValueError(
            f"[project.logging] {key} = {value!r}: expected one of {', '.join(LEVELS)}"
        )
    return LEVELS[name]
