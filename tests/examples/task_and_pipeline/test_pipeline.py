from app.components import ItemStore
from app.pipelines import SetupPipeline
from app.tasks import ExtractItems, TransformItems

# Deliberately builds Tasks/Pipeline directly rather than going through
# Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): registration is global
# for the whole pytest process.


def test_extract_populates_store_raw():
    store = ItemStore()

    result = ExtractItems(store).execute()

    assert result == ["apple", "banana", "cherry"]
    assert store.raw == result


def test_transform_uppercases_store_raw():
    store = ItemStore()
    store.raw = ["apple", "banana"]

    result = TransformItems(store).execute()

    assert result == ["APPLE", "BANANA"]
    assert store.transformed == result


def test_pipeline_runs_extract_then_transform():
    store = ItemStore()
    pipeline = SetupPipeline(ExtractItems(store), TransformItems(store))

    result = pipeline.execute()

    assert result == ["APPLE", "BANANA", "CHERRY"]
    assert store.raw == ["apple", "banana", "cherry"]
