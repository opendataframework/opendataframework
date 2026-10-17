from opendataframework import Component


@Component
class Inventory:
    def __init__(self) -> None:
        self.stock: dict[str, int] = {"apple": 2, "banana": 12}
