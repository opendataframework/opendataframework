# Tests

## Run all tests

```bash
poetry run pytest
```

## Run a single test file

```bash
poetry run pytest tests/test_context.py
```

## Run a single test

```bash
poetry run pytest tests/test_context.py::test_resolves_transitive_dependencies
```

## Verbose output

```bash
poetry run pytest -v
```
