import threading

from app.listeners import FailureAlerts
from opendataframework import Service


@Service
class AlertSender:
    """Drains FailureAlerts' queue in the background, off the calls' hot path."""

    def __init__(self, alerts: FailureAlerts) -> None:
        self.alerts = alerts
        self.sent: list[str] = []  # a stand-in for posting to a chat channel
        self._drained = threading.Event()

    def setup(self) -> None:
        self._drained.clear()

    def run(self) -> None:
        while (event := self.alerts.queue.get()) is not None:
            self.sent.append(f"{event.key} {event.method}() failed: {event.error}")
        self._drained.set()

    def stop(self) -> None:
        self.alerts.queue.put(None)  # lets run() return
        self._drained.wait(timeout=5)  # sends whatever was queued before stopping
