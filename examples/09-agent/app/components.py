from opendataframework import Component


@Component
class Catalogue:
    def __init__(self) -> None:
        self.books: list[tuple[str, str]] = [
            ("Dune", "Frank Herbert"),
            ("Emma", "Jane Austen"),
            ("Persuasion", "Jane Austen"),
        ]

    def authors(self) -> list[str]:
        return sorted({author for _, author in self.books})

    def titles_by(self, author: str) -> list[str]:
        return [title for title, written_by in self.books if written_by == author]


@Component
class Model:
    """Stand-in for a language model — picks the next step by fixed rules.

    In a real project this is where a model client or an agentic library
    goes. It is a separate component so the agent's loop stays the same
    whichever one is behind it.
    """

    def decide(self, question: str, observations: list[tuple[str, list[str]]]) -> tuple[str, str]:
        """Return the next ``(action, argument)`` given what has been observed so far."""
        if not observations:
            return ("list-authors", "")
        action, result = observations[-1]
        if action == "list-authors":
            for author in result:
                if author.split()[-1].lower() in question.lower():
                    return ("find-titles", author)
            return ("answer", "I couldn't find that author.")
        return ("answer", ", ".join(result))
