from app.agents import Librarian
from app.components import Catalogue, Model

# Deliberately builds the agent directly rather than going through
# Project/Context — same reason as the other examples' tests (see
# tests/examples/entity_repository/test_books.py): registration is global
# for the whole pytest process.


def test_librarian_answers_with_titles_by_the_author_asked_about():
    librarian = Librarian(Catalogue(), Model())

    assert librarian.invoke("What do you have by Austen?") == "Emma, Persuasion"


def test_librarian_answers_when_the_author_is_unknown():
    librarian = Librarian(Catalogue(), Model())

    assert librarian.invoke("Anything by Tolkien?") == "I couldn't find that author."


def test_librarian_gives_up_after_max_steps():
    class Indecisive:
        def decide(self, question, observations):
            return ("list-authors", "")

    librarian = Librarian(Catalogue(), Indecisive())

    assert librarian.invoke("Anything?") == "I ran out of steps."


def test_model_starts_by_listing_authors():
    assert Model().decide("Anything by Austen?", []) == ("list-authors", "")
