# Agent

An `Agent` is a finite executable whose steps are decided at run time rather than
written down in advance — typically by a language model working towards a goal it is
handed when called. It is wired through dependency injection the same way as a
[Component](component.md), with a single `invoke()` contract that, unlike a
[Task](task.md)'s `execute()`, takes arguments.

The framework ships no model client and no agent loop. `@Agent` marks the place where
one — an agentic library, a provider SDK, or hand-written logic — meets the rest of the
project: its components, its configuration, its logging.

Agents answer one question:

> What should work towards this goal, given what the project has?

---

## When to use Agent

Use `@Agent` when a class needs to:

* be handed a goal at call time — a question, a ticket, a document
* decide its own steps to reach it, usually by driving a model
* act on the project's components, repositories, or services along the way
* run to completion and return a result

Typical examples:

* answering questions over a repository
* triaging or classifying incoming records
* drafting a report from several data sources
* reviewing the output of a pipeline

---

## Decorator

The `@Agent` decorator registers the class into the `Agent` namespace. The `Context`
reads from this namespace at startup. The class is returned unchanged.

### Without arguments

```python
@Agent
class Librarian:
    def invoke(self, question: str) -> str: ...
```

### With a name

```python
@Agent(name="librarian")
class CatalogueAssistant:
    def invoke(self, question: str) -> str: ...
```

### Combined with a Layer

```python
@Analytics
@Agent
class Librarian:
    def invoke(self, question: str) -> str: ...
```

!!! warning "`invoke()` is required"
    Applying `@Agent` to a class that does not define `invoke()` raises `TypeError` at
    decoration time, as does applying it to anything that is not a class.

---

## Interface

An `Agent` implements a single method — `invoke()`. Its signature is the author's to
choose: any number of parameters, of any type, with or without defaults. It may return
a value or `None`.

```python
@Agent
class Librarian:
    def invoke(self, question: str) -> str: ...


@Agent
class Triage:
    def invoke(self, ticket: Ticket, *, urgent: bool = False) -> Verdict: ...


@Agent
class NightlyReview:
    def invoke(self) -> Report: ...
```

No parameter name is reserved, and nothing in `invoke()` is injected — every parameter
is supplied by the caller.

---

## Dependency Injection

Like all components, an `Agent` declares its dependencies through the constructor. For
an agent this doubles as a statement of reach: what it can act on is exactly what its
constructor asks for, and it shows up in the dependency graph like any other edge.

```python
@Agent
class Librarian:
    def __init__(
        self,
        books: Books,
        model: Model,
        logger: Logger,
    ):
        self.books = books
        self.model = model
        self.logger = logger

    def invoke(self, question: str) -> str: ...
```

The model is usually one of those dependencies — a [Component](component.md) or
[Service](service.md) of your own that holds the client and its configuration — so it
can be shared between agents and replaced in tests.

---

## Using an Agent

An `Agent` is invoked through the `Context` by its registered name, with keyword
arguments passed on to `invoke()`:

```python
answer = project.context.call("librarian", question="Anything by Herbert?")
```

Or by class, typed:

```python
answer = project.context.get(Librarian).invoke("Anything by Herbert?")
```

`project.context.parameters(Librarian)` returns the parameters of `invoke()` — what a
caller building a form or a schema needs to ask for.

Every invocation is logged to the agent's own log file — start, duration, and any
exception — whichever way it was made. See [Logger](logger.md).

### As a step in a Pipeline

An agent is injected like any other dependency, so a [Pipeline](pipeline.md) can make
it one of its steps:

```python
@Pipeline
class WeeklyDigest:
    def __init__(self, fetcher: NewBooksFetcher, librarian: Librarian):
        self.fetcher = fetcher
        self.librarian = librarian

    def execute(self):
        self.fetcher.execute()
        return self.librarian.invoke("Summarise this week's additions.")
```

### Functions as dependencies

What an agent may act on needn't be a class. A registered [Function](function.md) is
declared in the constructor too, and arrives with its own dependencies filled in:

```python
@Agent
class Librarian:
    def __init__(self, find: Annotated[Callable[..., list[str]], find_titles], model: Model):
        self.find = find
        self.model = model
```

See [Injecting a Function](function.md#injecting-a-function).

### Long-running agents

An agent is finite: one goal in, one result out. For an agent that works continuously —
draining a queue, watching a stream — keep the loop in a [Service](service.md) and
inject the agent into it:

```python
@Service
class TicketWorker:
    def __init__(self, tickets: Tickets, triage: Triage):
        self.tickets = tickets
        self.triage = triage
        self._stopped = threading.Event()

    def setup(self): ...

    def run(self):
        while not self._stopped.is_set():
            for ticket in self.tickets.unprocessed():
                self.triage.invoke(ticket)
            self._stopped.wait(5)

    def stop(self):
        self._stopped.set()
```

### One agent using another

Agents can depend on each other through their constructors, with the same rule as
everywhere else: no circular dependencies.

```python
@Agent
class Editor:
    def __init__(self, librarian: Librarian): ...
```

---

## Tools

An agent usually works by asking a language model, inside `invoke()`, what to do next.
That makes "tool" mean two different things around an agent, declared in different
places: the tools the agent **uses** while it works, and the tools it **offers** to a
model somewhere else that wants to call it.

### Tools the agent uses

These are the agent's dependencies. Whatever it takes through its constructor — a
component's methods, a registered function — is what it can hand to the model it runs
inside `invoke()`. Nothing else is in reach, and the dependency graph shows it.

```python
@Agent
class Librarian:
    def __init__(self, find: Annotated[Callable[..., list[str]], find_titles], model: Model):
        self.model = model
        self.tools = {"find-titles": find}

    def invoke(self, question: str) -> str: ...
```

How those callables are described to the model is up to whatever runs the loop; an
injected function keeps its name and docstring, and its signature lists only the
arguments a caller supplies.

This half needs nothing beyond this package.

### Tools the agent offers

A model outside the agent — a chat assistant, an MCP client — can call it only if
something serves the project's tools to that model. This package doesn't: it has no MCP
server, and here an agent is invoked by project code alone, through a class that
injects it or through `project.context.call()`.

What the package does define is how a class declares the tools it offers: by
implementing `mcp_tools()`, described under
[Component → MCP Tools](component.md#mcp-tools). To offer the agent itself, it returns
its own `invoke`:

```python
@Agent
class Librarian:
    """Answers questions about the book catalogue."""

    def invoke(self, question: str) -> str: ...

    def mcp_tools(self) -> list[McpTool]:
        return [
            McpTool(
                name="invoke",
                description="Ask the librarian a question about the catalogue.",
                handler=self.invoke,
            )
        ]
```

The calling model sees the parameters of `invoke()` and fills them in, so they should be
types a schema can express — a `str`, a number, a dataclass — not an arbitrary object.
`McpTool` requires them, and the return value, to be annotated; an `invoke()` that is
never offered as a tool keeps its free-form signature.

!!! tip "Seeing it in practice"
    The sibling [`odf`](https://opendataframework.github.io/odf/) package's `McpServer`
    is the consumer of `mcp_tools()`. With it running, the model on the other side calls
    `librarian.invoke`, and the librarian in turn uses the tools from its constructor to
    work out the answer.

The two are independent. An agent that uses tools needn't offer any, and one that
offers itself needn't use any.

---

## Wrapping an agentic library

`invoke()` is where a library's own agent runs. The class holds it, hands it the
project's components as tools, and exposes one method to the framework. The example
below uses [Pydantic AI](https://ai.pydantic.dev/), which is not a dependency of this
package — any library, or none, fits the same shape.

```python
from pydantic_ai import Agent as ModelAgent


@Agent
class Librarian:
    """Answers questions about the book catalogue."""

    def __init__(self, books: Books, config: Config):
        self.books = books
        self.agent = ModelAgent(config.librarian.model, instructions="Answer from the catalogue.")
        self.agent.tool_plain(self.find)

    def find(self, title: str) -> list[str]:
        """Find books whose title contains the given text."""
        return [book.title for book in self.books.search(title)]

    def invoke(self, question: str) -> str:
        return self.agent.run_sync(question).output
```

For a version with no third-party dependency at all — a rule-based stand-in for the
model, so the loop itself is visible — see
[`examples/09-agent/`](https://github.com/opendataframework/opendataframework/tree/main/examples/09-agent).

---

## Protocol

`AgentProtocol` documents the expected interface and is available for type checking
and introspection:

```python
from opendataframework import AgentProtocol

isinstance(instance, AgentProtocol)  # True if invoke() is present
```

`AgentProtocol` is `@runtime_checkable`, so the check confirms only that `invoke` is
present, not its signature.

```python
class AgentProtocol(Protocol):
    def invoke(self, *args, **kwargs): ...
```

---

## What Agent is Not

* **Not a model client.** The framework has no third-party dependencies and talks to no
  provider. The model is a dependency you supply.

* **Not an agent loop.** Planning, tool calling, retries, and memory belong to the
  library or code inside `invoke()`.

* **Not a long-running process.** `invoke()` runs to completion. For continuous work,
  inject the agent into a [Service](service.md).

* **Not async, and not streamed for you.** The `Context` calls and never awaits, so an
  `async def invoke()` makes `project.start()` raise `TypeError`. An `invoke()` that
  returns an iterator hands it back as is; the log then records when the iterator was
  created, not how long it took to finish.

* **Not a base class.** `Librarian` does not inherit from `Agent`. The decorator
  registers it; inheritance is not involved.

---

## Decision Guide

| I need to...                                        | Use                         |
| --------------------------------------------------- | --------------------------- |
| Work towards a goal handed over at call time        | `Agent`                     |
| Execute a bounded unit of work once, no arguments   | [Task](task.md)             |
| Coordinate multiple tasks into a workflow           | [Pipeline](pipeline.md)     |
| Run a process indefinitely                          | [Service](service.md)       |
| Provide a reusable capability                       | [Component](component.md)   |
| Make an existing function known to the framework    | [Function](function.md)     |
| Manage persistent data                              | [Repository](repository.md) |
