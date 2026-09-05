"""Points `import app` at examples/01-entity-repository/app for this
directory's collection. See `tests/examples/_isolation.py`."""

from pathlib import Path

from examples._isolation import use_app_from

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "01-entity-repository"

use_app_from(EXAMPLE_DIR)
