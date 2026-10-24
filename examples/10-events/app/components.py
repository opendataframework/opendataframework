from opendataframework import Component


@Component
class Orders:
    def __init__(self) -> None:
        self.items: dict[int, list[float]] = {}

    def on_start(self) -> None:
        # A lifecycle hook, so it is reported as an OnStartProtocol call.
        self.items = {1: [9.5, 3.0], 2: [20.0], 3: [4.25, 4.25, 1.5]}
