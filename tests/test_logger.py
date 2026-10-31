import json
import re
from datetime import datetime
from pathlib import Path

import pytest

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
