import pytest
from app.entities import Book
from app.repositories import Books
from app.storages import SQLite

from opendataframework.config import Config

# Deliberately builds SQLite/Books directly rather than going through
# Project/Context: @Component-family decorators register into a namespace
# that's global for the whole pytest process, so a real Project.start() here
# would resolve every class from every example's `app` package imported
# anywhere else in the same run, not just this one.


@pytest.fixture
def books(tmp_path) -> Books:
    config = Config({"sqlite": {"path": str(tmp_path / "test.db")}})
    sqlite = SQLite(config)
    yield Books(sqlite)
    sqlite.on_stop()


def test_books_repository_full_crud_cycle(books):
    assert books.all() == []

    books.save(Book(id=None, title="Dune", author="Frank Herbert"))
    saved = books.all()
    assert len(saved) == 1
    assert saved[0].title == "Dune"

    saved[0].author = "F. Herbert"
    books.save(saved[0])
    assert books.get(saved[0].id).author == "F. Herbert"

    books.delete(saved[0].id)
    assert books.all() == []
