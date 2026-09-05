import pytest
from app.components import Cache, Database

from opendataframework.config import Config

# Deliberately builds Database/Cache directly rather than going through
# Project/Context: @Component registers into a namespace that's global for
# the whole pytest process, so a real Project.start() here would try to
# resolve every Component from every example/demo app imported anywhere else
# in the same run. See tests/examples/entity_repository/test_books.py for
# the same pattern.


@pytest.fixture
def database() -> Database:
    return Database(Config({"database": {"dsn": "sqlite:///test.db"}}))


def test_database_reads_dsn_from_config(database):
    assert database.dsn == "sqlite:///test.db"


def test_database_falls_back_to_default_dsn():
    database = Database(Config({}))
    assert database.dsn == "sqlite:///app.db"


def test_cache_get_delegates_to_database_and_memoizes(database):
    cache = Cache(database)

    first = cache.get("user:1")

    assert first == database.query("user:1")
    assert cache.get("user:1") == first
    assert cache._store == {"user:1": first}


def test_cache_on_stop_clears_the_store(database):
    cache = Cache(database)
    cache.get("user:1")

    cache.on_stop()

    assert cache._store == {}
