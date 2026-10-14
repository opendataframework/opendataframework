"""Agent: a goal handed over at call time, pursued one chosen step at a time.

Librarian is an @Agent. Its constructor declares what it may act on — the
Catalogue — and what decides its next step — the Model, a rule-based
stand-in for a language model. Its invoke() runs the loop between the two.
Run from this directory: `python main.py`.
"""

from app.agents import Librarian

from opendataframework import Project

project = Project.from_config("config.toml")
project.start()

# By name — what a caller holding only a name and arguments would do.
print("call('agent.librarian', question='What do you have by Austen?')")
answer = project.context.call("agent.librarian", question="What do you have by Austen?")
print(f"-> {answer}\n")

# By class — the same thing, typed, for use from Python.
print("get(Librarian).invoke('Anything by Tolkien?')")
answer = project.context.get(Librarian).invoke("Anything by Tolkien?")
print(f"-> {answer}\n")

# What a caller must supply — enough to build a form or a schema.
print(f"parameters(Librarian) -> {list(project.context.parameters(Librarian))}")

project.stop()
