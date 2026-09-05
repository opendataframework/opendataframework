from examples._isolation import restore


def pytest_collection_finish(session) -> None:
    """Runs once collection finishes for the whole session, before any test
    executes. See `_isolation.py` for why this needs to be a full restore
    rather than a one-way purge."""
    restore()
