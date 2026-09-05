"""Config: same app code, different config paths per environment.

Greeter's behavior is entirely driven by config — nothing in app/ changes
between environments. Project.from_config takes a directory here: every
*.toml file inside it is loaded and deep-merged, so config/dev/ and
config/prod/ are each free to split settings across multiple files. There's
no environment flag anywhere in the framework — the path passed to
from_config *is* the environment. Run from this directory: `python main.py`.
"""

from app.components import Greeter

from opendataframework import Project

for env in ("dev", "prod"):
    project = Project.from_config(f"config/{env}")
    project.start()

    greeter = project.context.instances[Greeter]
    print(f"[{env}] {greeter.greet()}")

    project.stop()
