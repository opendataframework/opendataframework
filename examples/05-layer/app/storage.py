from opendataframework import Component, Storage


@Storage
@Component
class Warehouse:
    def __init__(self) -> None:
        self.items: list[str] = []

    def save(self, item: str) -> None:
        self.items.append(item)
