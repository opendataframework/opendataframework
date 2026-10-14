# 09 — Agent

One `@Agent`, `Librarian`, that answers questions about a small book
catalogue. It is handed a question at call time and works towards an answer
one step at a time, each step chosen by a model rather than written down in
advance.

This isolates the concept covered in [`docs/agent.md`](../../docs/agent.md):
an agent is a class with a single `invoke()` method that takes whatever
arguments its author declares. Everything it may act on is declared in its
constructor like any other dependency — here the `Catalogue` `@Component` it
reads from, and the `Model` `@Component` that decides the next step. The
framework resolves and injects both, calls `invoke()` by name through
`project.context.call(...)`, and logs every invocation.

`opendataframework` ships no model client and no agent loop. `Model` here is
a rule-based stand-in, so the example runs with no third-party dependency and
no API key; in a real project it is where a provider SDK or an agentic
library goes, and `Librarian.invoke()` stays the place where it meets the
project's components.

## Structure

```
09-agent/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — invokes the agent two different ways
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── components.py      # Catalogue, Model — @Component
    └── agents.py          # Librarian — @Agent
```

## Run it

```bash
cd examples/09-agent
python main.py
```

Expected output:

```
call('agent.librarian', question='What do you have by Austen?')
  list-authors() -> ['Frank Herbert', 'Jane Austen']
  find-titles(Jane Austen) -> ['Emma', 'Persuasion']
-> Emma, Persuasion

get(Librarian).invoke('Anything by Tolkien?')
  list-authors() -> ['Frank Herbert', 'Jane Austen']
-> I couldn't find that author.

parameters(Librarian) -> ['question']
```

`main.py` shows both ways to invoke a registered agent:

- `project.context.call("agent.librarian", question=...)` — by key,
  with keyword arguments passed on to `invoke()`.
- `project.context.get(Librarian).invoke(...)` — by class, typed, the way a
  `Pipeline` or `Service` holding an injected `Librarian` would call it.

`project.context.parameters(Librarian)` returns the parameters of `invoke()`
— what a caller needs to ask for before it can invoke the agent.

The two questions take a different number of steps: the loop in `invoke()`
runs until the model returns an answer, and gives up after `max_steps`.
