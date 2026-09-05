# 04 — Task + Pipeline

Two `@Task`s, `ExtractItems` and `TransformItems`, composed into a single
`@Pipeline`, `SetupPipeline`. Each `Task` is a bounded, self-contained unit of
work — `SetupPipeline` doesn't transform any data itself, it just calls the
two tasks in order.

This isolates the concept covered in [`docs/task.md`](../../docs/task.md) and
[`docs/pipeline.md`](../../docs/pipeline.md): a `Task` implements a single
`execute()` method and runs to completion; a `Pipeline` depends on `Task`s (and
other `Pipeline`s) through its constructor exactly like any other component,
and its own `execute()` just delegates to theirs in order. The two tasks share
state through `ItemStore`, a plain `@Component` — the same DI pattern from
example 02, reused here for coordination rather than data access.

## Structure

```
04-task-and-pipeline/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — runs SetupPipeline through the Context
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── components.py      # ItemStore — @Component, shared buffer
    ├── tasks.py            # ExtractItems, TransformItems — @Task
    └── pipelines.py        # SetupPipeline — @Pipeline
```

## Run it

```bash
cd examples/04-task-and-pipeline
python main.py
```

Expected output:

```
ExtractItems.execute    -> ['apple', 'banana', 'cherry']
TransformItems.execute  -> ['APPLE', 'BANANA', 'CHERRY']

Pipeline result: ['APPLE', 'BANANA', 'CHERRY']
```

`main.py` resolves `SetupPipeline` by class via
`project.context.get(SetupPipeline)` and calls `.execute()` on it — the typed
access pattern described in [`docs/project.md`](../../docs/project.md).
