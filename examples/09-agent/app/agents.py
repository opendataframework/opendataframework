from app.components import Catalogue, Model
from opendataframework import Agent


@Agent
class Librarian:
    """Answers questions about the catalogue, one model-chosen step at a time."""

    def __init__(self, catalogue: Catalogue, model: Model) -> None:
        self.catalogue = catalogue
        self.model = model
        self.max_steps = 5

    def invoke(self, question: str) -> str:
        observations: list[tuple[str, list[str]]] = []
        for _ in range(self.max_steps):
            action, argument = self.model.decide(question, observations)
            if action == "answer":
                return argument
            result = self._act(action, argument)
            print(f"  {action}({argument}) -> {result}")
            observations.append((action, result))
        return "I ran out of steps."

    def _act(self, action: str, argument: str) -> list[str]:
        if action == "list-authors":
            return self.catalogue.authors()
        return self.catalogue.titles_by(argument)
