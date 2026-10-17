# 08 — Function

Three plain functions — `restock`, `low_stock` and `format_report` — each made
framework-aware with a single `@Function` decorator. Nothing else about them
changes: no class, no base type, no new call convention.

This isolates the concept covered in
[`docs/function.md`](../../docs/function.md): `@Function` is the on-ramp for
code that already exists as functions. The decorator returns the function
unchanged, so calling it directly behaves exactly as before. Called through the
`Context` instead, a parameter annotated with a type the `Context` manages —
here the `Inventory` `@Component` — is injected, and only the remaining
arguments are passed. `format_report` takes no managed type at all; it is still
registered and callable by name, it just has no dependencies.

A function can also be a dependency itself. `Reorder`, a `@Task`, declares
`low_stock` in its constructor as `Annotated[Callable[..., list[str]], low_stock]`
and receives it with `inventory` already filled in — so the task never mentions
`Inventory`, and is free to call the parameter `find_shortages`.

## Structure

```
08-function/
├── config.toml           # no custom keys needed for this example
├── main.py                # entry point — calls the functions four different ways
└── app/
    ├── __init__.py        # imports all modules so decorators register at startup
    ├── components.py      # Inventory — @Component, the shared state
    ├── functions.py       # restock, low_stock, format_report — @Function
    └── tasks.py           # Reorder — @Task with low_stock injected
```

## Run it

```bash
cd examples/08-function
python main.py
```

Expected output:

```
call('function.low-stock')       -> ['apple']
call('function.restock', ...)    -> 12
get(low_stock)(threshold=15)     -> ['apple', 'banana']
get(format_report)(...)          -> apple, banana
execute('task.reorder')          -> ['apple', 'banana']
restock(Inventory(), cherry, 1)  -> 1
```

`main.py` shows all four ways to call a registered function:

- `project.context.call("function.restock", item=..., quantity=...)` — by
  key, with keyword arguments. `inventory` is injected.
- `project.context.get(low_stock)(threshold=15)` — by function, getting it back
  with `inventory` already filled in.
- `project.context.execute("task.reorder")` — injected: the task holds the same
  bound function `get(low_stock)` returns, and calls it in `execute()`.
- `restock(Inventory(), "cherry", 1)` — directly, exactly as before the
  decorator was added. Nothing is injected, which is why the tests in
  `tests/examples/function/` need no framework setup at all.
