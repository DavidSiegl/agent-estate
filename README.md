# agent-estate

The agent setup I give my repos, kept in one place so it can be applied to a new repo and updated across all of
them.

- **`copier.yml`, `template/`, `init/`**: a [Copier](https://copier.readthedocs.io/) template for the per-repo part:
  the issue tracker (`.scratch/` with optional ticket-sync, or GitHub Issues), the cross-review push gate, and, for uv
  Python projects, octoflow-ai's quality gate as `scripts/gate`. `init/apply.py` does what isn't a template file:
  `.gitignore`, the `CLAUDE.md` import, `pyproject.toml`, git config, labels. Its docstring lists every step.
- **`plugins/agent-estate/`**: the Claude Code plugin for the half that is not per repo: the skills every coding
  session uses (cross-review, triad, the `.scratch/` tracker and ticket-sync, spec- and ticket-generic, todo-ledger,
  readme-sync, deep-modules, design-it-twice, external-edits, handover and more), the `init-repo` skill that runs the
  template, and the hooks in `hooks/hooks.json`: the review gate's pre-push hook and the guard that keeps a push from
  skipping it, ticket-sync, the README check that refuses a pull request into `main` changing what the README names
  without the README (`hooks/readme-sync.py`'s docstring has the rule), and the context handover.
  `.claude-plugin/marketplace.json` makes this repo its marketplace.

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

In `~/.claude/settings.json` (dotfiles keeps it there), so that every machine has it:

```json
{
  "extraKnownMarketplaces": {
    "agent-estate": { "source": { "source": "github", "repo": "DavidSiegl/agent-estate" }, "autoUpdate": true }
  },
  "enabledPlugins": { "agent-estate@agent-estate": true },
  "permissions": { "deny": ["Bash(gh pr merge:*)"] }
}
```

then `claude plugin install agent-estate@agent-estate` once per machine. Interactively, the same is
`/plugin marketplace add DavidSiegl/agent-estate` and `/plugin install agent-estate@agent-estate`.

A plugin's own settings may set only `agent` and `subagentStatusLine`, so two things stay with the user:

- **The `gh pr merge` deny rule**, above: in a repo with `automerge`, auto-merge merges pull requests, never an
  agent. (`core.hooksPath` for the review gate does not need the user's settings: `hooks/git-hooks-path.sh` sets
  it at session start through `$CLAUDE_ENV_FILE`, for the commands Claude runs only.)
- **The context handover's token count.** The status line must write the last response's input tokens to
  `$XDG_RUNTIME_DIR/claude-context-tokens-<session_id>` (`hooks/context-handover.sh`'s header has the details);
  dotfiles' `statusline-command.sh` does. Without it the handover reminder never fires.

Plugin skills are namespaced, as in `agent-estate:cross-review`.

## Changing the template

A change to a question goes in `copier.yml` and in the `init-repo` skill's table of answers. Before committing, try
a change on a scratch repo: `copier copy` with every combination it touches, then `copier update` on a repo created
from the previous commit. Tag a release (`git tag vX.Y.Z`) so `copier update` moves between versions rather than
commits.
