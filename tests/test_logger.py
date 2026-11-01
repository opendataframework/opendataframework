import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest

from opendataframework import logger as logger_module
from opendataframework.logger import Logger, LogManager, render

# --- disabled by default -------------------------------------------------------


def test_write_is_noop_without_log_dir(tmp_path):
    manager = LogManager()
    manager.write("Thing", "INFO", "hello")
    assert manager.tail("Thing") == []
    assert list(tmp_path.iterdir()) == []


def test_tail_empty_without_log_dir():
    assert LogManager().tail("Thing") == []


# --- file writing ---------------------------------------------------------------


def test_write_creates_one_file_per_component(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("Thing", "INFO", "hello")
    manager.write("OtherThing", "INFO", "world")

    assert (tmp_path / "thing.jsonl").exists()
    assert (tmp_path / "other-thing.jsonl").exists()


def test_write_appends_multiple_lines(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("Thing", "INFO", "first")
    manager.write("Thing", "INFO", "second")

    entries = manager.tail("Thing")
    assert [e["message"] for e in entries] == ["first", "second"]


def test_tail_limits_to_last_n_lines(tmp_path):
    manager = LogManager(tmp_path)
    for i in range(5):
        manager.write("Thing", "INFO", f"line {i}")

    entries = manager.tail("Thing", lines=2)
    assert [e["message"] for e in entries] == ["line 3", "line 4"]


def test_tail_parses_timestamp_and_level(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("Thing", "ERROR", "boom")

    entry = manager.tail("Thing")[0]
    assert entry["level"] == "ERROR"
    assert entry["message"] == "boom"
    assert entry["ts"] is not None


def test_tail_unknown_component_returns_empty(tmp_path):
    manager = LogManager(tmp_path)
    assert manager.tail("Nonexistent") == []


def test_close_allows_reopening(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("Thing", "INFO", "first")
    manager.close()
    manager.write("Thing", "INFO", "second")

    entries = manager.tail("Thing")
    assert [e["message"] for e in entries] == ["first", "second"]


# --- Logger handle --------------------------------------------------------------


def test_logger_for_binds_component_name(tmp_path):
    manager = LogManager(tmp_path)
    logger = manager.logger_for("Thing")
    assert isinstance(logger, Logger)

    logger.info("hello")
    logger.error("oops")

    entries = manager.tail("Thing")
    assert (entries[0]["key"], entries[0]["level"], entries[0]["message"]) == (
        "Thing",
        "INFO",
        "hello",
    )
    assert entries[1]["level"] == "ERROR"


def test_logger_levels_are_recorded(tmp_path):
    manager = LogManager(tmp_path, {"level": "DEBUG"})
    logger = manager.logger_for("Thing")
    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")

    levels = [e["level"] for e in manager.tail("Thing")]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]


# --- level thresholds -----------------------------------------------------------


def messages(manager: LogManager, component: str) -> list[str]:
    """Return the messages written for ``component``."""
    return [e["message"] for e in manager.tail(component)]


def test_default_threshold_is_info(tmp_path):
    manager = LogManager(tmp_path)
    logger = manager.logger_for("task.load")
    logger.debug("d")
    logger.info("i")
    assert messages(manager, "task.load") == ["i"]


def test_top_level_sets_the_default(tmp_path):
    manager = LogManager(tmp_path, {"level": "warning"})  # any casing
    manager.write("task.load", "INFO", "i")
    manager.write("task.load", "WARNING", "w")
    assert messages(manager, "task.load") == ["w"]


def test_most_specific_setting_wins():
    manager = LogManager(
        config={
            "level": "ERROR",
            "events": "WARNING",
            "notifications": "INFO",
            "task": {"level": "INFO", "take-orders": "DEBUG"},
        }
    )
    assert manager.threshold("task.take-orders", "events") == 10  # component
    assert manager.threshold("task.load", "events") == 20  # namespace
    assert manager.threshold("service.db", "events") == 30  # source
    assert manager.threshold("service.db", "notifications") == 20  # source
    assert manager.threshold("service.db") == 40  # default


def test_source_level_applies_only_to_its_own_lines(tmp_path):
    manager = LogManager(tmp_path, {"events": "ERROR"})
    manager.write("task.load", "INFO", "call line", source="events")
    manager.write("task.load", "INFO", "logger line")
    assert messages(manager, "task.load") == ["logger line"]


def test_level_names_are_validated_on_construction():
    with pytest.raises(ValueError, match="task.load = 'LOUD'"):
        LogManager(config={"task": {"load": "LOUD"}})
    with pytest.raises(ValueError, match="level = 10"):
        LogManager(config={"level": 10})


def test_a_namespace_needs_a_table():
    with pytest.raises(ValueError, match="task.level = 'DEBUG'"):
        LogManager(config={"task": "DEBUG"})


def test_validate_rejects_an_unknown_namespace():
    manager = LogManager(config={"tsak": {"level": "DEBUG"}})
    with pytest.raises(ValueError, match="unknown key 'tsak'.*task"):
        manager.validate({"task"}, ["task.load"])


def test_validate_rejects_an_unknown_component():
    manager = LogManager(config={"task": {"lod": "DEBUG"}})
    with pytest.raises(ValueError, match=r"\[project.logging.task\] has unknown key 'lod'.*load"):
        manager.validate({"task"}, ["task.load"])


def test_validate_accepts_known_keys():
    manager = LogManager(config={"level": "INFO", "task": {"level": "INFO", "load": "DEBUG"}})
    manager.validate({"task"}, ["task.load"])


def test_context_open_rejects_a_component_typo(tmp_path):
    from opendataframework.context import Context
    from opendataframework.namespace import Namespace

    class Scope(Namespace): ...

    @Scope
    class Load: ...

    ctx = Context(namespaces={Scope}, log_dir=tmp_path, log_config={"scope": {"lod": "DEBUG"}})
    with pytest.raises(ValueError, match="unknown key 'lod'.*load"):
        ctx.open()


def test_context_component_level_applies_to_its_logger(tmp_path):
    from opendataframework.context import Context
    from opendataframework.namespace import Namespace

    class Scope(Namespace): ...

    @Scope
    class Load:
        def __init__(self, logger: Logger) -> None:
            logger.debug("constructed")

    @Scope
    class Other:
        def __init__(self, logger: Logger) -> None:
            logger.debug("constructed")

    levels = {"scope": {"load": "DEBUG"}}
    with Context(namespaces={Scope}, log_dir=tmp_path, log_config=levels) as ctx:
        assert "constructed" in [e["message"] for e in ctx.tail_logs("scope.load")]
        assert "constructed" not in [e["message"] for e in ctx.tail_logs("scope.other")]


# --- record format -------------------------------------------------------------


def test_json_record_has_the_fixed_fields(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("analytics.daily-report", "INFO", "hello")

    line = (tmp_path / "analytics.daily-report.jsonl").read_text()
    record = json.loads(line)
    assert record.keys() == {"ts", "level", "key", "namespace", "name", "source", "message"}
    assert record["key"] == "analytics.daily-report"
    assert (record["namespace"], record["name"]) == ("analytics", "daily-report")
    assert record["source"] is None
    assert datetime.fromisoformat(record["ts"]).tzinfo is not None
    assert manager.tail("analytics.daily-report") == [record]


def test_extra_is_top_level_and_fields_are_nested(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("task.load", "INFO", "x", source="events", extra={"call": "c1"}, fields={"n": 1})
    (record,) = manager.tail("task.load")
    assert (record["source"], record["call"], record["fields"]) == ("events", "c1", {"n": 1})


def test_logger_keywords_become_fields(tmp_path):
    manager = LogManager(tmp_path)
    logger = manager.logger_for("task.load")
    logger.info("order taken", order_id=7, message="a field named message")
    logger.info("no fields")

    with_fields, without = manager.tail("task.load")
    assert with_fields["message"] == "order taken"
    assert with_fields["fields"] == {"order_id": 7, "message": "a field named message"}
    assert "fields" not in without


def test_unserializable_field_is_written_as_str(tmp_path):
    manager = LogManager(tmp_path)
    manager.logger_for("task.load").info("saved", path=Path("/tmp/x"))
    assert manager.tail("task.load")[0]["fields"] == {"path": "/tmp/x"}


@pytest.mark.parametrize("fmt", ["json", "text"])
def test_newline_in_a_message_stays_one_record(tmp_path, fmt):
    manager = LogManager(tmp_path, {"format": fmt})
    manager.write("task.load", "INFO", "first\nsecond \\n literal")
    manager.write("task.load", "INFO", "next")
    messages = [r["message"] for r in manager.tail("task.load")]
    assert messages == ["first\nsecond \\n literal", "next"]


def test_malformed_json_line_comes_back_raw(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("task.load", "INFO", "ok")
    with open(tmp_path / "task.load.jsonl", "a") as f:
        f.write('{"ts": "2026-10-31T10:00\n')
    assert manager.tail("task.load")[-1] == {
        "ts": None,
        "level": "INFO",
        "message": '{"ts": "2026-10-31T10:00',
    }


def test_text_format_writes_rendered_lines_to_a_log_file(tmp_path):
    manager = LogManager(tmp_path, {"format": "TEXT"})
    manager.logger_for("task.load").warning("slow", ms=900)

    line = (tmp_path / "task.load.log").read_text()
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} WARNING  slow ms=900\n$", line)
    (entry,) = manager.tail("task.load")
    assert (entry["level"], entry["message"]) == ("WARNING", "slow ms=900")


def test_render_writes_full_ids():
    base = {"ts": "2026-10-31T10:00:00.123+01:00", "level": "INFO", "message": "m"}
    event = render({**base, "call": "a" * 32, "parent": None})
    notification = render({**base, "parent": "b" * 32})
    assert event == f"2026-10-31 10:00:00.123 INFO     m [call={'a' * 32} parent=-]"
    assert notification.endswith(f"m [parent={'b' * 32}]")


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="format = 'xml'"):
        LogManager(config={"format": "xml"})


# --- rotation ------------------------------------------------------------------


def record_size(manager: LogManager, message: str) -> int:
    """Return how many bytes one record with ``message`` takes, by writing it to a scratch key."""
    manager.write("scratch.size", "INFO", message)
    path = manager._path("scratch.size")
    size = path.stat().st_size
    manager._files.pop("scratch.size").close()
    path.unlink()
    return size


def test_no_rotation_by_default(tmp_path):
    manager = LogManager(tmp_path)
    for i in range(200):
        manager.write("task.load", "INFO", f"line {i:03}")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["task.load.jsonl"]


def test_rotates_before_a_record_would_pass_max_bytes(tmp_path):
    probe = LogManager(tmp_path / "probe")
    size = record_size(probe, "line 000")
    manager = LogManager(tmp_path / "logs", {"max-bytes": size * 3 + 1})
    for i in range(7):
        manager.write("task.load", "INFO", f"line {i:03}")

    def messages(name: str) -> list[str]:
        lines = (tmp_path / "logs" / name).read_text().splitlines()
        return [json.loads(line)["message"] for line in lines]

    assert messages("task.load.2.jsonl") == ["line 000", "line 001", "line 002"]
    assert messages("task.load.1.jsonl") == ["line 003", "line 004", "line 005"]
    assert messages("task.load.jsonl") == ["line 006"]


def test_keeps_at_most_backups_files(tmp_path):
    manager = LogManager(tmp_path, {"max-bytes": 1, "backups": 2})
    for i in range(6):
        manager.write("task.load", "INFO", f"line {i}")
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "task.load.1.jsonl",
        "task.load.2.jsonl",
        "task.load.jsonl",
    ]
    assert [e["message"] for e in manager.tail("task.load")] == ["line 3", "line 4", "line 5"]


def test_a_record_larger_than_max_bytes_is_still_written_whole(tmp_path):
    manager = LogManager(tmp_path, {"max-bytes": 10})
    manager.write("task.load", "INFO", "x" * 100)
    assert manager.tail("task.load")[0]["message"] == "x" * 100
    assert not (tmp_path / "task.load.1.jsonl").exists()


def test_rotation_carries_on_from_an_existing_file(tmp_path):
    LogManager(tmp_path).write("task.load", "INFO", "x" * 50)
    manager = LogManager(tmp_path, {"max-bytes": 60})
    manager.write("task.load", "INFO", "after restart")
    assert (tmp_path / "task.load.1.jsonl").exists()
    assert [e["message"] for e in manager.tail("task.load")] == ["x" * 50, "after restart"]


def test_tail_reads_across_a_rotation_boundary(tmp_path):
    manager = LogManager(tmp_path, {"max-bytes": 1, "backups": 5})
    for i in range(4):
        manager.write("task.load", "INFO", f"line {i}")
    assert [e["message"] for e in manager.tail("task.load", lines=3)] == [
        "line 1",
        "line 2",
        "line 3",
    ]
    assert manager.tail("task.load", lines=0) == []


def test_text_format_rotates_too(tmp_path):
    manager = LogManager(tmp_path, {"format": "text", "max-bytes": 1})
    manager.write("task.load", "INFO", "first")
    manager.write("task.load", "INFO", "second")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["task.load.1.log", "task.load.log"]
    assert [e["message"] for e in manager.tail("task.load")] == ["first", "second"]


def test_tail_of_a_large_file_reads_only_its_end(tmp_path, monkeypatch):
    path = tmp_path / "task.load.jsonl"
    with path.open("w") as f:
        for i in range(20_000):
            f.write(json.dumps({"ts": "t", "level": "INFO", "message": f"line {i}"}) + "\n")
    read: list[int] = []
    original = logger_module._read_block

    def counting(f, start: int, size: int) -> bytes:
        read.append(size)
        return original(f, start, size)

    monkeypatch.setattr(logger_module, "_read_block", counting)
    entries = LogManager(tmp_path).tail("task.load", lines=3)
    assert [e["message"] for e in entries] == ["line 19997", "line 19998", "line 19999"]
    assert sum(read) <= logger_module._BLOCK_SIZE < path.stat().st_size


def test_tail_handles_a_file_without_a_trailing_newline_and_short_files(tmp_path):
    (tmp_path / "task.load.jsonl").write_text(
        '{"ts": "t", "level": "INFO", "message": "a"}\n{"ts": "t", "level": "INFO", "message": "b"}'
    )
    assert [e["message"] for e in LogManager(tmp_path).tail("task.load", lines=5)] == ["a", "b"]


def test_records_reads_backups_oldest_first_then_the_current_file(tmp_path):
    manager = LogManager(tmp_path, {"max-bytes": 1, "backups": 12})
    for i in range(12):
        manager.write("task.load", "INFO", f"line {i}")
    manager.write("task.other", "INFO", "other")
    by_key: dict[str, list[str]] = {}
    for record in manager.records():
        by_key.setdefault(record["key"], []).append(record["message"])
    assert by_key == {"task.load": [f"line {i}" for i in range(12)], "task.other": ["other"]}


def test_records_since_skips_files_last_written_before_it(tmp_path):
    manager = LogManager(tmp_path, {"max-bytes": 1})
    manager.write("task.load", "INFO", "old")
    manager.write("task.load", "INFO", "new")
    old = tmp_path / "task.load.1.jsonl"
    os.utime(old, (1_000_000, 1_000_000))
    assert [r["message"] for r in manager.records(since=2_000_000)] == ["new"]
    assert [r["message"] for r in manager.records(since=datetime.fromtimestamp(2_000_000))] == [
        "new"
    ]
    assert [r["message"] for r in manager.records()] == ["old", "new"]


@pytest.mark.parametrize(
    "config, message",
    [
        ({"max-bytes": 0}, "max-bytes"),
        ({"max-bytes": "10MB"}, "max-bytes"),
        ({"max-bytes": True}, "max-bytes"),
        ({"backups": 0}, "backups"),
    ],
)
def test_rotation_keys_are_validated(config, message):
    with pytest.raises(ValueError, match=message):
        LogManager(config=config)


def test_validate_lists_the_rotation_keys():
    manager = LogManager(config={"tsak": {"level": "DEBUG"}})
    with pytest.raises(ValueError, match="max-bytes, backups"):
        manager.validate({"task"}, ["task.load"])
