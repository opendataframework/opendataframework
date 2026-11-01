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
5. Once your PR is merged into the release branch, your topic branch can
   be deleted.

### Releasing (maintainers)

1. Cut `release/X.Y.Z` from `main`.
2. Make the first commit on the release branch the version bump: set
   `version` in `pyproject.toml` and `CITATION.cff` to `X.Y.Z`, and add
   an empty `## X.Y.Z` section to the top of `docs/release-notes.md`.
   Bumping first means everything built from the branch already reports
   the version it will ship as, and PRs have a section to add their notes
   to. Use a `:bookmark: chore(release): bump version to X.Y.Z` commit.
3. Merge PRs into the release branch as they land, each adding its notes
   under the `## X.Y.Z` section.
4. When ready, finalize `docs/release-notes.md` in a last commit on the
   release branch.
5. Run `poetry run pytest` on the release branch and confirm CI is green.
6. Open a PR `release/X.Y.Z` → `main` and **merge it with a merge
   commit** (not squash, not rebase).
7. Tag the merge commit on `main` and push the tag:
   `git tag -a X.Y.Z -m "X.Y.Z" && git push origin X.Y.Z`.
   Tags are bare versions with no `v` prefix, matching existing tags.
8. The tag push triggers the workflow that deploys the docs. The package
   is then published to PyPI manually by the code owner — this will be
   automated by a workflow later.

Fixes discovered after a release go into the next release branch (a patch
or minor bump); every PyPI version corresponds to exactly one release
branch.

### Patching an older version

Fixes normally go into the next release branch. If you must publish a
patch (say `0.2.1`) while a newer release is in development:

- **Newer version not yet tagged:** nothing special. Cut
  `release/0.2.1` from `main`, release it as usual, then merge `main`
  into the in-progress release branch so it picks up the fix.
- **Newer version already tagged on `main`:** `main` has moved on, so
  the patch can't go through it. Cut `maint/0.2` from the `0.2.0` tag,
  fix and tag `0.2.1` there, then cherry-pick the fix into the next
  release branch so it isn't lost. PyPI serves the highest version by
  default, so users on 0.3.0 are unaffected. The docs workflow only
  deploys for the highest tag, so the site keeps showing the newest
  version.

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
- **Tag-triggered docs** ship from the exact commit that was tagged,
  rather than going live on merge before the release is cut.
