# CONTRIBUTING

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
prefixed with a [gitmoji](https://gitmoji.dev/):

```
<gitmoji> <type>[(scope)][!]: <description>

[optional body — the *why*, not the *what*]
```

Common types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `build`.
Append `!` after the type/scope for a breaking change. Keep the
description short and in the imperative mood ("add", not "added").

Example:

```
:bug: fix(deps): mark docs dependency group optional

A plain `poetry install`/`poetry sync` was pulling in the whole `docs`
group (mkdocs-material, requests, watchdog, ...) by default since
nothing marked it non-default, contradicting the zero-runtime-deps
guarantee and the documented `poetry install --with docs` opt-in.
```
