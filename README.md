# agent-estate

The agent setup I give my repos, kept in one place so it can be applied to a new repo and updated across all of
them.

- **`copier.yml`, `template/`, `init/`**: a [Copier](https://copier.readthedocs.io/) template for the per-repo part:
  the issue tracker (`.scratch/` with optional ticket-sync, or GitHub Issues), the cross-review push gate, and, for uv
  Python projects, octoflow-ai's quality gate as `scripts/gate`. `init/apply.py` does what isn't a template file:
  `.gitignore`, the `CLAUDE.md` import, `pyproject.toml`, git config, labels. Its docstring lists every step.
- **`plugins/agent-estate/`**: a Claude Code plugin whose `init-repo` skill tells Claude how to run the template and
  which answers to ask the user for. `.claude-plugin/marketplace.json` makes this repo its marketplace.

The global half (the skills and hooks in `~/.claude` that this setup relies on: ticket-sync, cross-review, the
pre-push gate) is not in here yet; see `TODO.md`.

## Applying it to a repo

In a clean git repo:

```bash
uvx copier copy --trust gh:DavidSiegl/agent-estate .
```

Copier asks the questions in `copier.yml` and records the answers in `.copier-answers.yml`; commit that file.
`--trust` lets the template run `init/apply.py`.

## Updating

```bash
uvx copier update --trust              # pick up template changes
uvx copier update --trust -d tracker=github   # change an answer
```

The files Copier rendered (`docs/agents/*`, `scripts/gate`) are three-way merged with local edits. `apply.py` reruns
and is idempotent. `CLAUDE.md` only gains an `@docs/agents/README.md` import line, so its own text is never
rewritten.

## Installing the plugin

```text
/plugin marketplace add DavidSiegl/agent-estate
/plugin install agent-estate@agent-estate
```

## Changing the template

A change to a question goes in `copier.yml` and in the `init-repo` skill's table of answers. Before committing, try
a change on a scratch repo: `copier copy` with every combination it touches, then `copier update` on a repo created
from the previous commit. Tag a release (`git tag vX.Y.Z`) so `copier update` moves between versions rather than
commits.
