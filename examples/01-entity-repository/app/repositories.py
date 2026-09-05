from app.entities import Book
from app.storages import SQLite
from opendataframework import Repository


@Repository(Book)
class Books:
    def __init__(self, sqlite: SQLite) -> None:
        self.db = sqlite

    def all(self) -> list[Book]:
        with self.db.lock:
            rows = self.db.conn.execute("SELECT id, title, author FROM books").fetchall()
        return [Book(id=r[0], title=r[1], author=r[2]) for r in rows]

    def get(self, book_id: int) -> Book | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT id, title, author FROM books WHERE id = ?", (book_id,)
            ).fetchone()
        return Book(id=row[0], title=row[1], author=row[2]) if row else None

    def save(self, book: Book) -> None:
        with self.db.lock:
            if book.id is None:
                cursor = self.db.conn.execute(
                    "INSERT INTO books (title, author) VALUES (?, ?)",
                    (book.title, book.author),
                )
                book.id = cursor.lastrowid
            else:
                self.db.conn.execute(
                    "UPDATE books SET title = ?, author = ? WHERE id = ?",
                    (book.title, book.author, book.id),
                )
            self.db.conn.commit()

    def delete(self, book_id: int) -> None:
        with self.db.lock:
            self.db.conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            self.db.conn.commit()
