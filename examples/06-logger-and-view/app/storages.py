from opendataframework import Component


@Component
class Store:
    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._next_id = 1

    def insert(self, row: dict) -> int:
        row_id = self._next_id
        self._next_id += 1
        self._rows.append({**row, "id": row_id})
        return row_id

    def all(self) -> list[dict]:
        return list(self._rows)
