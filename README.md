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

## CI and auto-merge

With `ci` set, pull requests run `scripts/gate` in CI; with `automerge`, `.github/workflows/automerge.yml` merges one
into `main` once CI passed on its head commit (the generated `docs/agents/README.md` says what holds one back). It
merges with the workflow's own token, so it needs no secret, and it checks who reported the result itself, so it is
safe before any ruleset exists.

Once CI reports on pull requests, protect `main` with the `ci-cd` ruleset (needs a gh token with Administration:
write on the repo; the docstring says what it sets):

```bash
init/github-rules.py OWNER/NAME --check continuous-integration/jenkins/pr-head --app-id 5456635   # Jenkins
init/github-rules.py OWNER/NAME --check gate --app-id 15368                                       # GitHub Actions
```

### Jenkins

The generated `Jenkinsfile` expects, as octoflow-ai's does (its `docs/quality-gate.md`, "Jenkins setup", has the
reasons):

- a **Multibranch Pipeline** job on the repo, "Discover branches" set to exclude branches that are also filed as
  PRs, and "Discover pull requests from origin" building the pull request's head, so the status is `pr-head`;
- a **GitHub App credential** as the checkout credential, the App installed on the repo with Contents: read, Pull
  requests: read and Commit statuses: read and write. Its login is the `jenkins_status_login` answer;
  auto-merge trusts statuses from that login only. Keep the credential in the job's folder store, not the global one;
- an **agent labelled `jenkins_agent_label`** (default `untrusted`) that holds nothing an agent should not have,
  restricted per node with the Job Restrictions plugin, with `uv`, `git`, `curl`, `shellcheck` and `actionlint` on
  it.

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
