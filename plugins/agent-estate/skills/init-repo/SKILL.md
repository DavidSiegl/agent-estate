---
name: init-repo
description: Apply the agent setup (issue tracker, cross-review push gate, quality gate) to a git repo from the agent-estate Copier template, or bring a repo that has it up to date. Use when asked to set up, initialise or bootstrap a repo for agents, to give a repo "the same setup as octoflow/hyprmuse", to change a repo's tracker, review gate or quality gate, or to update a repo after the template changed. Not for writing CLAUDE.md content by hand (`/init`).
---

# Applying the agent setup to a repo

The setup is a Copier template in DavidSiegl/agent-estate. Copier renders `docs/agents/`
(and `scripts/gate` for Python), then runs `init/apply.py`, which edits the files the repo
already owns and sets state outside the tree. `init/apply.py`'s docstring lists each step;
read it rather than guessing what a run will touch. A repo that has the setup carries
`.copier-answers.yml`.

## Before running anything

1. **The repo must exist, be a git repo, and be clean.** `copier copy` fails outside a git
   work tree (apply.py refuses it), and `copier update` refuses a dirty one. Work on a branch, per the
   user's git rules.
2. **Collect the answers from the user, not from guesses.** Each one is a decision about
   their repo:

   | Answer | What it decides | Default to propose |
   |---|---|---|
   | `repo` | the GitHub `owner/name` the issues live on | from `git remote -v`, confirmed by the user |
   | `tracker` | `scratch` (files under `.scratch/`) or `github` (GitHub Issues) | `scratch` |
   | `ticket_sync` | mirror `.scratch/` tickets to GitHub issues: **publishes every open ticket** | ask; never assume yes |
   | `review_gate` | refuse Claude's pushes without a passing cross-review | yes |
   | `gate` / `python_package` | the quality gate: `python` (octoflow-ai's, for a uv-managed Python project, measuring `python_package`), `own` (a starter `scripts/gate` the repo fills in, any language) or `none` | `python` for such a project, else `own` |
   | `ci` | where the gate runs on pull requests: `none`, `jenkins`, `github-actions` | ask; Jenkins needs a job the user sets up |
   | `jenkins_agent_label` / `jenkins_status_login` | the Jenkins agents allowed to build, and the App login whose status counts | `untrusted`; the login has no default: ask, as `<app-slug>[bot]` |
   | `jenkins_notify_email` | the address Jenkins mails on a build that did not pass and on the first passing one after it; empty sends none | ask; empty |
   | `automerge` | merge pull requests into main once CI passes, with no human | ask; it changes who merges |
   | `release` / `jenkins_release_credential` | CI releases every merge into main that raises the version (`scripts/release`); on Jenkins, the credential holds a token that may create releases | ask; `GitHub-Agents` |

   `ticket_sync` and the GitHub tracker's labels write to GitHub: say so before running.

## Running it

```bash
uvx copier copy --trust --defaults \
  -d repo=OWNER/NAME -d tracker=scratch -d ticket_sync=false \
  -d review_gate=true -d gate=python -d python_package=PKG \
  gh:DavidSiegl/agent-estate .
```

`--trust` is needed because the template runs apply.py. Without `--defaults` Copier asks
interactively, which a Bash tool call cannot answer.

To bring a repo up to date with the template, or to change an answer:

```bash
uvx copier update --trust --defaults                 # same answers, latest release
uvx copier update --trust --defaults -d review_gate=false   # change one answer
```

Both copy and update take the newest `vX.Y.Z` tag, not `main`: template work merged since the last tag
reaches no repo until it is tagged (the README's "Changing the template"). A change you just merged into
the template and want in a repo now is a tag for the user to push. `--vcs-ref=<sha>` is for a trial on a
scratch copy only, never committed: the repo's next plain update would refuse to "downgrade" from that
sha to the newest tag until a later one exists.

Copier three-way merges template changes into the files it rendered; a conflict shows as
inline markers (or `.rej` files) to resolve before committing.

## After running

- Read every line apply.py printed and pass on anything it reported rather than did (an
  existing `[tool.ruff.lint]` left alone, a gate it could not turn off).
- In a repo whose `docs/agents/`, `CLAUDE.md` or `AGENTS.md` were written by hand, compare the
  old text with the rendered one, and move anything repo-specific out of `docs/agents/`: the
  next `copier update` rewrites those files. apply.py only appends one line to `CLAUDE.md` (an
  import) and to `AGENTS.md` (a pointer, for tools other than Claude Code), and leaves an
  `AGENTS.md` that is a symlink alone.
- For a Python gate, run `uv run pytest` and `scripts/gate`. Findings already in the
  repo do not block; only lines a change adds count.
- Commit `.copier-answers.yml` with the rest; it is what `copier update` works from.
- With `ci` set: the CI side is the user's (the README's "Jenkins" section lists it). Once CI reports on a pull
  request, `init/github-rules.py` sets the `ci-cd` ruleset; it needs Administration: write, which the agents' token
  may lack, in which case give the user the command. Not before: until CI reports, the ruleset blocks every merge.
  On an update of a repo with `automerge` whose ruleset is already set, it needs running again all the same: a
  ruleset set before the template required strict status checks lacks them, and auto-merge relies on them (the
  README's "Updating").
- With `automerge` set, when the change adds `automerge.yml`: tell the user its pull request is theirs to merge.
  GitHub runs the workflow from `main`'s copy, so nothing merges this one, and agents never merge one themselves.
