import pytest

from opendataframework.logger import Logger, LogManager

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

    assert (tmp_path / "thing.log").exists()
    assert (tmp_path / "other-thing.log").exists()


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
    assert entries[0] == {"ts": entries[0]["ts"], "level": "INFO", "message": "hello"}
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
        levels={
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
        LogManager(levels={"task": {"load": "LOUD"}})
    with pytest.raises(ValueError, match="level = 10"):
        LogManager(levels={"level": 10})


def test_a_namespace_needs_a_table():
    with pytest.raises(ValueError, match="task.level = 'DEBUG'"):
        LogManager(levels={"task": "DEBUG"})


def test_validate_rejects_an_unknown_namespace():
    manager = LogManager(levels={"tsak": {"level": "DEBUG"}})
    with pytest.raises(ValueError, match="unknown key 'tsak'.*task"):
        manager.validate({"task"}, ["task.load"])


def test_validate_rejects_an_unknown_component():
    manager = LogManager(levels={"task": {"lod": "DEBUG"}})
    with pytest.raises(ValueError, match=r"\[project.logging.task\] has unknown key 'lod'.*load"):
        manager.validate({"task"}, ["task.load"])


def test_validate_accepts_known_keys():
    manager = LogManager(levels={"level": "INFO", "task": {"level": "INFO", "load": "DEBUG"}})
    manager.validate({"task"}, ["task.load"])


def test_context_open_rejects_a_component_typo(tmp_path):
    from opendataframework.context import Context
    from opendataframework.namespace import Namespace

    class Scope(Namespace): ...

    @Scope
    class Load: ...

    ctx = Context(namespaces={Scope}, log_dir=tmp_path, log_levels={"scope": {"lod": "DEBUG"}})
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
    with Context(namespaces={Scope}, log_dir=tmp_path, log_levels=levels) as ctx:
        assert "constructed" in [e["message"] for e in ctx.tail_logs("scope.load")]
        assert "constructed" not in [e["message"] for e in ctx.tail_logs("scope.other")]
