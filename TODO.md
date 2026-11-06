# TODO

## Open issues

- **Copier runs `init/apply.py` three times per update.** It also runs it in the scratch renders of the old and new
  template versions. `apply.py` returns early outside a git work tree, which is also why `copier copy` into a
  directory that isn't a git repo silently skips every step.
- **The judged code can still tamper with the judge.** `scripts/gate` runs the pull request's tests (conftest, test
  code, the dependencies in its `uv.lock`) and then gate.py, as the same user, in the same `.venv`. Since 2026-11-04
  it checks gate.py's hash on a fresh copy after the tests, in a directory created after them, and runs it with
  `python -I`; that stops a pull request from replacing the cached gate.py. Everything else that user can write is
  still open, within the run and beyond it: the `.venv`'s ruff, mypy, coverage, interpreter and `.pth` files (which
  `-I` does not stop), `uv`, `~/.gitconfig` (gate.py runs git), `~/.config/uv/uv.toml` and `~/.cache/uv`, none of
  which `cleanWs()` reaches; the checkout's `.git/config` and `.git/info/attributes` (an attribute like `*.py -diff`
  hides every changed line from gate.py); `scripts/gate` itself, which bash reads while it runs; a process the tests leave running,
  which can swap the copy of gate.py after its check; and a `conftest.py`, whose hooks run in any build. A test can so change the verdict
  on its own pull request, which auto-merge then merges, or on later builds on that agent. Review 02 on hyprmuse,
  F3: "the same-process part needs the judge kept out of the judged code's reach, or a recorded decision that it is
  accepted." Closed by running the tests where they cannot write what gate.py and its tools use (a container, or a
  different user on the Jenkins agent), or by the user deciding agents' pull requests are trusted that far.

- **Two auto-merge runs at the same moment can merge two raises to the same version.** With `release`,
  `automerge.yml` re-checks the raise against `main` right before merging (hyprmuse's review 26, F1), but two runs that
  both check before either merges both pass, and the second merge ships unreleased. Closed by strict status checks on
  the `ci-cd` ruleset (`init/github-rules.py`), with auto-merge updating a branch that is behind.

- **The release token sits on the Jenkins agent that runs agents' code.** Review 01, F1: "The Release stage binds a
  Contents: read and write token (`jenkins_release_credential`) in the job that builds agents' pull requests on the
  `untrusted` agent." A pull request can bind it in its own Jenkinsfile, or plant a `gh` that the next Release on
  `main` runs. Packaging, though run outside `withCredentials` (F15), can also reach it, as review 01's F16 found: as
  the same user in the same workspace, scripts/package and its build dependencies can leave a process that reads
  `scripts/release publish`'s `/proc/<pid>/environ`, or rewrite `scripts/release` or `.git/config` before publish
  runs them. Harmless only while the token is one the agents already hold, which the README requires. Closed by
  releasing from a job on a trusted agent that builds `main` only, with a token agents never hold. GitHub Actions'
  `release` job (in `gate.yml`) already runs so: on `main` only, on a fresh runner, with the workflow's own token.

- **The CI files each repeat `scripts/release`'s exit-status dispatch.** Review 02, F7: "the exit-status dispatch on
  `scripts/release changed` / `due` is now copied in three CI files" (the Jenkinsfile's Package and Release stages,
  `gate.yml`'s Package step and release job), so a change to that exit contract must be repeated in each. Closed by
  subcommands that act instead of answering (say `scripts/release package-if-changed BASE`), leaving CI one call
  whose failure is the only outcome to handle.

- **GitHub Actions shows no test results.** Jenkins publishes the JUnit reports `scripts/gate` leaves (the
  Jenkinsfile's `post`); `gate.yml` ignores them, so on that CI a failing test is visible only in quality.md
  and the log. Closed by a step in `gate.yml` that turns them into a check run or the job summary, without a
  third-party action the token would have to trust.

### ticket-sync

Paths relative to `plugins/agent-estate/hooks/`.

- **Issues opened by other people are not synced at all.** Decided in dotfiles' cross-review 08 (2026-10-27): five
  rounds showed a two-way sync of issues whose authors can rewrite body, title and marker at will keeps opening holes in
  a ticket store agents act on (findings 1–2, 12–15, 19–21, 23–25, 27–30). `ticket-sync.py` ignores them
  (`Repo._ticket_of`, `Repo._add`). Closed, if they come to matter, by a one-way snapshot import that a maintainer
  triggers with a label (labels need triage rights), tying issue to ticket in the local record only, and never pulling
  the author's later edits.
- **Only the first 100 comments of an issue are seen.** `gh issue list --json comments` returns at most 100 per issue.
- **A linked worktree syncs into its own `.scratch/`.** `agent.ticketSync` lives in the shared git config, so a session
  in a worktree restores every open ticket into the worktree's fresh `.scratch/`. Closed by resolving the main checkout
  (`git rev-parse --git-common-dir`) in `opted_in()`.

## Decided against

- **A gate for any language as commands in Copier answers** (say `test_command`, `lint_command`), rendered into the
  Jenkinsfile and `gate.yml`. Rejected for the generic template (2026-11-05): the logic would live in answer strings,
  untested and unlintable, duplicated across both CI files. A repo-owned `scripts/gate` (`gate: own`) holds it instead,
  tested and run alike locally and in CI.
- **Per-language presets** (`gate: rust`, `gate: node`, …). Rejected with the above: no fixed set covers "any project",
  and each preset is upkeep for a language few repos use. Only octoflow-ai's Python gate is the template's, because it
  is shared estate tooling, not a preset.
