from opendataframework import Component, Config


@Component
class Greeter:
    def __init__(self, config: Config) -> None:
        cfg = config.get("greeter")
        self.greeting = cfg.get("greeting", "Hello")
        self.name = cfg.get("name", "World")

    def greet(self) -> str:
        return f"{self.greeting}, {self.name}!"
