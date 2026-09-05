"""Points `import app` at examples/04-task-and-pipeline/app for this
directory's collection. See `tests/examples/_isolation.py`."""

from pathlib import Path

from examples._isolation import use_app_from

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "04-task-and-pipeline"

use_app_from(EXAMPLE_DIR)
