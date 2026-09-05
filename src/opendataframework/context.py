"""``Context`` — dependency resolution, instance creation, and lifecycle.

Composes ``Resolver`` (pure DI: gather registered classes → topological
sort → instantiate with injected dependencies), ``Lifecycle`` (protocol
dispatch: setup/run/stop for services, on_start/on_stop for components),
and ``StreamManager`` (background threads for ``StreamableProtocol``
repositories). ``Context`` is the only public entry point of the three —
``Resolver``/``Lifecycle``/``StreamManager`` are internal collaborators.
"""

import functools
import inspect
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from queue import Empty, Full, Queue
from typing import TypeVar, cast

from opendataframework.component import Component, OnStartProtocol, OnStopProtocol
from opendataframework.config import Config
from opendataframework.logger import Logger, LogManager
from opendataframework.namespace import Namespace
from opendataframework.pipeline import Pipeline
from opendataframework.repository import (
    CloseStreamProtocol,
    OpenStreamProtocol,
    Repository,
    StreamableProtocol,
)
from opendataframework.service import Service, ServiceProtocol
from opendataframework.task import Task

_STREAM_ENDED = object()

T = TypeVar("T")

_DEFAULT_NAMESPACES: frozenset[type[Namespace]] = frozenset(
    {Component, Repository, Service, Task, Pipeline}
)


def _logged_execute(execute, name: str, log_manager: LogManager):
    """Wrap a bound ``execute`` method to log its start, duration, and errors."""

    @functools.wraps(execute)
    def wrapped(*args, **kwargs):
        """Call the wrapped ``execute``, logging its start, duration, and errors."""
        log_manager.write(name, "INFO", "execute() started")
        start = time.monotonic()
        try:
            result = execute(*args, **kwargs)
        except Exception as exc:
            log_manager.write(name, "ERROR", f"execute() raised {exc!r}")
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        log_manager.write(name, "INFO", f"execute() completed in {elapsed_ms:.1f}ms")
        return result

    return wrapped


class Resolver:
    """Builds the dependency graph and creates instances in dependency order.

    Collects registered classes from the given namespaces, derives the
    dependency graph from constructor signatures, sorts classes topologically,
    and instantiates each one with its dependencies injected. Has no knowledge
    of lifecycle or framework protocols — the one exception is ``Logger``
    (see ``opendataframework.logger``), which is resolved contextually: a ``logger: Logger``
    constructor parameter receives an instance bound to the *consuming*
    class's own name rather than a single shared instance, and every
    instantiation is logged to that component's file.

    Args:
        namespaces: Namespace subclasses to collect registered classes from.
        log_manager: Owns per-component log files. Defaults to a disabled
            ``LogManager`` (writes become no-ops) when omitted.

    Example:
        >>> class NS(Namespace): ...
        >>> @NS
        ... class Config: ...
        >>> @NS
        ... class Postgres:
        ...     def __init__(self, config: Config): ...
        >>> resolver = Resolver({NS})
        >>> resolver.resolve()
        >>> isinstance(resolver.instances[Postgres], Postgres)
        True
        >>> resolver.instances[Postgres].config is resolver.instances[Config]
        True
    """

    def __init__(
        self,
        namespaces: Iterable[type[Namespace]],
        extra_instances: dict[type, object] | None = None,
        log_manager: LogManager | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        self._namespaces = set(namespaces)
        self._instances: dict[type, object] = dict(extra_instances or {})
        self._order: list[type] = []
        self._log_manager = log_manager if log_manager is not None else LogManager()

    @property
    def instances(self) -> dict[type, object]:
        """Resolved class-to-instance mapping, populated after ``resolve()``.

        Returns:
            A shallow copy of the internal mapping. Mutating the returned dict
            does not affect the resolver's state.
        """
        return dict(self._instances)

    @property
    def order(self) -> list[type]:
        """Classes in dependency order (leaves first), populated after ``resolve()``.

        Returns:
            A copy of the ordered class list.
        """
        return list(self._order)

    def resolve(self) -> None:
        """Gather registered classes, sort by dependency order, and instantiate.

        Runs the full resolution pipeline: collect classes from namespaces →
        topological sort → instantiate with injected dependencies.

        Raises:
            ValueError: If a circular dependency is detected among registered classes.

        Example:
            >>> class NS(Namespace): ...
            >>> @NS
            ... class A: ...
            >>> @NS
            ... class B:
            ...     def __init__(self, a: A): ...
            >>> resolver = Resolver({NS})
            >>> resolver.resolve()
            >>> resolver.order
            [A, B]
        """
        classes = self._gather()
        self._order = self._sort(classes)
        for cls in self._order:
            self._instances[cls] = self._instantiate(cls)

    def _gather(self) -> set[type]:
        """Collect all classes registered across the configured namespaces.

        Returns:
            Flat set of every class found in ``self._namespaces``.
        """
        classes: set[type] = set()
        for ns in self._namespaces:
            for _, cls in ns.items():
                classes.add(cls)
        return classes

    @staticmethod
    def dependencies(cls: type) -> dict[str, type]:
        """Return typed constructor parameters for ``cls``.

        Inspects ``cls.__init__`` and returns only parameters that carry a
        type annotation which is itself a type (i.e. not a string forward
        reference or a generic alias).

        Public so other framework code (e.g. topology introspection) can
        derive the same dependency edges without duplicating this logic.

        Args:
            cls: The class to inspect.

        Returns:
            Mapping of parameter name to annotated type. Empty if the
            signature cannot be inspected or no typed parameters exist.
        """
        try:
            sig = inspect.signature(cls.__init__)
        except ValueError, TypeError:
            return {}
        return {
            name: param.annotation
            for name, param in sig.parameters.items()
            if name != "self"
            and param.annotation is not inspect.Parameter.empty
            and isinstance(param.annotation, type)
        }

    def _sort(self, classes: set[type]) -> list[type]:
        """Return ``classes`` in topological order (leaves first).

        Uses Kahn's algorithm. Only dependencies that are themselves present
        in ``classes`` are considered — external types are ignored.

        Args:
            classes: The full set of classes to order.

        Returns:
            Classes sorted so every dependency appears before its dependents.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        all_deps = {cls: self.dependencies(cls) for cls in classes}
        registered_deps = {
            cls: {name: dep for name, dep in deps.items() if dep in classes}
            for cls, deps in all_deps.items()
        }
        in_degree = {cls: len(deps) for cls, deps in registered_deps.items()}
        dependents: dict[type, set[type]] = {cls: set() for cls in classes}
        for cls, deps in registered_deps.items():
            for dep in deps.values():
                dependents[dep].add(cls)
        queue = sorted(
            (cls for cls in classes if in_degree[cls] == 0),
            key=lambda c: c.__name__,
        )
        result: list[type] = []
        while queue:
            cls = queue.pop(0)
            result.append(cls)
            for dependent in sorted(dependents[cls], key=lambda c: c.__name__):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if len(result) != len(classes):
            remaining = ", ".join(c.__name__ for c in classes - set(result))
            raise ValueError(f"Circular dependency detected among: {remaining}")
        return result

    def _instantiate(self, cls: type) -> object:
        """Instantiate ``cls`` with its dependencies injected from ``self._instances``.

        A ``dep`` annotated exactly as ``Logger`` is special-cased: instead of
        a shared instance, ``cls`` receives a ``Logger`` bound to its own
        name (see ``opendataframework.logger.LogManager.logger_for``). All other
        dependencies are only passed if already present in ``self._instances``
        — unregistered types in the constructor signature are silently
        ignored.

        Args:
            cls: The class to instantiate.

        Returns:
            A new instance of ``cls`` with resolved dependencies injected.
        """
        kwargs = {}
        for name, dep in self.dependencies(cls).items():
            if dep is Logger:
                kwargs[name] = self._log_manager.logger_for(cls.__name__)
            elif dep in self._instances:
                kwargs[name] = self._instances[dep]
        instance = cls(**kwargs)
        self._log_manager.write(cls.__name__, "INFO", f"{cls.__name__} resolved")
        return instance


class Lifecycle:
    """Drives the startup and shutdown lifecycle for resolved instances.

    Iterates instances in dependency order on start, and in reverse order on
    stop. Dispatches to the appropriate protocol for each instance. Has no
    knowledge of dependency resolution or instance creation.

    Every stage transition is also logged to the component's own log file via
    ``log_manager`` (see ``opendataframework.logger``), giving every ``Service`` a log
    record with no code changes required.

    Args:
        instances: Class-to-instance mapping produced by ``Resolver``.
        order: Classes in dependency order, as returned by ``Resolver.order``.
        log_manager: Owns per-component log files. Defaults to a disabled
            ``LogManager`` (writes become no-ops) when omitted.

    Example:
        >>> lifecycle = Lifecycle(instances={...}, order=[...])
        >>> lifecycle.on_start()   # services set up and backgrounded
        >>> lifecycle.on_stop()    # services stopped in reverse order
    """

    def __init__(
        self,
        instances: dict[type, object],
        order: list[type],
        log_manager: LogManager | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        self._instances = instances
        self._order = order
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._threads: list[threading.Thread] = []
        self._running: dict[type, bool] = {}

    def on_start(self) -> None:
        """Activate all instances in dependency order.

        For each ``ServiceProtocol`` instance: calls ``setup()`` (blocking),
        then spawns ``run()`` in a daemon thread. Every other instance that
        defines an ``on_start()`` method — a ``Component`` or ``Repository``
        opting into the lightweight hook documented in ``docs/repository.md``
        — has it called directly (blocking; expected to return quickly, per
        ``docs/project.md``). Instances with neither are skipped — they have
        no lifecycle contract.

        Example:
            >>> lifecycle.on_start()
            # Postgres.setup() called, Postgres.run() backgrounded
            # Users.on_start() called directly
        """
        for cls in self._order:
            instance = self._instances[cls]
            if isinstance(instance, ServiceProtocol):
                self.start_one(cls)
            elif isinstance(instance, OnStartProtocol):
                self._activate_one(cls, instance)

    def _activate_one(self, cls: type, instance: object) -> None:
        """Call a non-``Service`` instance's ``on_start()`` hook."""
        name = cls.__name__
        self._log_manager.write(name, "INFO", "on_start() called")
        instance.on_start()
        self._log_manager.write(name, "INFO", "on_start() complete")

    def start_one(self, cls: type) -> None:
        """Start a single ``ServiceProtocol`` instance. No-op if already running.

        Args:
            cls: A class present in ``self._instances`` whose instance
                implements ``ServiceProtocol``.

        Example:
            >>> lifecycle.start_one(Postgres)
            # Postgres.setup() called, Postgres.run() backgrounded
        """
        if self._running.get(cls):
            return
        instance = self._instances[cls]
        name = cls.__name__
        self._log_manager.write(name, "INFO", "setup() starting")
        instance.setup()
        self._log_manager.write(name, "INFO", "setup() complete")
        t = threading.Thread(target=self._run, args=(cls, instance), daemon=True)
        t.start()
        self._threads.append(t)
        self._running[cls] = True

    def stop_one(self, cls: type) -> None:
        """Stop a single running ``ServiceProtocol`` instance. No-op if not running.

        Args:
            cls: A class present in ``self._instances`` whose instance
                implements ``ServiceProtocol``.

        Example:
            >>> lifecycle.stop_one(Postgres)
            # Postgres.stop() called
        """
        if not self._running.get(cls):
            return
        instance = self._instances[cls]
        name = cls.__name__
        self._log_manager.write(name, "INFO", "stop() called")
        instance.stop()
        self._log_manager.write(name, "INFO", "stop() complete")
        self._running[cls] = False

    def is_running(self, cls: type) -> bool:
        """Return whether ``cls``'s instance is currently started."""
        return self._running.get(cls, False)

    def _run(self, cls: type, instance: ServiceProtocol) -> None:
        """Run ``instance.run()``, logging its start, return, and any exception."""
        name = cls.__name__
        self._log_manager.write(name, "INFO", "run() started")
        try:
            instance.run()
            self._log_manager.write(name, "INFO", "run() returned")
        except Exception as exc:
            self._log_manager.write(name, "ERROR", f"run() raised {exc!r}")
            raise

    def on_stop(self) -> None:
        """Deactivate all instances in reverse dependency order.

        For each ``ServiceProtocol`` instance: calls ``stop()``. Every other
        instance that defines an ``on_stop()`` method has it called directly
        (blocking; expected to return quickly). Dependents are stopped
        before their dependencies, ensuring nothing is torn down while still
        in use.

        Example:
            >>> lifecycle.on_stop()
            # UsersApi.stop() called before Postgres.stop()
            # Users.on_stop() called before Postgres.stop()
        """
        for cls in reversed(self._order):
            instance = self._instances[cls]
            if isinstance(instance, ServiceProtocol):
                self.stop_one(cls)
            elif isinstance(instance, OnStopProtocol):
                self._deactivate_one(cls, instance)

    def _deactivate_one(self, cls: type, instance: object) -> None:
        """Call a non-``Service`` instance's ``on_stop()`` hook."""
        name = cls.__name__
        self._log_manager.write(name, "INFO", "on_stop() called")
        instance.on_stop()
        self._log_manager.write(name, "INFO", "on_stop() complete")


def _publish_latest(q: Queue, item: object) -> None:
    """Replace ``q``'s pending item, if any, with ``item``.

    Keeps at most one item queued per subscriber — a slow viewer sees the
    newest frame next, never a growing backlog of stale ones.
    """
    try:
        q.get_nowait()
    except Empty:
        pass
    try:
        q.put_nowait(item)
    except Full:
        pass


class StreamManager:
    """Drives background stream-consumer threads for ``StreamableProtocol`` repositories.

    Mirrors ``Lifecycle``'s start_one/stop_one/is_running for services, but
    for repository streams: a single background thread iterates
    ``instance.stream()`` and fans each entity out to every subscriber queue,
    so multiple independent subscribers share one live feed instead of each
    opening a second, independent generator over the same resource.

    If the instance defines ``open_stream()``/``close_stream()``, those are
    called around the background thread's lifetime — ``open_stream()``
    blocking before the thread starts, ``close_stream()`` after it has fully
    exited — the streaming analogue of a ``Service``'s ``setup()``/``stop()``
    bracketing its backgrounded ``run()``. This is how a repository ties an
    expensive resource (e.g. a camera device) to the stream actually being
    active, rather than to the whole ``Project``'s lifetime: unlike
    ``on_start()``/``on_stop()`` (called once, at ``Project`` start/stop),
    these fire on every ``start_stream()``/``stop_stream()`` call. Both are
    optional — a stream reading from an already-open resource (a queue, a
    socket handed in via the constructor) needs neither.

    ``stop()`` cooperates with the background thread via a ``threading.Event``
    checked between yields, rather than calling ``.close()`` on the generator
    from another thread — generators aren't safe to resume or close from a
    thread other than the one currently driving them.

    ``self._lock`` guards only the rare, structural start/subscribe/stop
    operations. The per-frame hot path in ``_run`` deliberately never
    acquires it: a producer with no natural blocking point (unlike a real
    device read) spins fast enough to starve any other thread contending for
    the same lock under CPython's GIL scheduling, so reads there go through
    plain dict/Event lookups instead, which are safe without a lock.
    """

    def __init__(self, log_manager: LogManager | None = None) -> None:
        """See class docstring; ``log_manager`` defaults to a disabled ``LogManager``."""
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._threads: dict[type, threading.Thread] = {}
        self._stop_events: dict[type, threading.Event] = {}
        self._subscribers: dict[type, list[Queue]] = {}
        self._starting: set[type] = set()
        self._lock = threading.Lock()

    def start(self, cls: type, instance: StreamableProtocol) -> None:
        """Start streaming ``instance`` in a background thread. No-op if already streaming.

        Calls ``instance.open_stream()`` first (blocking), if defined, before
        spawning the thread — mirroring a ``Service``'s blocking ``setup()``
        ahead of its backgrounded ``run()``. If ``open_stream()`` raises, the
        exception propagates and no thread is spawned.
        """
        with self._lock:
            if cls in self._threads or cls in self._starting:
                return
            self._starting.add(cls)
        name = cls.__name__
        try:
            if isinstance(instance, OpenStreamProtocol):
                self._log_manager.write(name, "INFO", "open_stream() called")
                instance.open_stream()
                self._log_manager.write(name, "INFO", "open_stream() complete")
            with self._lock:
                self._subscribers[cls] = []
                event = threading.Event()
                self._stop_events[cls] = event
                thread = threading.Thread(
                    target=self._run, args=(cls, instance, event), daemon=True
                )
                self._threads[cls] = thread
        finally:
            with self._lock:
                self._starting.discard(cls)
        self._log_manager.write(name, "INFO", "stream started")
        thread.start()

    def stop(self, cls: type) -> None:
        """Stop a running stream and wait for its thread to exit. No-op if not streaming.

        Waits for the thread to fully exit before returning — by then, its
        ``close_stream()`` call (see ``_run``) has already happened.
        """
        with self._lock:
            thread = self._threads.get(cls)
            event = self._stop_events.get(cls)
        if thread is None:
            return
        event.set()
        thread.join(timeout=5)
        self._log_manager.write(cls.__name__, "INFO", "stream stopped")

    def stop_all(self) -> None:
        """Stop every currently running stream. Used by ``Context.close()``."""
        for cls in list(self._threads):
            self.stop(cls)

    def is_streaming(self, cls: type) -> bool:
        """Return whether ``cls``'s stream is currently running."""
        return cls in self._threads

    def subscribe(self, cls: type) -> Queue:
        """Attach a new subscriber queue to ``cls``'s running stream.

        Raises:
            KeyError: If ``cls`` is not currently streaming.
        """
        with self._lock:
            if cls not in self._subscribers:
                raise KeyError(cls)
            q: Queue = Queue(maxsize=1)
            self._subscribers[cls].append(q)
            return q

    def unsubscribe(self, cls: type, q: Queue) -> None:
        """Detach a subscriber queue previously returned by ``subscribe()``."""
        with self._lock:
            subs = self._subscribers.get(cls)
            if subs and q in subs:
                subs.remove(q)

    def _run(self, cls: type, instance: StreamableProtocol, stop_event: threading.Event) -> None:
        """Drive ``instance.stream()``, fanning entities out to subscribers until done."""
        name = cls.__name__
        try:
            for entity in instance.stream():
                if stop_event.is_set():
                    break
                for q in list(self._subscribers.get(cls, ())):
                    _publish_latest(q, entity)
        except Exception as exc:
            self._log_manager.write(name, "ERROR", f"stream raised {exc!r}")
        finally:
            # Runs whether the loop above ended via stop_event, the source
            # exhausting itself (e.g. a device disconnecting), or an
            # exception — close_stream() releases the resource in all three
            # cases, not just an explicit stop_stream() call.
            if isinstance(instance, CloseStreamProtocol):
                self._log_manager.write(name, "INFO", "close_stream() called")
                try:
                    instance.close_stream()
                except Exception as exc:
                    self._log_manager.write(name, "ERROR", f"close_stream() raised {exc!r}")
                else:
                    self._log_manager.write(name, "INFO", "close_stream() complete")
            with self._lock:
                subscribers = self._subscribers.pop(cls, [])
                self._threads.pop(cls, None)
                self._stop_events.pop(cls, None)
            for q in subscribers:
                _publish_latest(q, _STREAM_ENDED)


class Context:
    """Resolves dependencies, creates instances, and drives component lifecycles.

    Composes a ``Resolver`` (pure DI: gather → sort → instantiate) and a
    ``Lifecycle`` (protocol dispatch: setup → run → stop for services).

    By default, collects classes from all four built-in namespaces:
    ``Component``, ``Service``, ``Task``, and ``Pipeline``. Pass ``namespaces``
    to override — primarily useful for testing.

    Args:
        namespaces: Namespace subclasses to collect registered classes from.
            Defaults to ``{Component, Service, Task, Pipeline}``.
        config: Configuration dict, pre-seeded as ``Config`` into the
            container.
        log_dir: Directory to write per-component ``<name>.log`` files under.
            ``None`` (the default) disables file logging entirely — see
            ``opendataframework.logger.LogManager``. ``Project.from_config``/``from_dict``
            opt in to a real directory.

    Attributes:
        instances: Class-to-instance mapping, populated after ``open()`` returns.
            Backs ``Context.get(cls)``, the typed lookup by class.

    Example:
        Default usage via context manager::

            with Context() as ctx:
                api = ctx.instances[UsersApi]

        Isolated usage in tests::

            class TestNS(Namespace): ...

            @TestNS
            class Postgres:
                def setup(self): ...
                def run(self): ...
                def stop(self): ...

            with Context(namespaces={TestNS}) as ctx:
                assert isinstance(ctx.instances[Postgres], Postgres)

        Explicit lifecycle control (e.g. from ``Project``)::

            ctx = Context()
            ctx.open()
            # application running
            ctx.close()
    """

    def __init__(
        self,
        namespaces: Iterable[type[Namespace]] | None = None,
        config: dict | None = None,
        log_dir: str | Path | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        extra = {Config: Config(config)} if config is not None else {}
        self._log_manager = LogManager(log_dir)
        self._resolver = Resolver(
            namespaces if namespaces is not None else _DEFAULT_NAMESPACES,
            extra_instances=extra,
            log_manager=self._log_manager,
        )
        self._lifecycle: Lifecycle | None = None
        self._stream_manager = StreamManager(self._log_manager)

    @property
    def instances(self) -> dict[type, object]:
        """Class-to-instance mapping produced by the resolver.

        Returns:
            A shallow copy of the resolved instances. Mutating the returned
            dict does not affect the context's state.
        """
        return self._resolver.instances

    def get(self, cls: type[T]) -> T:
        """Return the resolved instance of ``cls``, typed as ``cls``.

        Unlike ``instances[cls]``, the return type is inferred from the
        argument at the call site — ``context.get(Books)`` types as
        ``Books``, no annotation or cast required.

        Args:
            cls: The registered class to resolve.

        Raises:
            KeyError: If ``cls`` was not resolved (not registered, or
                ``open()`` has not been called yet).

        Example:
            >>> books = context.get(Books)
            >>> books.all()
            [Book(id=1, title='Dune', author='Frank Herbert')]
        """
        return cast(T, self._resolver.instances[cls])

    def open(self) -> None:
        """Resolve all registered classes and drive their startup lifecycle.

        Runs ``Resolver.resolve()``, wraps every ``Task``/``Pipeline``
        instance's ``execute()`` for automatic logging, then constructs a
        ``Lifecycle`` from the result and calls ``Lifecycle.on_start()``.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        self._resolver.resolve()
        self._instrument_execute()
        self._lifecycle = Lifecycle(
            self._resolver.instances, self._resolver.order, self._log_manager
        )
        self._lifecycle.on_start()

    def close(self) -> None:
        """Tear down all components in reverse dependency order.

        Calls ``Lifecycle.on_stop()``, stops any still-running repository
        streams, then closes any open log files. Safe to call even if
        ``open()`` was never called.
        """
        if self._lifecycle is not None:
            self._lifecycle.on_stop()
        self._stream_manager.stop_all()
        self._log_manager.close()

    def start(self, name: str) -> None:
        """Start a single resolved ``Service`` by class name. No-op if already running.

        Args:
            name: The class name of a resolved instance (e.g. ``"Postgres"``).

        Raises:
            KeyError: If no resolved instance matches ``name``.
            TypeError: If the matched instance is not a ``Service``.
        """
        cls, instance = self._resolved(name)
        if not isinstance(instance, ServiceProtocol):
            raise TypeError(f"{name} is not a Service")
        self._lifecycle.start_one(cls)

    def stop(self, name: str) -> None:
        """Stop a single running ``Service`` by class name. No-op if not running.

        Args:
            name: The class name of a resolved instance (e.g. ``"Postgres"``).

        Raises:
            KeyError: If no resolved instance matches ``name``.
            TypeError: If the matched instance is not a ``Service``.
        """
        cls, instance = self._resolved(name)
        if not isinstance(instance, ServiceProtocol):
            raise TypeError(f"{name} is not a Service")
        self._lifecycle.stop_one(cls)

    def is_running(self, name: str) -> bool:
        """Return whether the ``Service`` matching ``name`` is currently started.

        Raises:
            KeyError: If no resolved instance matches ``name``.
        """
        cls, instance = self._resolved(name)
        return isinstance(instance, ServiceProtocol) and self._lifecycle.is_running(cls)

    def start_stream(self, name: str) -> None:
        """Start a single resolved ``StreamableProtocol`` repository's stream by class name.

        Mirrors ``start()`` for services: spawns a background thread that
        drives ``instance.stream()`` so it keeps running independent of any
        one viewer's connection. No-op if already streaming.

        Args:
            name: The class name of a resolved instance (e.g. ``"Webcam"``).

        Raises:
            KeyError: If no resolved instance matches ``name``.
            TypeError: If the matched instance is not ``StreamableProtocol``.
        """
        cls, instance = self._resolved(name)
        if not isinstance(instance, StreamableProtocol):
            raise TypeError(f"{name} is not streamable")
        self._stream_manager.start(cls, instance)

    def stop_stream(self, name: str) -> None:
        """Stop a single running repository stream by class name. No-op if not streaming.

        Args:
            name: The class name of a resolved instance (e.g. ``"Webcam"``).

        Raises:
            KeyError: If no resolved instance matches ``name``.
            TypeError: If the matched instance is not ``StreamableProtocol``.
        """
        cls, instance = self._resolved(name)
        if not isinstance(instance, StreamableProtocol):
            raise TypeError(f"{name} is not streamable")
        self._stream_manager.stop(cls)

    def is_streaming(self, name: str) -> bool:
        """Return whether the repository stream matching ``name`` is currently running.

        Raises:
            KeyError: If no resolved instance matches ``name``.
        """
        cls, instance = self._resolved(name)
        return isinstance(instance, StreamableProtocol) and self._stream_manager.is_streaming(cls)

    def iter_stream(self, name: str) -> Iterator[object]:
        """Attach as one subscriber to a repository's already-running stream.

        Does not start or stop the stream itself — see ``start_stream()``.
        Iterating stops (and detaches the subscription) when the stream is
        stopped, or when the caller stops iterating (e.g. a client
        disconnect closes this generator).

        Args:
            name: The class name of a resolved instance (e.g. ``"Webcam"``).

        Raises:
            KeyError: If no resolved instance matches ``name``, or if it
                isn't currently streaming.
        """
        cls, _ = self._resolved(name)
        q = self._stream_manager.subscribe(cls)
        return self._drain_stream(cls, q)

    def _drain_stream(self, cls: type, q: Queue) -> Iterator[object]:
        """Yield items from ``q`` until the stream ends, unsubscribing on exit."""
        try:
            while True:
                item = q.get()
                if item is _STREAM_ENDED:
                    return
                yield item
        finally:
            self._stream_manager.unsubscribe(cls, q)

    def execute(self, name: str) -> object:
        """Execute a single resolved ``Task`` or ``Pipeline`` by class name.

        Args:
            name: The class name of a resolved instance (e.g. ``"DailyAnalytics"``).

        Returns:
            Whatever ``execute()`` returns.

        Raises:
            KeyError: If no resolved instance matches ``name``.
            TypeError: If the matched instance is not a ``Task`` or ``Pipeline``.
        """
        cls, instance = self._resolved(name)
        executable = set(dict(Task.items()).values()) | set(dict(Pipeline.items()).values())
        if cls not in executable:
            raise TypeError(f"{name} is not a Task or Pipeline")
        return instance.execute()

    def _resolved(self, name: str) -> tuple[type, object]:
        """Look up a resolved ``(cls, instance)`` pair by exact class name.

        Raises:
            KeyError: If no resolved instance matches ``name``.
        """
        for cls, instance in self._resolver.instances.items():
            if cls.__name__ == name:
                return cls, instance
        raise KeyError(name)

    def tail_logs(self, component: str, lines: int = 300) -> list[dict]:
        """Return the last ``lines`` log entries for a resolved component.

        Args:
            component: The component's class name (e.g. ``"Postgres"``).
            lines: Maximum number of most-recent entries to return.

        Returns:
            A list of ``{"ts", "level", "message"}`` dicts, oldest first.
            Empty if file logging is disabled or nothing was logged.
        """
        return self._log_manager.tail(component, lines)

    def _instrument_execute(self) -> None:
        """Wrap ``execute()`` on every resolved ``Task``/``Pipeline`` instance.

        Logs start, completion (with duration), and any exception to that
        component's own log file — with no code changes required in the
        Task/Pipeline classes themselves.
        """
        executable = set(dict(Task.items()).values()) | set(dict(Pipeline.items()).values())
        for cls, instance in self._resolver.instances.items():
            if cls in executable and hasattr(instance, "execute"):
                instance.execute = _logged_execute(
                    instance.execute, cls.__name__, self._log_manager
                )

    def __enter__(self) -> Context:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
