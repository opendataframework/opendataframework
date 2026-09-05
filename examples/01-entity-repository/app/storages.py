import sqlite3
import threading

from opendataframework import Component, Config


@Component
class SQLite:
    def __init__(self, config: Config) -> None:
        path = config.get("sqlite").get("path", "app.db")
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                title  TEXT NOT NULL,
                author TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def on_stop(self) -> None:
        self.conn.close()
