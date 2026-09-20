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

Commit messages must not reference Claude or any other AI tool, and must
not contain external links to one (e.g. a URL to the Claude site or a
session). That includes `Co-Authored-By:` trailers and "Generated with
..." footers.

Example:

```
:bug: fix(deps): mark docs dependency group optional

A plain `poetry install`/`poetry sync` was pulling in the whole `docs`
group (mkdocs-material, requests, watchdog, ...) by default since
nothing marked it non-default, contradicting the zero-runtime-deps
guarantee and the documented `poetry install --with docs` opt-in.
```

## Branching and releases

`main` always reflects the latest published release. Work for the next
version happens on a dedicated release branch, and `main` only moves when
that version ships.

```
main ─────●───────────────────●──────────  (tag 0.3.0 here)
           \                 /
release/0.3.0 ●──●──●──●────●               (deleted after merge)
               ↑  ↑  ↑
             squashed feature/fix PRs
```

### Branch names

- `release/<version>` — collects everything for one version, e.g.
  `release/0.3.0`. Cut from `main`. A patch release (`release/0.2.1`) is
  cut the same way; there is no separate hotfix flow.
- Everything else (`feat/…`, `fix/…`, `docs/…`) — short-lived topic
  branches, cut from and merged back into the current release branch.

Release branches carry the `release/` prefix so they never collide with
the bare version tags (`0.3.0`) — a branch and a tag with the same name
make `git checkout`/`git push` ambiguous.

### Pull requests

1. Open a PR from your topic branch **into the current release branch**,
   not `main`. (GitHub defaults to `main`; change the base.)
2. The PR title is the commit message — use the
   [format above](#commit-messages). PRs are **squash-merged**, so the
   title becomes the single commit on the release branch and your
   intermediate commits are dropped (you stay credited as the author).
3. Update your branch by rebasing on the release branch, not by merging
   it in. Force-pushing your own topic branch is fine.
4. Include the matching `docs/` update when you change public behaviour.

### Releasing (maintainers)

1. Cut `release/X.Y.Z` from `main`. Merge PRs into it as they land.
2. When ready, add a final commit on the release branch that bumps
   `version` in `pyproject.toml` and adds the notes to
   `docs/release-notes.md`.
3. Run `poetry run pytest` on the release branch and confirm CI is green.
4. Open a PR `release/X.Y.Z` → `main` and **merge it with a merge
   commit** (not squash, not rebase).
5. Tag the merge commit on `main` and push the tag:
   `git tag -a X.Y.Z -m "X.Y.Z" && git push origin X.Y.Z`.
   Tags are bare versions with no `v` prefix, matching existing tags.
6. The tag push triggers the workflows that publish to PyPI and deploy
   the docs. Check both, then delete the release branch.

Fixes discovered after a release go into the next release branch (a patch
or minor bump); every PyPI version corresponds to exactly one release
branch.

### Why this way

- **Squash into the release branch** keeps one clean, conventionally
  formatted commit per change, whatever the contributor's local history
  looks like.
- **Merge commit into `main`** preserves those per-change commits for
  `git log` and release notes, and records that the release branch is
  fully contained in `main`. Squashing would collapse the release into one
  commit and leave the branches diverged; rebasing would rewrite SHAs so
  the release branch and `main` hold different commits for the same
  change.
- **Tag-triggered publishing** means docs and PyPI ship together, from
  the exact commit that was tagged, rather than docs going live on merge
  before the package is available.
