from app.tasks import ExtractItems, TransformItems
from opendataframework import Pipeline


@Pipeline
class SetupPipeline:
    """Coordinates the two Tasks — it does not transform data itself."""

    def __init__(self, extract: ExtractItems, transform: TransformItems) -> None:
        self.extract = extract
        self.transform = transform

    def execute(self) -> list[str]:
        self.extract.execute()
        return self.transform.execute()
