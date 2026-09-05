"""Points `import app` at examples/05-layer/app for this directory's
collection. See `tests/examples/_isolation.py`."""

from pathlib import Path

from examples._isolation import use_app_from

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "05-layer"

use_app_from(EXAMPLE_DIR)
