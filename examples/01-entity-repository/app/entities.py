from dataclasses import dataclass

from opendataframework import Entity


@Entity
@dataclass
class Book:
    id: int | None
    title: str
    author: str
