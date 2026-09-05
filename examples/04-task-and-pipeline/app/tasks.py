from app.components import ItemStore
from opendataframework import Task


@Task
class ExtractItems:
    def __init__(self, store: ItemStore) -> None:
        self.store = store

    def execute(self) -> list[str]:
        self.store.raw = ["apple", "banana", "cherry"]
        print(f"ExtractItems.execute    -> {self.store.raw}")
        return self.store.raw


@Task
class TransformItems:
    def __init__(self, store: ItemStore) -> None:
        self.store = store

    def execute(self) -> list[str]:
        self.store.transformed = [item.upper() for item in self.store.raw]
        print(f"TransformItems.execute  -> {self.store.transformed}")
        return self.store.transformed
