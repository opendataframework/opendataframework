"""Lets each examples/<n>-<name>/ test package `import app` safely.

Every example's package is conventionally named `app` (matching `odf run`'s
`--app app` default). In one pytest process, whichever `app` package a test
file imports last "wins" in `sys.modules` for anyone importing it later —
including at *execution* time (after collection has finished for the whole
session). A naive purge-and-never-restore approach fixes collection-time
correctness but forces a fresh, side-effecting re-import of whichever `app`
package a later test needs.

`use_app_from` remembers whatever was cached before the *first* example
touched `sys.modules`, and `restore` (called once collection finishes,
before any test runs) puts it back exactly — so execution starts from the
same state it would have without examples/ tests in the run at all.
"""

import sys
from pathlib import Path

_original_app_modules: dict[str, object] | None = None


def _app_modules() -> dict[str, object]:
    return {
        name: mod for name, mod in sys.modules.items() if name == "app" or name.startswith("app.")
    }


def use_app_from(example_dir: Path) -> None:
    global _original_app_modules
    if _original_app_modules is None:
        _original_app_modules = _app_modules()

    for name in _app_modules():
        del sys.modules[name]

    path = str(example_dir)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


def restore() -> None:
    global _original_app_modules

    for name in _app_modules():
        del sys.modules[name]
    if _original_app_modules:
        sys.modules.update(_original_app_modules)
    _original_app_modules = None

    examples_dir = Path(__file__).resolve().parents[2] / "examples"
    prefix = str(examples_dir) + "/"
    sys.path[:] = [p for p in sys.path if not p.startswith(prefix)]
