"""Resets opendataframework's process-global Namespace registries between tests.

`Entity`/`Component`/`Repository`/`Service`/`Task`/`Pipeline`/`Layer` (and
`Layer`'s own built-in subclasses) are `opendataframework.namespace.Namespace`
subclasses, each keeping a shared name -> class registry for its whole
subclass. Re-registering a name now raises (0.2.0) instead of silently
overwriting, so a test that decorates a locally-defined class with a generic
name (e.g. `class Postgres: ...` via `@Service`) as a throwaway fixture would
collide with the next test doing the same, since both register into the same
process-wide dict within one pytest session. This snapshots each registry
before every test and restores it after, so no test's registrations leak into
another's — along with what `Subscriber` and `Publisher` record per target.
"""

import pytest

from opendataframework.namespace import Namespace


def _namespace_classes() -> list[type]:
    seen: list[type] = []
    stack = list(Namespace.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in seen:
            seen.append(cls)
            stack.extend(cls.__subclasses__())
    return seen


def _declarations(cls: type) -> dict | None:
    """Return the per-target declarations a namespace keeps (``Subscriber``,
    ``Publisher``), or ``None`` if it keeps none of its own."""
    return cls.__dict__.get("_declared")


@pytest.fixture(autouse=True)
def _reset_namespaces():
    snapshot = {cls: dict(cls._namespace) for cls in _namespace_classes()}
    declared = {
        cls: dict(_declarations(cls))
        for cls in _namespace_classes()
        if _declarations(cls) is not None
    }
    yield
    for cls in _namespace_classes():
        cls._namespace.clear()
        cls._namespace.update(snapshot.get(cls, {}))
        if (declarations := _declarations(cls)) is not None:
            declarations.clear()
            declarations.update(declared.get(cls, {}))
