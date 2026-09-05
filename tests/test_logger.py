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
    manager = LogManager(tmp_path)
    logger = manager.logger_for("Thing")
    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")

    levels = [e["level"] for e in manager.tail("Thing")]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]
