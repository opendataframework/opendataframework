"""The notification history: ``history/notifications.jsonl`` and ``notification_history()``."""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from opendataframework import LogsUnavailable, normalize_key
from opendataframework import logger as logger_module
from opendataframework.component import Component
from opendataframework.context import Context
from opendataframework.events import _summary
from opendataframework.logger import _HISTORY, LogManager, check_key
from opendataframework.namespace import Namespace
from opendataframework.notifications import Notifications, Publisher
from opendataframework.task import Task
from opendataframework.utils import normalize

# --- helpers -----------------------------------------------------------------


def make_ns():
    """Return a fresh isolated Namespace subclass for each test."""

    class Scope(Namespace): ...

    return Scope


def make_ctx(log_dir: Path | None, log_config: dict | None = None) -> Context:
    """Return a Context logging to ``log_dir``, with nothing registered."""
    return Context(namespaces={make_ns()}, log_dir=log_dir, log_config=log_config)


def hub(log_dir: Path, config: dict | None = None) -> tuple[LogManager, Notifications]:
    """Return a LogManager on ``log_dir`` and an unbound hub writing to it."""
    manager = LogManager(log_dir, config)
    return manager, Notifications(manager)


def history_path(log_dir: Path, backup: int = 0) -> Path:
    """Return the history file, or its ``backup``-th rotated one."""
    suffix = f".{backup}" if backup else ""
    return log_dir / "history" / f"notifications{suffix}.jsonl"


def history_lines(log_dir: Path, backup: int = 0) -> list[dict]:
    """Return the records in one history file, in file order."""
    return [json.loads(line) for line in history_path(log_dir, backup).read_text().splitlines()]


def seqs(rows: list[dict]) -> list[int]:
    """Return the ``seq`` inside each row's cursor."""
    return [int(row["cursor"]) for row in rows]


def line_size(tmp_path: Path) -> int:
    """Return the size of one history line for a one-digit seq, as ``fill()`` writes them."""
    _, notifications = hub(tmp_path / "probe")
    notifications.publish("a.b", key="webhooks", summary="s")
    return history_path(tmp_path / "probe").stat().st_size


def fill(notifications: Notifications, count: int) -> None:
    """Publish ``count`` same-size notifications."""
    for _ in range(count):
        notifications.publish("a.b", key="webhooks", summary="s")


def handwrite(path: Path, records: list[dict], mtime: float | None = None) -> None:
    """Write history ``records`` to ``path`` by hand, optionally setting its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def iso(ts: float) -> str:
    """Return ``ts`` as a record's ISO 8601 ``ts``."""
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="milliseconds")


# --- keys --------------------------------------------------------------------


@pytest.mark.parametrize("key", ["", "a/b", "a\\b", "../x", ".hidden", "k" * 201])
def test_publish_rejects_a_key_unsafe_as_a_file_name(tmp_path, key):
    log_dir = tmp_path / "logs"
    _, notifications = hub(log_dir)
    received = []
    notifications.subscribe(received.append)
    with pytest.raises(ValueError, match="invalid key"):
        notifications.publish("a.b", key=key, summary="s")
    assert received == []
    assert not log_dir.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_a_200_byte_key_publishes_and_its_backups_are_created(tmp_path):
    key = "k" * 200
    _, notifications = hub(tmp_path, {"max-bytes": 1})
    notifications.publish("a.b", key=key)
    notifications.publish("a.b", key=key)
    assert (tmp_path / f"{key}.jsonl").exists()
    assert (tmp_path / f"{key}.1.jsonl").exists()


def test_the_key_length_is_its_file_name_s():
    with pytest.raises(ValueError, match="200 bytes"):
        check_key("A" * 150)  # kebab-case: 299 bytes
    with pytest.raises(ValueError, match="200 bytes"):
        check_key("é" * 101)  # 202 bytes in UTF-8


@pytest.mark.parametrize("key", ["webhooks", "webhooks.", "task.take-orders"])
def test_safe_keys_still_publish(tmp_path, key):
    _, notifications = hub(tmp_path)
    notifications.publish("a.b", key=key)
    assert (tmp_path / f"{key}.jsonl").exists()


def test_component_files_go_through_the_key_check():
    manager = LogManager("unused")
    with pytest.raises(ValueError, match="invalid key"):
        manager._path(_HISTORY)
    assert manager._history_path(1).name == "notifications.1.jsonl"


def test_normalize_key():
    assert normalize_key("Task.TakeOrders") == "task.take-orders"
    assert normalize_key("Webhooks") == "webhooks"
    assert normalize_key("webhooks.") == normalize("webhooks.")
    assert normalize_key("WebHooks") != normalize_key("webhooks")


# --- writing -----------------------------------------------------------------


def test_publish_writes_summary_to_the_component_log_and_the_history(tmp_path):
    manager, notifications = hub(tmp_path)
    notifications.publish("orders.received", key="webhooks", summary="Le Petit: 2 baguettes")
    notifications.publish("orders.received", key="webhooks")
    logged = manager.tail("webhooks")
    assert [r["summary"] for r in logged] == ["Le Petit: 2 baguettes", None]
    assert [r["message"] for r in logged] == [
        "notified orders.received: Le Petit: 2 baguettes",
        "notified orders.received",
    ]
    history = history_lines(tmp_path)
    assert [r["summary"] for r in history] == ["Le Petit: 2 baguettes", None]
    for own, copied in zip(logged, history, strict=True):
        assert copied == {**own, "seq": copied["seq"]}
    assert [r["seq"] for r in history] == [1, 2]


def test_concurrent_publishers_get_gap_free_increasing_seqs(tmp_path):
    _, notifications = hub(tmp_path)

    def publish_many(n: int) -> None:
        for i in range(50):
            notifications.publish("a.b", key=f"publisher-{n}", summary=str(i))

    threads = [threading.Thread(target=publish_many, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    history = history_lines(tmp_path)
    assert [r["seq"] for r in history] == list(range(1, 401))
    stamps = [datetime.fromisoformat(r["ts"]) for r in history]
    assert stamps == sorted(stamps)


def test_seq_continues_across_a_restart(tmp_path):
    fill(hub(tmp_path)[1], 2)
    fill(hub(tmp_path)[1], 1)
    assert [r["seq"] for r in history_lines(tmp_path)] == [1, 2, 3]


def test_seq_continues_when_the_current_file_is_empty_after_a_rotation(tmp_path):
    fill(hub(tmp_path, {"history-max-bytes": 1})[1], 2)
    # As if a rotation happened and the process stopped before the next write.
    os.replace(history_path(tmp_path, 1), history_path(tmp_path, 2))
    os.replace(history_path(tmp_path), history_path(tmp_path, 1))
    history_path(tmp_path).touch()
    fill(hub(tmp_path, {"history-max-bytes": 1})[1], 1)
    assert [r["seq"] for r in history_lines(tmp_path)] == [3]


def test_a_truncated_last_line_is_ended_before_the_next_record(tmp_path):
    fill(hub(tmp_path)[1], 2)
    path = history_path(tmp_path)
    whole = path.read_text().splitlines()[-1]
    with path.open("a") as f:
        f.write(whole[: len(whole) // 2])  # a crash mid-write
    manager, notifications = hub(tmp_path)
    fill(notifications, 1)
    lines = path.read_text().splitlines()
    assert len(lines) == 4
    assert json.loads(lines[-1])["seq"] == 3
    assert seqs(manager.notification_history()) == [3, 2, 1]


def test_the_history_directory_is_created_on_the_first_write(tmp_path):
    manager, notifications = hub(tmp_path)
    manager.write("task.load", "INFO", "hello")
    assert not (tmp_path / "history").exists()
    fill(notifications, 1)
    assert history_path(tmp_path).exists()


@pytest.mark.parametrize(
    "config, history_rotates, components_rotate",
    [
        ({"history-max-bytes": 1, "history-backups": 2, "max-bytes": 10**9}, True, False),
        ({"max-bytes": 1, "backups": 2}, True, True),
        ({}, False, False),
        ({"history-max-bytes": 1}, True, False),
    ],
)
def test_history_rotation_settings(tmp_path, config, history_rotates, components_rotate):
    _, notifications = hub(tmp_path, config)
    fill(notifications, 4)
    history = sorted(p.name for p in (tmp_path / "history").iterdir())
    components = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    if history_rotates:
        backups = config.get("history-backups", config.get("backups", 5))
        expected = 3 if backups == 2 else 4
        assert len(history) == expected
    else:
        assert history == ["notifications.jsonl"]
    assert (len(components) > 1) is components_rotate


@pytest.mark.parametrize(
    "config",
    [{"history-max-bytes": 0}, {"history-max-bytes": "big"}, {"history-backups": True}],
)
def test_history_size_keys_are_validated(config):
    with pytest.raises(ValueError, match="history-"):
        LogManager(config=config)


def test_a_history_namespace_can_still_set_its_levels():
    manager = LogManager(config={"history": {"level": "DEBUG"}})
    assert manager.threshold("history.archive") == 10
    with pytest.raises(ValueError, match="history-max-bytes, history-backups"):
        LogManager(config={"tsak": {"level": "DEBUG"}}).validate({"task"}, [])


def test_close_closes_the_history_file(tmp_path):
    manager, notifications = hub(tmp_path)
    fill(notifications, 1)
    handle = manager._files[_HISTORY]
    manager.close()
    assert handle.closed


def test_the_history_is_json_lines_in_the_text_format(tmp_path):
    manager, notifications = hub(tmp_path, {"format": "text"})
    fill(notifications, 1)
    assert (tmp_path / "webhooks.log").exists()
    assert history_lines(tmp_path)[0]["summary"] == "s"
    assert seqs(manager.notification_history()) == [1]


def test_a_threshold_drops_a_notification_from_the_history_too(tmp_path):
    manager, notifications = hub(tmp_path, {"notifications": "WARNING"})
    notifications.publish("a.b", key="webhooks", summary="dropped")
    assert not history_path(tmp_path).exists()
    notifications.publish("a.b", key="webhooks", summary="kept", level="warning")
    assert [r["summary"] for r in manager.notification_history()] == ["kept"]


def test_records_and_traces_never_see_the_history_file(tmp_path):
    NS = make_ns()

    @Publisher("orders.received")
    @NS
    @Task
    class TakeOrder:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def execute(self) -> None:
            self.notifications.publish("orders.received", summary="Le Petit: 2 baguettes")

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.take-order")
    published = [r for r in ctx._log_manager.records() if r["source"] == "notifications"]
    assert len(published) == 1
    (notification,) = ctx.trace(published[0]["parent"])["notifications"]
    assert notification["summary"] == "Le Petit: 2 baguettes"
    assert notification["message"] == "notified orders.received: Le Petit: 2 baguettes"
    assert len(ctx.logs(published[0]["parent"])) == 3  # started, notified, completed


def test_other_records_are_written_as_before(tmp_path):
    manager = LogManager(tmp_path)
    manager.write("task.load", "INFO", "hello")
    (record,) = manager.tail("task.load")
    assert set(record) == {"ts", "level", "key", "namespace", "name", "source", "message"}


# --- reading -----------------------------------------------------------------


def test_after_a_restart_the_history_reads_back_before_anything_is_published(tmp_path):
    fill(hub(tmp_path)[1], 3)
    assert seqs(LogManager(tmp_path).notification_history()) == [3, 2, 1]


def test_rows_are_newest_first_with_every_field(tmp_path):
    NS = make_ns()

    @NS
    @Component
    class HistoryOrders: ...

    @Publisher("orders.received")
    @NS
    @Task
    class TakeOrder:
        def __init__(self, notifications: Notifications) -> None:
            self.notifications = notifications

        def execute(self) -> None:
            self.notifications.publish(
                "orders.received", {"secret": 1}, summary="2 baguettes", subject=HistoryOrders, record=7
            )

    with Context(namespaces={NS}, log_dir=tmp_path) as ctx:
        ctx.execute("scope.take-order")
        sent = ctx.notifications.publish(
            "messages.received", key="webhooks", level="warning", summary="hi"
        )
        newest, oldest = ctx.notification_history()
    assert newest == {
        "id": sent.id,
        "key": "webhooks",
        "topic": "messages.received",
        "level": "warning",
        "summary": "hi",
        "message": "notified messages.received: hi",
        "subject": None,
        "record": None,
        "parent": None,
        "ts": newest["ts"],
        "cursor": newest["cursor"],
    }
    assert oldest["key"] == "scope.take-order"
    assert oldest["level"] == "info"
    assert oldest["subject"] == "scope.history-orders"
    assert oldest["record"] == 7
    assert oldest["parent"] is not None
    assert "secret" not in json.dumps(oldest)
    assert datetime.fromisoformat(newest["ts"]) >= datetime.fromisoformat(oldest["ts"])
    json.dumps([newest, oldest])  # JSON-ready


def test_the_key_filter_compares_normalised_keys(tmp_path):
    ctx = make_ctx(tmp_path)
    for key in ("webhooks", "task.take-orders", "webhooks.", "Task.Other"):
        ctx.notifications.publish("a.b", key=key)
    assert [r["key"] for r in ctx.notification_history(key="Webhooks")] == ["webhooks"]
    assert [r["key"] for r in ctx.notification_history(key="Task.TakeOrders")] == [
        "task.take-orders"
    ]
    assert [r["key"] for r in ctx.notification_history(key="webhooks.")] == ["webhooks."]
    assert [r["key"] for r in ctx.notification_history(key="task.other")] == ["Task.Other"]
    assert ctx.notification_history(key="removed.component") == []


def test_each_filter(tmp_path):
    ctx = make_ctx(tmp_path)
    publish = ctx.notifications.publish
    publish("orders.received", key="a", summary="1")
    publish("orders.received.late", key="a", level="warning")
    publish("orders", key="b", level="error", summary="3")
    publish("messages.received", key="b", level="success", summary="4")

    def topics(**kwargs) -> list[str]:
        return [r["topic"] for r in ctx.notification_history(**kwargs)]

    assert topics(topic="orders") == ["orders"]
    assert topics(topic="orders.*") == ["orders.received.late", "orders.received"]
    assert topics(topic=("orders", "messages.*")) == ["messages.received", "orders"]
    assert topics(key="b") == ["messages.received", "orders"]
    assert topics(level="warning") == ["orders.received.late"]
    assert topics(level=("error", "success")) == ["messages.received", "orders"]
    assert topics(summary_only=True) == ["messages.received", "orders", "orders.received"]
    assert topics(topic="orders.*", summary_only=True) == ["orders.received"]
    assert topics(limit=2) == ["messages.received", "orders"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"topic": "a*b"},
        {"topic": ()},
        {"level": "warn"},
        {"level": ()},
        {"before": "not-a-cursor"},
        {"before": "0"},
        {"before": True},
        {"since": "yesterday"},
        {"key": "../x"},
        {"key": ""},
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"summary_only": "yes"},
    ],
)
def test_invalid_arguments_are_a_plain_value_error(tmp_path, kwargs):
    for ctx in (make_ctx(tmp_path), make_ctx(None)):
        with pytest.raises(ValueError) as raised:
            ctx.notification_history(**kwargs)
        assert type(raised.value) is ValueError


def test_logs_unavailable(tmp_path):
    assert issubclass(LogsUnavailable, ValueError)
    off = make_ctx(None)
    with pytest.raises(LogsUnavailable, match="file logging is off"):
        off.notification_history()
    with pytest.raises(LogsUnavailable):
        off.trace("abc")
    with pytest.raises(LogsUnavailable):
        off.logs("abc")
    text = make_ctx(tmp_path, {"format": "text"})
    assert text.notification_history() == []
    with pytest.raises(LogsUnavailable, match='"json" log format'):
        text.trace("abc")
    with pytest.raises(LogsUnavailable):
        text.logs("abc")


def test_paging_by_cursor_walks_everything_with_no_repeats_or_gaps(tmp_path):
    manager, notifications = hub(tmp_path, {"history-max-bytes": 2000, "history-backups": 100})
    for i in range(250):  # many in the same millisecond
        notifications.publish("a.b", key="webhooks", summary=str(i))
    walked: list[int] = []
    page = manager.notification_history(limit=7)
    while page:
        walked += seqs(page)
        page = manager.notification_history(limit=7, before=page[-1]["cursor"])
    assert walked == list(range(250, 0, -1))


def test_before_a_time_returns_only_older_rows(tmp_path):
    now = time.time()
    handwrite(
        history_path(tmp_path),
        [
            {"seq": 1, "ts": iso(now - 20), "key": "k"},
            {"seq": 2, "ts": iso(now - 10), "key": "k"},
            {"seq": 3, "ts": iso(now), "key": "k"},
        ],
    )
    manager = LogManager(tmp_path)
    assert seqs(manager.notification_history(before=datetime.fromtimestamp(now - 5))) == [2, 1]
    assert seqs(manager.notification_history(before=now - 15)) == [1]


def test_since_stops_the_read_and_skips_backups_last_written_well_before_it(
    tmp_path, monkeypatch
):
    since = time.time()
    handwrite(
        history_path(tmp_path),
        [{"seq": 4, "ts": iso(since - 1), "key": "k"}, {"seq": 5, "ts": iso(since + 9)}],
    )
    # Modified within a second before since: may still hold a record after it.
    handwrite(history_path(tmp_path, 1), [{"seq": 3, "ts": iso(since + 0.5)}], since - 0.5)
    handwrite(history_path(tmp_path, 2), [{"seq": 2, "ts": iso(since - 10)}], since - 5)
    handwrite(history_path(tmp_path, 3), [{"seq": 1, "ts": iso(since - 20)}], since - 6)
    manager = LogManager(tmp_path)
    assert seqs(manager.notification_history(since=since)) == [5]  # stops at seq 4

    (tmp_path / "history" / "notifications.jsonl").write_text(
        json.dumps({"seq": 5, "ts": iso(since + 9)}) + "\n"
    )
    opened: list[str] = []
    real_open = open

    def spy(path, *args, **kwargs):
        opened.append(Path(path).name)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(logger_module, "open", spy, raising=False)
    assert seqs(manager.notification_history(since=since)) == [5, 3]
    assert opened == ["notifications.jsonl", "notifications.1.jsonl"]


def count_block_reads(monkeypatch, on_read=None) -> dict[str, int]:
    """Count ``_read_block`` calls per file name, calling ``on_read`` before the first."""
    reads: dict[str, int] = {}
    real = logger_module._read_block

    def counting(f, start: int, size: int) -> bytes:
        if not reads and on_read is not None:
            on_read()
        name = Path(f.name).name
        reads[name] = reads.get(name, 0) + 1
        return real(f, start, size)

    monkeypatch.setattr(logger_module, "_read_block", counting)
    return reads


def test_a_file_entirely_newer_than_the_cursor_is_read_only_to_its_first_line(
    tmp_path, monkeypatch
):
    size = line_size(tmp_path)
    manager, notifications = hub(tmp_path / "logs", {"history-max-bytes": size * 3})
    fill(notifications, 6)
    assert [r["seq"] for r in history_lines(tmp_path / "logs")] == [4, 5, 6]
    reads = count_block_reads(monkeypatch)
    assert seqs(manager.notification_history(before="4")) == [3, 2, 1]
    assert reads == {"notifications.1.jsonl": 1}


def test_a_rotation_mid_read_gives_no_duplicates_and_no_gaps(tmp_path, monkeypatch):
    size = line_size(tmp_path)
    log_dir = tmp_path / "logs"
    manager, notifications = hub(log_dir, {"history-max-bytes": size * 3, "history-backups": 3})
    fill(notifications, 9)  # .2: 1-3, .1: 4-6, current: 7-9

    reads = count_block_reads(monkeypatch, on_read=lambda: fill(notifications, 1))
    rows = manager.notification_history()
    assert seqs(rows) == [9, 8, 7, 6, 5, 4, 3, 2, 1]  # seq 10, written during the read, isn't
    # The file just read, reopened under its new name, is read only to its first line.
    assert reads == {
        "notifications.jsonl": 1,
        "notifications.2.jsonl": 1,
        "notifications.3.jsonl": 1,
    }
    assert seqs(manager.notification_history()) == list(range(10, 0, -1))


def test_nothing_published_gives_no_rows(tmp_path):
    assert make_ctx(tmp_path).notification_history() == []
    assert make_ctx(tmp_path / "missing").notification_history() == []


# --- trace -------------------------------------------------------------------


def test_a_trace_notification_s_summary_falls_back_to_its_message():
    assert _summary({"summary": "s", "topic": "a.b", "message": "notified a.b: x"}) == "s"
    assert _summary({"summary": None, "topic": "a.b", "message": "notified a.b"}) is None
    assert _summary({"topic": "a.b", "message": "notified a.b: Le Petit: 2"}) == "Le Petit: 2"
    assert _summary({"topic": "a.b", "message": "notified a.b"}) is None
