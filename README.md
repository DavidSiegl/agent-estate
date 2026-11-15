# agent-estate

The agent setup I give my repos, kept in one place so it can be applied to a new repo and updated across all of
them.

- **`copier.yml`, `template/`, `init/`**: a [Copier](https://copier.readthedocs.io/) template for the per-repo part:
  the issue tracker (`.scratch/` with optional ticket-sync, or GitHub Issues), the cross-review push gate, and, for a
  project in any language, a quality gate as `scripts/gate` (octoflow-ai's for a uv Python project, else the repo's
  own), run by Jenkins or GitHub Actions, with optional auto-merge and releases (`scripts/release`). `init/apply.py`
  does what isn't a template file: `.gitignore`, the `CLAUDE.md` import, `pyproject.toml`, git config, labels. Its
  docstring lists every step.
- **`plugins/agent-estate/`**: the Claude Code plugin for the half that is not per repo: the skills every coding
  session uses (cross-review, triad, the `.scratch/` tracker and ticket-sync, spec- and ticket-generic, todo-ledger and todo-tickets,
  readme-sync, unslop, stale-worktrees, make-pr-easy-to-review, principle-never-block-on-the-human, teach, how, why, babysit, fix-ci, get-pr-comments, automate-me, deep-modules, design-it-twice, external-edits, handover and more), the `init-repo` skill that runs the
  template, the `chore` agent in `agents/`, which takes fully specified work (run the tests, apply a given edit) on
  Sonnet instead of the session's model, and the hooks in `hooks/hooks.json`: the review gate's pre-push hook and the guard that keeps a push from
  skipping it, ticket-sync, the README check that refuses a pull request into `main` changing what the README names
  without the README (`hooks/readme-sync.py`'s docstring has the rule), the version check that refuses one changing
  a plugin without raising the `version` in its `.claude-plugin/plugin.json`, without which installs never load the
  change (`hooks/plugin-version.py`'s docstring has the rule), and the context handover.
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

The files Copier rendered (`docs/agents/*`, `scripts/gate`) are three-way merged with local edits, except a
repo-owned gate (`gate: own`): Copier writes its starter `scripts/gate` once and never again. `apply.py` reruns
and is idempotent. `CLAUDE.md` only gains an `@docs/agents/README.md` import line, so its own text is never
rewritten.

## CI and auto-merge

`gate` picks the quality gate: `python`, octoflow-ai's, for a uv-managed Python project; `own`, a starter
`scripts/gate` whose header is the contract CI relies on (exit 0, 1 or 2 on a change since BASE), for the repo to fill
with its own checks in any language; or `none`, which also leaves out CI.

With `ci` set, pull requests run `scripts/gate` in CI; with `automerge`, `.github/workflows/automerge.yml` merges one
into `main` once CI passed on its head commit (the generated `docs/agents/README.md` says what holds one back). It
checks who reported the result itself, so it is safe before any ruleset exists. It merges with a repository secret,
`AUTOMERGE_TOKEN`: a fine-grained personal access token of the owner, limited to the repo, with Contents, Pull
requests and Workflows read and write (the header of the generated `automerge.yml` says why not the workflow's own
token). Until it is set, nothing merges:

```bash
gh secret set AUTOMERGE_TOKEN -R OWNER/NAME
```

GitHub runs the workflow from `main`'s copy (its header), so it merges nothing before `automerge.yml` is on `main`:
the pull request that first adds it is merged by hand, and one whose CI passed before then, or before the secret was
set, waits for a new CI result.

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
  restricted per node with the Job Restrictions plugin, with `git` and what `scripts/gate` needs on it (for
  `gate: python`: `uv`, `curl`, `shellcheck` and `actionlint`), and also `gh` when `release` is on.
- the **JUnit** plugin, 1.51 or later for the `junit` step's options (`skipMarkingBuildUnstable` came in 1.51), which
  shows the JUnit reports `scripts/gate` leaves (the Jenkinsfile's `post` names them), and with `jenkins_notify_email`
  set, the **Email Extension** plugin and a working mail server in Jenkins's configuration: the job then mails that
  address when a build fails, is unstable or is aborted, and when one passes after it.

### Releases

With `release`, a merge into `main` whose version has no GitHub release yet is released as `v<version>` by
`scripts/release publish`, and CI's Version stage (Jenkins) or step (GitHub Actions) fails a pull request into `main`
that changes a released path without raising the version; auto-merge checks that again right before merging, so a
pull request overtaken by another that raised to the same version is held. The version is read from the first of
`pyproject.toml`, `Cargo.toml`, `package.json` or `VERSION` that holds one. `scripts/release`'s header is the rule:
which file, which paths are exempt, and how versions compare.

On GitHub Actions, the Gate workflow's `release` job releases on each push to `main` that passes the gate, with the
workflow's own token, so it needs no secret; a merge auto-merge makes with `AUTOMERGE_TOKEN` triggers it. On Jenkins,
the job needs:

- a **string credential** named by `jenkins_release_credential` (default `GitHub-Agents`), holding a GitHub token
  that may create releases on the repo (Contents: read and write). It is bound on the same agent that builds the
  agents' pull requests, whose code can read it, so it must be a token the agents already hold, as
  `GitHub-Agents` is; never one they should not have;
- optionally a repo-owned, executable **`scripts/package`** that builds what the release attaches and leaves it as
  plain files directly in `dist/release/`, on either CI. The Package stage or step runs it on a pull request that
  touches a released path, and the release again on `main` when the version is due, without the token, right before
  it publishes; without it the release has only GitHub's source archives;
- optionally a repo-owned **`.release-exempt`**: more paths whose changes reach no user, one git glob pathspec per
  line, beside the built-in docs, tests and CI.

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
from the previous commit, and run `python3 tests/release_test.py` and `python3 tests/gate_test.py`. Tag a release (`git tag vX.Y.Z`) so `copier update` moves between versions rather than
commits.
