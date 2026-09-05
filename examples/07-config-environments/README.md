# 07 — Config Environments

One `Greeter` `@Component`, one `app/` package, two environments —
`config/dev/` and `config/prod/` — that change its behavior without changing
a single line of code. `Project.from_config` takes a directory here instead
of a single file: every `*.toml` inside it is loaded and deep-merged.

This isolates the concept covered in [`docs/config.md`](../../docs/config.md):
there is no environment flag anywhere in the framework — the *path* passed to
`Project.from_config` is the environment. Each environment directory is free
to split its settings across multiple files (`project.toml`, `greeter.toml`,
...) the same way a real project would split `storage.toml`/`api.toml`
instead of one giant file.

## Structure

```
07-config-environments/
├── config/
│   ├── dev/
│   │   ├── project.toml   # [project] name
│   │   └── greeter.toml   # [greeter] greeting = "Yo", name = "Dev"
│   └── prod/
│       ├── project.toml
│       └── greeter.toml   # [greeter] greeting = "Hello", name = "Production"
├── main.py                # entry point — starts a Project per environment
└── app/
    ├── __init__.py        # imports components.py so the decorator registers at startup
    └── components.py      # Greeter — @Component, reads config.get("greeter")
```

## Run it

```bash
cd examples/07-config-environments
python main.py
```

Expected output:

```
[dev] Yo, Dev!
[prod] Hello, Production!
```

`main.py` starts a separate `Project` per environment — the framework
supports multiple `Project` instances in the same process (see CLAUDE.md's
"No global mutable state" constraint), each with its own resolved `Greeter`
built from that environment's merged config.
