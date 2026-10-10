from collections.abc import Callable
from typing import Annotated

from app.functions import low_stock
from opendataframework import Task


@Task
class Reorder:
    def __init__(self, find_shortages: Annotated[Callable[..., list[str]], low_stock]) -> None:
        self.find_shortages = find_shortages

    def execute(self) -> list[str]:
        return self.find_shortages(threshold=15)
