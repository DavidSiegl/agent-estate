---
name: init-repo
description: Apply the agent setup (issue tracker, cross-review push gate, quality gate) to a git repo from the agent-estate Copier template, or bring a repo that has it up to date. Use when asked to set up, initialise or bootstrap a repo for agents, to give a repo "the same setup as octoflow/hyprmuse", to change a repo's tracker, review gate or quality gate, or to update a repo after the template changed. Not for writing CLAUDE.md content by hand (`/init`) or for the global skills and hooks in ~/.claude.
---

# Applying the agent setup to a repo

The setup is a Copier template in DavidSiegl/agent-estate. Copier renders `docs/agents/`
(and `scripts/gate` for Python), then runs `init/apply.py`, which edits the files the repo
already owns and sets state outside the tree. `init/apply.py`'s docstring lists each step;
read it rather than guessing what a run will touch. A repo that has the setup carries
`.copier-answers.yml`.

## Before running anything

1. **The repo must exist, be a git repo, and be clean.** apply.py does nothing outside a
   git work tree, and `copier update` refuses a dirty one. Work on a branch, per the
   user's git rules.
2. **Collect the answers from the user, not from guesses.** Each one is a decision about
   their repo:

   | Answer | What it decides | Default to propose |
   |---|---|---|
   | `repo` | the GitHub `owner/name` the issues live on | from `git remote -v`, confirmed by the user |
   | `tracker` | `scratch` (files under `.scratch/`) or `github` (GitHub Issues) | `scratch` |
   | `ticket_sync` | mirror `.scratch/` tickets to GitHub issues: **publishes every open ticket** | ask; never assume yes |
   | `review_gate` | refuse Claude's pushes without a passing cross-review | yes |
   | `python_gate` / `python_package` | octoflow-ai's quality gate, for a uv-managed Python project | yes for such a project |

   `ticket_sync` and the GitHub tracker's labels write to GitHub: say so before running.

## Running it

```bash
uvx copier copy --trust --defaults \
  -d repo=OWNER/NAME -d tracker=scratch -d ticket_sync=false \
  -d review_gate=true -d python_gate=true -d python_package=PKG \
  gh:DavidSiegl/agent-estate .
```

`--trust` is needed because the template runs apply.py. Without `--defaults` Copier asks
interactively, which a Bash tool call cannot answer. The repo is private, so this needs the
user's GitHub credentials for git (`gh auth setup-git`).

To bring a repo up to date with the template, or to change an answer:

```bash
uvx copier update --trust --defaults                 # same answers, newer template
uvx copier update --trust --defaults -d review_gate=false   # change one answer
```

Copier three-way merges template changes into the files it rendered; a conflict shows as
inline markers (or `.rej` files) to resolve before committing.

## After running

- Read every line apply.py printed and pass on anything it reported rather than did (an
  existing `[tool.ruff.lint]` left alone, a gate it could not turn off).
- In a repo whose `docs/agents/` or `CLAUDE.md` were written by hand, compare the old text
  with the rendered one, and move anything repo-specific out of `docs/agents/`: the next
  `copier update` rewrites those files.
- For a Python gate, run `uv run pytest` and `scripts/gate`. Findings already in the
  repo do not block; only lines a change adds count.
- Commit `.copier-answers.yml` with the rest; it is what `copier update` works from.
