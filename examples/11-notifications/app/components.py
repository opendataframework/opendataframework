from opendataframework import Component


@Component
class Inbox:
    """A stand-in for the vendor tools — a café POS, a messenger — orders arrive from."""

    def __init__(self) -> None:
        self.pending: list[tuple[str, str, int]] = []

    def on_start(self) -> None:
        self.pending = [("Le Petit", "baguette", 2), ("Millers Ltd", "sourdough", 12)]
