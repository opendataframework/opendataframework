"""``Context`` — dependency resolution, instance creation, and lifecycle.

Composes ``Resolver`` (pure DI: gather registered classes and functions →
topological sort → instantiate classes and bind functions with injected
dependencies), ``Lifecycle`` (protocol
dispatch: setup/run/stop for services, on_start/on_stop for components),
and ``StreamManager`` (background threads for ``StreamableProtocol``
repositories). ``Context`` is the only public entry point of the three —
``Resolver``/``Lifecycle``/``StreamManager`` are internal collaborators.
Every protocol call the three make is logged and also reported as an
``Event`` to the ``Context``'s ``Events`` (see ``opendataframework.events``).
"""

import contextvars
import functools
import inspect
import threading
import time
from collections.abc import Callable, Hashable, Iterable, Iterator
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Annotated, TypeAliasType, TypeVar, cast, get_origin, overload

from opendataframework.agent import Agent, AgentProtocol
from opendataframework.component import Component, OnStartProtocol, OnStopProtocol
from opendataframework.config import Config
from opendataframework.events import Events
from opendataframework.function import Function, FunctionProtocol, bind, string_hint
from opendataframework.logger import Logger, LogManager
from opendataframework.namespace import Namespace, parse, qualified
from opendataframework.pipeline import Pipeline, PipelineProtocol
from opendataframework.repository import (
    CloseStreamProtocol,
    OpenStreamProtocol,
    Repository,
    StreamableProtocol,
)
from opendataframework.service import Service, ServiceProtocol
from opendataframework.task import Task, TaskProtocol
from opendataframework.utils import normalize

_STREAM_ENDED = object()

T = TypeVar("T")
R = TypeVar("R")

_DEFAULT_NAMESPACES: frozenset[type[Namespace]] = frozenset(
    {Component, Repository, Service, Task, Pipeline, Agent, Function}
)

_LIFECYCLE_HOOKS = ("on_start", "on_stop")
_SERVICE_METHODS = ("setup", "run", "stop")
_STREAM_METHODS = ("stream", "open_stream", "close_stream")


def _is_async(func: object) -> bool:
    """Return whether ``func`` is an ``async def`` function or async generator."""
    return inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)


def _logged_execute(
    execute, name: str, log_manager: LogManager, events: Events, protocol: type, method: str
):
    """Wrap a bound ``execute`` method to log its start, duration, and errors.

    ``protocol`` and ``method`` name the protocol call being wrapped, so the
    same wrapper also serves an ``Agent``'s ``invoke()`` and a ``Function``
    called through the ``Context``. Each call is also reported to ``events``.
    """
    label = "call" if protocol is FunctionProtocol else f"{method}()"

    @functools.wraps(execute)
    def wrapped(*args, **kwargs):
        """Call the wrapped ``execute``, logging its start, duration, and errors."""
        with events.notify(name, protocol, method):
            log_manager.write(name, "INFO", f"{label} started")
            start = time.monotonic()
            try:
                result = execute(*args, **kwargs)
            except Exception as exc:
                log_manager.write(name, "ERROR", f"{label} raised {exc!r}")
                raise
            elapsed_ms = (time.monotonic() - start) * 1000
            log_manager.write(name, "INFO", f"{label} completed in {elapsed_ms:.1f}ms")
            return result

    return wrapped


def _dependency(annotation: object) -> type | Callable[..., object] | None:
    """Return the class or function a parameter annotation asks for, if any.

    A plain class asks for that class. ``Annotated[..., func]`` asks for the
    function named in its metadata — the first item that is a hashable,
    named callable and not a class. A ``type X = ...`` alias is read through.
    Anything else (a string forward reference, a generic alias) asks for
    nothing.
    """
    while isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, type):
        return annotation
    if get_origin(annotation) is Annotated:
        for item in annotation.__metadata__:
            if (
                not isinstance(item, type)
                and callable(item)
                and isinstance(item, Hashable)
                and hasattr(item, "__name__")
            ):
                return item
    return None


class Resolver:
    """Builds the dependency graph and creates instances in dependency order.

    Collects registered classes and functions from the given namespaces,
    derives the dependency graph from their signatures, sorts them
    topologically, and instantiates each class — or binds each function —
    with its dependencies injected. Has no knowledge
    of lifecycle or framework protocols — the exceptions are ``Logger``
    (see ``opendataframework.logger``), which is resolved contextually: a ``logger: Logger``
    constructor parameter receives an instance bound to the *consuming*
    class's own key rather than a single shared instance, and every
    instantiation is logged to that component's file — and ``Events``
    (see ``opendataframework.events``): an ``events: Events`` parameter
    receives the ``Context``'s own instance, and every call of a bound
    function is reported to it as a ``FunctionProtocol`` call.

    Args:
        namespaces: Namespace subclasses to collect registered classes from.
        log_manager: Owns per-component log files. Defaults to a disabled
            ``LogManager`` (writes become no-ops) when omitted.
        events: Receives an event for every call of a bound function.
            Defaults to an ``Events`` with no listeners when omitted.

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
        events: Events | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        self._namespaces = set(namespaces)
        self._instances: dict[type, object] = dict(extra_instances or {})
        self._order: list[type] = []
        self._functions: dict[Callable[..., object], Callable[..., object]] = {}
        self._injected: dict[Callable[..., object], dict[str, object]] = {}
        self._keys: dict[type | Callable[..., object], str] = {}
        self._by_key: dict[str, type | Callable[..., object]] = {}
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._events = events if events is not None else Events(self._log_manager)

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

    @property
    def functions(self) -> dict[Callable[..., object], Callable[..., object]]:
        """Registered function → bound callable mapping, populated after ``resolve()``.

        Returns:
            A shallow copy. Each value calls its key with the managed
            dependencies already filled in, and logs the call — it is the
            same callable injected wherever the function is asked for.
        """
        return dict(self._functions)

    @property
    def keys(self) -> dict[type | Callable[..., object], str]:
        """Registered class or function → its ``<namespace>.<name>`` key.

        Populated after ``resolve()``; see ``opendataframework.namespace.qualified``.

        Returns:
            A shallow copy.
        """
        return dict(self._keys)

    def lookup(self, key: str) -> type | Callable[..., object]:
        """Return the registered class or function addressed by ``key``, in any casing.

        Raises:
            ValueError: If ``key`` is not ``<namespace>.<name>``.
            KeyError: If nothing gathered is registered under ``key``.
        """
        normalized = parse(key)
        if normalized not in self._by_key:
            raise KeyError(key)
        return self._by_key[normalized]

    def injected(self, func: Callable[..., object]) -> dict[str, object]:
        """Return the parameter name → value pairs injected into ``func``.

        Raises:
            KeyError: If ``func`` was not resolved.
        """
        return dict(self._injected[func])

    def resolve(self) -> None:
        """Gather registered classes and functions, sort by dependency order, and create.

        Runs the full resolution pipeline: collect from namespaces →
        topological sort → instantiate each class, and bind each function,
        with injected dependencies. Functions are sorted together with
        classes, since a class may ask for one (see ``dependencies``), but
        only classes appear in ``order``.

        Raises:
            ValueError: If a circular dependency is detected among registered
                classes and functions, or one of them asks for the same
                dependency under more than one parameter.

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
        self._index()
        ordered = self._sort(self.gather() | self.gather_functions())
        self._order = [node for node in ordered if isinstance(node, type)]
        for node in ordered:
            if isinstance(node, type):
                self._instances[node] = self._instantiate(node)
            else:
                self._injected[node] = self._inject(node)
                self._functions[node] = _logged_execute(
                    bind(node, self._injected[node]),
                    self._keys[node],
                    self._log_manager,
                    self._events,
                    FunctionProtocol,
                    "__call__",
                )

    def _index(self) -> None:
        """Give everything gathered its ``<namespace>.<name>`` key.

        Raises:
            ValueError: If an object is registered in more than one of the
                gathered namespaces (e.g. ``namespaces={Api, Component}`` for
                an ``@Api @Component`` class), or two namespaces share a name,
                so a key would not name exactly one object.
        """
        keys: dict[type | Callable[..., object], str] = {}
        by_key: dict[str, type | Callable[..., object]] = {}
        for ns in sorted(self._namespaces, key=lambda ns: ns.__name__):
            for name, obj in ns.items():
                key = qualified(ns, normalize(name))
                if obj in keys:
                    raise ValueError(
                        f"{obj.__name__} is registered as both {keys[obj]!r} and {key!r} — "
                        "gather it from one namespace only, so it has one key"
                    )
                if key in by_key:
                    raise ValueError(
                        f"{key!r} names both {by_key[key].__name__} and {obj.__name__} — "
                        "two gathered namespaces share a name"
                    )
                keys[obj] = key
                by_key[key] = obj
        self._keys = keys
        self._by_key = by_key

    def gather(self) -> set[type]:
        """Collect all classes registered across the configured namespaces.

        Returns:
            Flat set of every class found in ``self._namespaces``. Registered
            functions are left out — see ``gather_functions``.
        """
        classes: set[type] = set()
        for ns in self._namespaces:
            for _, cls in ns.items():
                if isinstance(cls, type):
                    classes.add(cls)
        return classes

    def gather_functions(self) -> set[Callable[..., object]]:
        """Collect all functions registered across the configured namespaces."""
        return {
            func for ns in self._namespaces for _, func in ns.items() if not isinstance(func, type)
        }

    @staticmethod
    def dependencies(cls: type | Callable[..., object]) -> dict[str, type | Callable[..., object]]:
        """Return typed constructor parameters for ``cls``.

        Inspects ``cls.__init__`` — or, for a registered function, the
        function's own signature — and returns only parameters that carry a
        type annotation which is itself a type (i.e. not a string forward
        reference or a generic alias), or one that names a function::

            def __init__(self, load: Annotated[Callable[..., int], load_data]): ...

        The first argument to ``Annotated`` is what a type checker sees; the
        function after it is the dependency.

        Public so other framework code (e.g. topology introspection) can
        derive the same dependency edges without duplicating this logic.

        Args:
            cls: The class, or registered function, to inspect.

        Returns:
            Mapping of parameter name to annotated type, or named function.
            Empty if the signature cannot be inspected or no typed
            parameters exist.
        """
        is_class = isinstance(cls, type)
        try:
            sig = inspect.signature(cls.__init__ if is_class else cls)
        except ValueError, TypeError:
            return {}
        found = {}
        for name, param in sig.parameters.items():
            if is_class and name == "self":
                continue
            dep = _dependency(param.annotation)
            if dep is not None:
                found[name] = dep
        return found

    def _sort(self, classes: set) -> list:
        """Return ``classes`` in topological order (leaves first).

        Uses Kahn's algorithm. Only dependencies that are themselves present
        in ``classes`` are considered — external types are ignored.

        Args:
            classes: The full set of classes, and registered functions, to
                order.

        Returns:
            Classes and functions sorted so every dependency appears before
            its dependents.

        Raises:
            ValueError: If a circular dependency is detected, or one class
                or function asks for the same dependency more than once.
        """
        all_deps = {cls: self.dependencies(cls) for cls in classes}
        registered_deps = {
            cls: {name: dep for name, dep in deps.items() if dep in classes}
            for cls, deps in all_deps.items()
        }
        for cls, deps in registered_deps.items():
            self._require_distinct(cls, deps)
        in_degree = {cls: len(deps) for cls, deps in registered_deps.items()}
        dependents: dict[object, set] = {cls: set() for cls in classes}
        for cls, deps in registered_deps.items():
            for dep in deps.values():
                dependents[dep].add(cls)
        queue = sorted(
            (cls for cls in classes if in_degree[cls] == 0),
            key=lambda c: c.__name__,
        )
        result: list = []
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

    @staticmethod
    def _require_distinct(cls: type | Callable[..., object], deps: dict) -> None:
        """Raise ``ValueError`` if ``cls`` asks for one dependency under several parameters.

        There is a single instance per class (and a single bound callable per
        function), so the parameters would all receive the same object —
        almost always a sign that two separate ones were expected.
        """
        by_dep: dict[object, list[str]] = {}
        for name, dep in deps.items():
            by_dep.setdefault(dep, []).append(name)
        for dep, names in by_dep.items():
            if len(names) > 1:
                listed = ", ".join(repr(name) for name in names)
                raise ValueError(
                    f"{cls.__name__} asks for {dep.__name__} more than once "
                    f"(parameters {listed}) — the Context holds a single "
                    f"{dep.__name__}, so each would receive the same object"
                )

    def _instantiate(self, cls: type) -> object:
        """Instantiate ``cls`` with its dependencies injected from ``self._instances``.

        See ``_supply`` for which constructor parameters are passed.

        Args:
            cls: The class to instantiate.

        Returns:
            A new instance of ``cls`` with resolved dependencies injected.
        """
        supplied = self._supply(cls)
        self._require_readable(cls, supplied)
        instance = cls(**supplied)
        self._log_manager.write(self._keys[cls], "INFO", f"{cls.__name__} resolved")
        return instance

    @staticmethod
    def _require_readable(cls: type, supplied: dict[str, object]) -> None:
        """Raise ``TypeError`` if a required constructor parameter has a string annotation.

        Such a parameter is never injected (see ``_dependency``), so ``cls``
        could not be created anyway — this replaces Python's bare "missing 1
        required positional argument" with the reason.
        """
        try:
            parameters = list(inspect.signature(cls.__init__).parameters.values())[1:]
        except ValueError, TypeError:
            return
        unread = [
            parameter
            for parameter in parameters
            if isinstance(parameter.annotation, str)
            and parameter.default is inspect.Parameter.empty
            and parameter.name not in supplied
        ]
        if unread:
            listed = ", ".join(repr(parameter.name) for parameter in unread)
            raise TypeError(
                f"{cls.__name__}.__init__() is missing {listed} — "
                f"not injected by the Context{string_hint(unread)}"
            )

    def _inject(self, func: Callable[..., object]) -> dict[str, object]:
        """Return the values to inject into ``func``, by parameter name.

        Follows the same rule as ``_instantiate`` — see ``_supply``. Every
        remaining parameter is left for the caller.
        """
        injected = self._supply(func)
        self._log_manager.write(self._keys[func], "INFO", f"{func.__name__} resolved")
        return injected

    def _supply(self, target: type | Callable[..., object]) -> dict[str, object]:
        """Return the dependencies ``target`` asks for, by parameter name.

        A ``dep`` annotated exactly as ``Logger`` is special-cased: instead of
        a shared instance, ``target`` receives a ``Logger`` bound to its own
        key (see ``opendataframework.logger.LogManager.logger_for``). One
        annotated exactly as ``Events`` receives the ``Context``'s ``Events``. A class is
        supplied only if already present in ``self._instances``, and a
        function only if already bound — unregistered ones in the signature
        are silently ignored.
        """
        supplied: dict[str, object] = {}
        for name, dep in self.dependencies(target).items():
            if dep is Logger:
                supplied[name] = self._log_manager.logger_for(self._keys[target])
            elif dep is Events:
                supplied[name] = self._events
            elif dep in self._instances:
                supplied[name] = self._instances[dep]
            elif dep in self._functions:
                supplied[name] = self._functions[dep]
        return supplied


class Lifecycle:
    """Drives the startup and shutdown lifecycle for resolved instances.

    Iterates instances in dependency order on start, and in reverse order on
    stop. Dispatches to the appropriate protocol for each instance. Has no
    knowledge of dependency resolution or instance creation.

    Every stage transition is also logged to the component's own log file via
    ``log_manager`` (see ``opendataframework.logger``), giving every ``Service`` a log
    record with no code changes required, and every protocol call is reported
    to ``events`` (see ``opendataframework.events``).

    Args:
        instances: Class-to-instance mapping produced by ``Resolver``.
        order: Classes in dependency order, as returned by ``Resolver.order``.
        keys: Class → ``<namespace>.<name>`` key, as returned by
            ``Resolver.keys``. Names each class's log file.
        log_manager: Owns per-component log files. Defaults to a disabled
            ``LogManager`` (writes become no-ops) when omitted.
        events: Receives an event for every protocol call. Defaults to an
            ``Events`` with no listeners when omitted.

    Example:
        >>> lifecycle = Lifecycle(instances={...}, order=[...], keys={...})
        >>> lifecycle.on_start()   # services set up and backgrounded
        >>> lifecycle.on_stop()    # services stopped in reverse order
    """

    def __init__(
        self,
        instances: dict[type, object],
        order: list[type],
        keys: dict[type, str],
        log_manager: LogManager | None = None,
        events: Events | None = None,
    ) -> None:
        """See class docstring for ``Args``."""
        self._instances = instances
        self._order = order
        self._keys = keys
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._events = events if events is not None else Events(self._log_manager)
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
        name = self._keys[cls]
        with self._events.notify(name, OnStartProtocol, "on_start"):
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
        name = self._keys[cls]
        with self._events.notify(name, ServiceProtocol, "setup"):
            self._log_manager.write(name, "INFO", "setup() starting")
            instance.setup()
            self._log_manager.write(name, "INFO", "setup() complete")
        # An empty context, so run() is a top-level call rather than a child
        # of whatever call started the service.
        t = threading.Thread(
            target=self._run, args=(cls, instance), daemon=True, context=contextvars.Context()
        )
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
        name = self._keys[cls]
        with self._events.notify(name, ServiceProtocol, "stop"):
            self._log_manager.write(name, "INFO", "stop() called")
            instance.stop()
            self._log_manager.write(name, "INFO", "stop() complete")
        self._running[cls] = False

    def is_running(self, cls: type) -> bool:
        """Return whether ``cls``'s instance is currently started."""
        return self._running.get(cls, False)

    def _run(self, cls: type, instance: ServiceProtocol) -> None:
        """Run ``instance.run()``, logging its start, return, and any exception."""
        name = self._keys[cls]
        with self._events.notify(name, ServiceProtocol, "run"):
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
        name = self._keys[cls]
        with self._events.notify(name, OnStopProtocol, "on_stop"):
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

    def __init__(
        self,
        keys: dict[type, str] | None = None,
        log_manager: LogManager | None = None,
        events: Events | None = None,
    ) -> None:
        """See class docstring; ``log_manager`` defaults to a disabled ``LogManager``.

        ``keys`` maps each class to the ``<namespace>.<name>`` key its log
        lines go under, as returned by ``Resolver.keys``. ``events`` receives
        an event for every ``open_stream()``/``stream()``/``close_stream()``
        call, and defaults to an ``Events`` with no listeners.
        """
        self._keys = keys if keys is not None else {}
        self._log_manager = log_manager if log_manager is not None else LogManager()
        self._events = events if events is not None else Events(self._log_manager)
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
        name = self._keys[cls]
        try:
            if isinstance(instance, OpenStreamProtocol):
                with self._events.notify(name, OpenStreamProtocol, "open_stream"):
                    self._log_manager.write(name, "INFO", "open_stream() called")
                    instance.open_stream()
                    self._log_manager.write(name, "INFO", "open_stream() complete")
            with self._lock:
                self._subscribers[cls] = []
                event = threading.Event()
                self._stop_events[cls] = event
                thread = threading.Thread(
                    target=self._run,
                    args=(cls, instance, event),
                    daemon=True,
                    context=contextvars.Context(),
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
        self._log_manager.write(self._keys[cls], "INFO", "stream stopped")

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
        name = self._keys[cls]
        try:
            with self._events.notify(name, StreamableProtocol, "stream"):
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
                try:
                    with self._events.notify(name, CloseStreamProtocol, "close_stream"):
                        self._log_manager.write(name, "INFO", "close_stream() called")
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

    By default, collects from every built-in namespace: ``Component``,
    ``Repository``, ``Service``, ``Task``, ``Pipeline``, ``Agent``, and
    ``Function``. Pass ``namespaces`` to override — primarily useful for
    testing.

    Args:
        namespaces: Namespace subclasses to collect registered classes from.
            Defaults to all of the built-in ones listed above.
        config: Configuration dict, pre-seeded as ``Config`` into the
            container.
        log_dir: Directory to write per-component ``<namespace>.<name>.log``
            files under.
            ``None`` (the default) disables file logging entirely — see
            ``opendataframework.logger.LogManager``. ``Project.from_config``/``from_dict``
            opt in to a real directory.

    Attributes:
        instances: Class-to-instance mapping, populated after ``open()`` returns.
            Backs ``Context.get(cls)``, the typed lookup by class.

    Every method that takes a string — ``execute``, ``call``, ``start``,
    ``tail_logs`` and the rest — takes a key, ``<namespace>.<name>``
    (``"task.load-job"``, ``"agent.librarian"``), in any casing. A name is
    only unique within its namespace, so the namespace is always part of it;
    ``key(obj)`` returns the key of a class or function you hold.

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
        self._events = Events(self._log_manager)
        self._resolver = Resolver(
            namespaces if namespaces is not None else _DEFAULT_NAMESPACES,
            extra_instances=extra,
            log_manager=self._log_manager,
            events=self._events,
        )
        self._lifecycle: Lifecycle | None = None
        self._stream_manager = StreamManager(log_manager=self._log_manager, events=self._events)
        self._functions: dict[Callable[..., object], Callable[..., object]] = {}

    @property
    def instances(self) -> dict[type, object]:
        """Class-to-instance mapping produced by the resolver.

        Returns:
            A shallow copy of the resolved instances. Mutating the returned
            dict does not affect the context's state.
        """
        return self._resolver.instances

    @property
    def events(self) -> Events:
        """The ``Events`` every protocol call this ``Context`` makes is reported to.

        The same instance an ``events: Events`` constructor parameter
        receives. Usable before ``open()``, so a listener subscribed first
        also sees the startup calls ``open()`` makes. See
        ``opendataframework.events``.

        Example:
            >>> unsubscribe = context.events.subscribe(print, protocol=ServiceProtocol)
            >>> context.open()
            Event(key='service.postgres', protocol=<class '...ServiceProtocol'>, ...)
        """
        return self._events

    @property
    def functions(self) -> dict[Callable[..., object], Callable[..., object]]:
        """Registered ``Function`` → bound callable mapping, populated by ``open()``.

        Kept apart from ``instances``, which holds classes only. Each value
        calls its key with the managed dependencies already filled in — the
        same callable ``get(func)`` returns.

        Returns:
            A shallow copy. Mutating the returned dict does not affect the
            context's state.
        """
        return dict(self._functions)

    @overload
    def get(self, cls: type[T]) -> T: ...
    @overload
    def get(self, cls: Callable[..., R]) -> Callable[..., R]: ...
    def get(self, cls):
        """Return the resolved instance of ``cls``, typed as ``cls``.

        Unlike ``instances[cls]``, the return type is inferred from the
        argument at the call site — ``context.get(Books)`` types as
        ``Books``, no annotation or cast required.

        Given a registered ``Function`` instead of a class, returns that
        function with its managed dependencies already filled in — call it
        with the remaining arguments only.

        Args:
            cls: The registered class, or function, to resolve.

        Raises:
            KeyError: If ``cls`` was not resolved (not registered, or
                ``open()`` has not been called yet).

        Example:
            >>> books = context.get(Books)
            >>> books.all()
            [Book(id=1, title='Dune', author='Frank Herbert')]
            >>> context.get(load_data)("data.csv")  # db injected
            42
        """
        if isinstance(cls, type):
            return cast(T, self._resolver.instances[cls])
        return self._functions[cls]

    def key(self, obj: type | Callable[..., object]) -> str:
        """Return the ``<namespace>.<name>`` key a resolved class or function is addressed by.

        The key every string-taking method here accepts, and the name of
        ``obj``'s log file.

        Raises:
            KeyError: If ``obj`` was not resolved (not registered, or
                ``open()`` has not been called yet).

        Example:
            >>> context.key(DailyAnalytics)
            'pipeline.daily-analytics'
        """
        return self._resolver.keys[obj]

    def open(self) -> None:
        """Resolve all registered classes and drive their startup lifecycle.

        Runs ``Resolver.resolve()`` (which also binds every ``Function``,
        logged), wraps every ``Task``/``Pipeline`` instance's ``execute()``
        and every ``Agent`` instance's ``invoke()`` for automatic logging,
        then constructs a
        ``Lifecycle`` from the result and calls ``Lifecycle.on_start()``.

        Raises:
            ValueError: If a circular dependency is detected, or a gathered
                object would not have exactly one key (see
                ``Resolver._index``).
            TypeError: If a registered function, or a method the ``Context``
                calls, is async — see ``_require_sync``.
        """
        self._require_sync()
        self._resolver.resolve()
        keys = self._resolver.keys
        self._instrument(keys)
        self._functions = self._resolver.functions
        self._stream_manager = StreamManager(keys, self._log_manager, self._events)
        self._lifecycle = Lifecycle(
            self._resolver.instances, self._resolver.order, keys, self._log_manager, self._events
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

    def start(self, key: str) -> None:
        """Start a single resolved ``Service`` by key. No-op if already running.

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"service.postgres"``), in any casing.

        Raises:
            KeyError: If no resolved instance matches ``key``.
            TypeError: If the matched instance is not a ``Service``.
        """
        cls, instance = self._resolved(key)
        if not isinstance(instance, ServiceProtocol):
            raise TypeError(f"{key} is not a Service")
        self._lifecycle.start_one(cls)

    def stop(self, key: str) -> None:
        """Stop a single running ``Service`` by key. No-op if not running.

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"service.postgres"``), in any casing.

        Raises:
            KeyError: If no resolved instance matches ``key``.
            TypeError: If the matched instance is not a ``Service``.
        """
        cls, instance = self._resolved(key)
        if not isinstance(instance, ServiceProtocol):
            raise TypeError(f"{key} is not a Service")
        self._lifecycle.stop_one(cls)

    def is_running(self, key: str) -> bool:
        """Return whether the ``Service`` matching ``key`` is currently started.

        Raises:
            KeyError: If no resolved instance matches ``key``.
        """
        cls, instance = self._resolved(key)
        return isinstance(instance, ServiceProtocol) and self._lifecycle.is_running(cls)

    def start_stream(self, key: str) -> None:
        """Start a single resolved ``StreamableProtocol`` repository's stream by key.

        Mirrors ``start()`` for services: spawns a background thread that
        drives ``instance.stream()`` so it keeps running independent of any
        one viewer's connection. No-op if already streaming.

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"repository.webcam"``), in any casing.

        Raises:
            KeyError: If no resolved instance matches ``key``.
            TypeError: If the matched instance is not ``StreamableProtocol``.
        """
        cls, instance = self._resolved(key)
        if not isinstance(instance, StreamableProtocol):
            raise TypeError(f"{key} is not streamable")
        self._stream_manager.start(cls, instance)

    def stop_stream(self, key: str) -> None:
        """Stop a single running repository stream by key. No-op if not streaming.

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"repository.webcam"``), in any casing.

        Raises:
            KeyError: If no resolved instance matches ``key``.
            TypeError: If the matched instance is not ``StreamableProtocol``.
        """
        cls, instance = self._resolved(key)
        if not isinstance(instance, StreamableProtocol):
            raise TypeError(f"{key} is not streamable")
        self._stream_manager.stop(cls)

    def is_streaming(self, key: str) -> bool:
        """Return whether the repository stream matching ``key`` is currently running.

        Raises:
            KeyError: If no resolved instance matches ``key``.
        """
        cls, instance = self._resolved(key)
        return isinstance(instance, StreamableProtocol) and self._stream_manager.is_streaming(cls)

    def iter_stream(self, key: str) -> Iterator[object]:
        """Attach as one subscriber to a repository's already-running stream.

        Does not start or stop the stream itself — see ``start_stream()``.
        Iterating stops (and detaches the subscription) when the stream is
        stopped, or when the caller stops iterating (e.g. a client
        disconnect closes this generator).

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"repository.webcam"``), in any casing.

        Raises:
            KeyError: If no resolved instance matches ``key``, or if it
                isn't currently streaming.
        """
        cls, _ = self._resolved(key)
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

    def execute(self, key: str) -> object:
        """Execute a single resolved ``Task`` or ``Pipeline`` by key.

        Args:
            key: The ``<namespace>.<name>`` key of a resolved instance
                (e.g. ``"pipeline.daily-analytics"``), in any casing.

        Returns:
            Whatever ``execute()`` returns.

        Raises:
            KeyError: If no resolved instance matches ``key``.
            TypeError: If the matched instance is not a ``Task`` or ``Pipeline``.
        """
        cls, instance = self._resolved(key)
        executable = set(dict(Task.items()).values()) | set(dict(Pipeline.items()).values())
        if cls not in executable:
            raise TypeError(f"{key} is not a Task or Pipeline")
        return instance.execute()

    def call(self, key: str, /, **kwargs: object) -> object:
        """Call a resolved ``Function`` or ``Agent`` by key, with arguments.

        The counterpart of ``execute()`` for what — unlike a ``Task`` — takes
        arguments.

        For a ``Function``, parameters whose type the ``Context`` manages are
        filled in and ``kwargs`` supplies the rest; an argument passed
        explicitly wins over the injected value. For an ``Agent``, whose
        dependencies were already injected through its constructor,
        ``kwargs`` is passed to its ``invoke()`` as is.

        Args:
            key: The ``<namespace>.<name>`` key, in any casing
                (``"function.load-data"``, ``"function.load_data"``,
                ``"Agent.Librarian"``). Positional-only, so a parameter that
                is itself called ``key`` can still be passed.
            **kwargs: The function's remaining arguments, or the agent's
                ``invoke()`` arguments.

        Returns:
            Whatever the function, or the agent's ``invoke()``, returns.

        Raises:
            ValueError: If ``key`` is not ``<namespace>.<name>``.
            KeyError: If no resolved function or agent matches ``key``.
            TypeError: If a required argument is neither managed by the
                ``Context`` nor supplied.

        Example:
            >>> context.call("function.load-data", path="data.csv")  # db injected
            42
            >>> context.call("agent.librarian", question="Anything by Herbert?")
            'Dune, by Frank Herbert'
        """
        target = self._resolver.lookup(key)
        if target in self._functions:
            return self._functions[target](**kwargs)
        if target in set(dict(Agent.items()).values()) and target in self._resolver.instances:
            return self._resolver.instances[target].invoke(**kwargs)
        raise KeyError(key)

    def parameters(self, func: type | Callable[..., object]) -> dict[str, inspect.Parameter]:
        """Return the parameters a caller must supply to ``call()`` a function or agent.

        For a ``Function``, that is its signature minus the parameters the
        ``Context`` injects. For an ``Agent`` class, it is the signature of
        its ``invoke()``. Either way, it is what a caller building a form or
        a tool schema needs to ask for.

        Args:
            func: The registered function, or agent class.

        Returns:
            Parameter name → ``inspect.Parameter``, in signature order.

        Raises:
            KeyError: If ``func`` was not resolved, or is a resolved class
                that is not an ``Agent``.
        """
        if isinstance(func, type):
            if func not in set(dict(Agent.items()).values()):
                raise KeyError(func)
            return dict(inspect.signature(self._resolver.instances[func].invoke).parameters)
        injected = self._resolver.injected(func)
        return {
            name: parameter
            for name, parameter in inspect.signature(func).parameters.items()
            if name not in injected
        }

    def _resolved(self, key: str) -> tuple[type, object]:
        """Look up a resolved ``(cls, instance)`` pair by ``<namespace>.<name>`` key.

        Raises:
            ValueError: If ``key`` is not ``<namespace>.<name>``.
            KeyError: If no resolved instance matches ``key``.
        """
        cls = self._resolver.lookup(key)
        instances = self._resolver.instances
        if cls not in instances:
            raise KeyError(key)
        return cls, instances[cls]

    def tail_logs(self, key: str, lines: int = 300) -> list[dict]:
        """Return the last ``lines`` log entries for a resolved class or function.

        Args:
            key: Its ``<namespace>.<name>`` key (e.g. ``"service.postgres"``),
                in any casing.
            lines: Maximum number of most-recent entries to return.

        Returns:
            A list of ``{"ts", "level", "message"}`` dicts, oldest first.
            Empty if file logging is disabled or nothing was logged.

        Raises:
            ValueError: If ``key`` is not ``<namespace>.<name>``.
        """
        return self._log_manager.tail(parse(key), lines)

    def _require_sync(self) -> None:
        """Raise ``TypeError`` if anything the ``Context`` would call is async.

        The ``Context`` calls and never awaits, so an ``async def`` would
        hand back a coroutine nobody runs — an ``on_start()`` that silently
        does nothing, an ``execute()`` logged as complete before it began.
        Checked before anything is created. Only what the ``Context`` itself
        calls is looked at — a registered function, and per class the
        lifecycle, execution and stream methods that apply to it — so an
        unrelated ``async def`` on a component is left alone.

        Raises:
            TypeError: Naming the first async function or method found.
        """
        executable = set(dict(Task.items()).values()) | set(dict(Pipeline.items()).values())
        agents = set(dict(Agent.items()).values())
        repositories = set(dict(Repository.items()).values())
        found: list[str] = [
            f"{func.__name__}()" for func in self._resolver.gather_functions() if _is_async(func)
        ]
        for cls in self._resolver.gather():
            methods = list(_LIFECYCLE_HOOKS)
            if all(callable(getattr(cls, method, None)) for method in _SERVICE_METHODS):
                methods.extend(_SERVICE_METHODS)
            if cls in executable:
                methods.append("execute")
            if cls in agents:
                methods.append("invoke")
            if cls in repositories:
                methods.extend(_STREAM_METHODS)
            found.extend(
                f"{cls.__name__}.{method}()"
                for method in methods
                if _is_async(getattr(cls, method, None))
            )
        if found:
            raise TypeError(
                f"{min(found)} is async — the Context does not await, so async is not "
                "supported yet. Make it synchronous, or keep it out of the Context and "
                "call it yourself"
            )

    def _instrument(self, keys: dict[type, str]) -> None:
        """Wrap every resolved ``Task``/``Pipeline``'s ``execute()`` and ``Agent``'s ``invoke()``.

        Logs start, completion (with duration), and any exception to that
        component's own log file — with no code changes required in the
        classes themselves — and reports each call to ``events`` as a
        ``TaskProtocol``, ``PipelineProtocol`` or ``AgentProtocol`` call. The
        wrapper is set on the instance, so a call made directly (from a
        ``Pipeline``, say) is logged the same as one made through the
        ``Context``.
        """
        tasks = set(dict(Task.items()).values())
        pipelines = set(dict(Pipeline.items()).values())
        agents = set(dict(Agent.items()).values())
        for cls, instance in self._resolver.instances.items():
            if cls in tasks | pipelines and hasattr(instance, "execute"):
                protocol = PipelineProtocol if cls in pipelines else TaskProtocol
                instance.execute = _logged_execute(
                    instance.execute,
                    keys[cls],
                    self._log_manager,
                    self._events,
                    protocol,
                    "execute",
                )
            if cls in agents:
                instance.invoke = _logged_execute(
                    instance.invoke,
                    keys[cls],
                    self._log_manager,
                    self._events,
                    AgentProtocol,
                    "invoke",
                )

    def __enter__(self) -> Context:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
