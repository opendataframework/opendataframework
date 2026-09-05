import time

from opendataframework import Config, Service


@Service
class Heartbeat:
    def __init__(self, config: Config) -> None:
        self.interval = config.get("heartbeat").get("interval", 1.0)
        self.count = 0
        self._running = False

    def setup(self) -> None:
        print("Heartbeat.setup    starting up")
        self._running = True

    def run(self) -> None:
        # Blocks by design — the framework backgrounds this in a thread, so
        # project.start() returns as soon as setup() is done, not after run().
        while self._running:
            time.sleep(self.interval)
            if self._running:
                self.count += 1
                print(f"Heartbeat.run      tick {self.count}")

    def stop(self) -> None:
        print(f"Heartbeat.stop     stopping after {self.count} ticks")
        self._running = False
