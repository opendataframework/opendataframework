"""Per-component file logging.

``LogManager`` owns one log file per component name, scoped to a single
``Context`` — no process-global state, so multiple ``Project`` instances in
the same process never share log files or file handles (see
``docs/context.md`` / ``CLAUDE.md``'s "no global mutable state" constraint).

Two ways log lines get written:

* Automatically, by ``Context``/``Resolver``/``Lifecycle`` — resolution,
  ``setup``/``run``/``stop``, and ``execute()`` are logged with no code
  changes required anywhere.
* Explicitly, by component code that declares ``logger: Logger`` in its
  constructor. ``Resolver`` special-cases this type: each consumer receives
  a ``Logger`` already bound to its own class name, so ``self.logger.info(x)``
  needs no name argument and still lands in that component's own file.
"""

import re
import threading
from datetime import datetime
from pathlib import Path

from opendataframework.utils import kebab

_LINE_RE = re.compile(r"^(\S+ \S+) (\S+)\s+(.*)$")


class LogManager:
    """Owns per-component log files for a single ``Context``.

    When ``log_dir`` is ``None`` (the default), logging is a no-op — writes
    are dropped and ``tail()`` returns an empty list. This keeps the
    framework's default (and its test suite) free of stray files, while
    ``Project.from_config``/``from_dict`` opt in to a real ``log_dir``.

    Args:
        log_dir: Directory to write ``<component>.log`` files under, or
            ``None`` to disable file logging entirely.
    """

    def __init__(self, log_dir: str | Path | None = None) -> None:
        """Set the log directory (or ``None`` to disable file logging)."""
        self._dir = Path(log_dir) if log_dir is not None else None
        self._lock = threading.Lock()
        self._files: dict[str, object] = {}

    def write(self, component: str, level: str, message: str) -> None:
        """Append one log line for ``component``. No-op if logging is disabled."""
        if self._dir is None:
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
    bound to the requesting class's own name, rather than a single shared
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
