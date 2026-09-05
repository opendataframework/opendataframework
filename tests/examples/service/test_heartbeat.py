import threading
import time

import pytest
from app.services import Heartbeat

from opendataframework.config import Config

# Deliberately drives setup()/run()/stop() by hand rather than through
# Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): @Service registration is
# global for the whole pytest process. run() blocks by design, so it's driven
# in a thread here the same way the Context would background it.


@pytest.fixture
def heartbeat() -> Heartbeat:
    return Heartbeat(Config({"heartbeat": {"interval": 0.01}}))


def test_heartbeat_reads_interval_from_config(heartbeat):
    assert heartbeat.interval == 0.01


def test_heartbeat_falls_back_to_default_interval():
    heartbeat = Heartbeat(Config({}))
    assert heartbeat.interval == 1.0


def test_heartbeat_ticks_while_running_then_stops_cleanly(heartbeat):
    heartbeat.setup()
    thread = threading.Thread(target=heartbeat.run)
    thread.start()

    time.sleep(0.05)
    heartbeat.stop()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert heartbeat.count > 0
