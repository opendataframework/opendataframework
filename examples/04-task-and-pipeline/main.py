"""Task + Pipeline: composing bounded units of work into an ordered workflow.

ExtractItems and TransformItems are independent @Task steps sharing state
through an ItemStore @Component; SetupPipeline depends on both and calls
them in order — the Pipeline coordinates, it doesn't do the work itself.
Run from this directory: `python main.py`.
"""

from app.pipelines import SetupPipeline

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

result = project.context.get(SetupPipeline).execute()
print(f"\nPipeline result: {result}")

project.stop()
