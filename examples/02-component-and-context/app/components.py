from opendataframework import Component, Config


@Component
class Database:
    """Depends only on the framework-provided Config — nothing else."""

    def __init__(self, config: Config) -> None:
        self.dsn = config.get("database").get("dsn", "sqlite:///app.db")

    def on_start(self) -> None:
        print(f"Database.on_start  connecting to {self.dsn}")

    def on_stop(self) -> None:
        print("Database.on_stop   closing connection")

    def query(self, key: str) -> str:
        return f"row for {key!r} from {self.dsn}"


@Component
class Cache:
    """Depends on Database — the Context must build Database first."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._store: dict[str, str] = {}

    def on_start(self) -> None:
        print("Cache.on_start     ready, store is empty")

    def on_stop(self) -> None:
        print(f"Cache.on_stop      dropping {len(self._store)} cached entries")
        self._store.clear()

    def get(self, key: str) -> str:
        if key not in self._store:
            self._store[key] = self.database.query(key)
        return self._store[key]
