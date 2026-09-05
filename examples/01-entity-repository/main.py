"""Entity + Repository, the smallest possible ODF data layer.

No Service, no UI — just a Project, a Repository, and the CRUD methods it
exposes. Run from this directory: `python main.py`.
"""

from app.entities import Book
from app.repositories import Books

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

books = project.context.get(Books)

books.save(Book(id=None, title="Dune", author="Frank Herbert"))
books.save(Book(id=None, title="Neuromancer", author="William Gibson"))

print("All books:")
for book in books.all():
    print(f"  {book}")

first = books.all()[0]
assert first.id is not None
first.author = "Frank Herbert (corrected)"
books.save(first)
print(f"\nUpdated: {books.get(first.id)}")

books.delete(first.id)
print(f"\nAfter delete: {books.all()}")

project.stop()
