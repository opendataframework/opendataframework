from opendataframework import Component


@Component
class ItemStore:
    """Plain in-memory buffer the two Tasks share — not itself a Task/Pipeline."""

    def __init__(self) -> None:
        self.raw: list[str] = []
        self.transformed: list[str] = []
