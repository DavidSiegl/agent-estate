# TODO

## Open issues

- **Copier runs `init/apply.py` three times per update.** (#23) It also runs it in the scratch renders of the old and new
  template versions. `apply.py` returns early outside a git work tree, which is also why `copier copy` into a
  directory that isn't a git repo silently skips every step.
- **Two auto-merge runs at the same moment can merge two raises to the same version.** (#22) With `release`,
  `automerge.yml` re-checks the raise against `main` right before merging (hyprmuse's review 26, F1), but two runs that
  both check before either merges both pass, and the second merge ships unreleased. Closed by strict status checks on
  the `ci-cd` ruleset (`init/github-rules.py`), with auto-merge updating a branch that is behind.

- **The CI files each repeat `scripts/release`'s exit-status dispatch.** (#18) Review 02, F7: "the exit-status dispatch on
  `scripts/release changed` / `due` is now copied in three CI files" (the Jenkinsfile's Package and Release stages,
  `gate.yml`'s Package step and release job), so a change to that exit contract must be repeated in each. Closed by
  subcommands that act instead of answering (say `scripts/release package-if-changed BASE`), leaving CI one call
  whose failure is the only outcome to handle.

- **GitHub Actions shows no test results.** (#19) Jenkins publishes the JUnit reports `scripts/gate` leaves (the
  Jenkinsfile's `post`); `gate.yml` ignores them, so on that CI a failing test is visible only in quality.md
  and the log. Closed by a step in `gate.yml` that turns them into a check run or the job summary, without a
  third-party action the token would have to trust.
- **The own-gate starter tells every repo what Jenkins does with its files.** (#20) Review 05, F4: the starter's header
  "still says 'which Jenkins publishes' whatever `ci` is. The own starter is not a `.jinja` file, so it renders
  unchanged under `ci: github-actions` or `ci: none`." Closes with the starter rendered as `.jinja`, its CI sentences
  under `ci`; only new renders get it, since `copier update` never rewrites the starter.
- **`scripts/release raised` names the target two ways in its failures.** Review 06, F6: "`exempt_at` and
  `version_at` print their argument, so the messages now read 'no commit refs/remotes/origin/main', 'cannot read
  .release-exempt at refs/remotes/origin/main' and 'no release version at refs/remotes/origin/main: …'. The rest of
  `raised` says 'main'." Accurate, but it reads inconsistently in auto-merge's comments and Jenkins logs. Closes when
  those helpers' messages name what the caller calls the commit, if that costs less than the parameter it seems to
  need.
- **A plugin change merged without a version raise still never reaches installs.** (#24)
  `plugins/agent-estate/hooks/plugin-version.py` checks only a Claude `gh pr create`; a pull request opened in the
  browser, or a push straight to `main`, is not checked. Closed by a CI check on this repo's own pull requests:
  `scripts/release`'s Version step already refuses a released path changed without a raise, but reads the version
  from `pyproject.toml` and the like, not from `plugin.json`, and this repo runs none of its own template's CI.

### ticket-sync

Paths relative to `plugins/agent-estate/hooks/`.

- **Issues opened by other people are not synced at all.** Decided in dotfiles' cross-review 08 (2026-10-27): five
  rounds showed a two-way sync of issues whose authors can rewrite body, title and marker at will keeps opening holes in
  a ticket store agents act on (findings 1–2, 12–15, 19–21, 23–25, 27–30). `ticket-sync.py` ignores them
  (`Repo._ticket_of`, `Repo._add`). Closed, if they come to matter, by a one-way snapshot import that a maintainer
  triggers with a label (labels need triage rights), tying issue to ticket in the local record only, and never pulling
  the author's later edits.
- **Only the first 100 comments of an issue are seen.** `gh issue list --json comments` returns at most 100 per issue.
- **A linked worktree syncs into its own `.scratch/`.** (#21) `agent.ticketSync` lives in the shared git config, so a session
  in a worktree restores every open ticket into the worktree's fresh `.scratch/`. Closed by resolving the main checkout
  (`git rev-parse --git-common-dir`) in `opted_in()`.

## Decided against

- **Keeping the judged code out of the judge's reach.** `scripts/gate` runs a pull request's tests and then gate.py
  as the same user in the same `.venv`; since 2026-11-04 it checks gate.py's hash on a fresh copy after the tests and
  runs it with `python -I`, but the tests can still rewrite the `.venv`'s tools and `.pth` files, `uv` and its
  config and cache, `~/.gitconfig`, the checkout's `.git/config` and `.git/info/attributes`, `scripts/gate` itself,
  or leave a process running, and so change the verdict on their own pull request (hyprmuse's review 02, F3).
  Running the tests in a container or as a different user was rejected (2026-11-11): agents' pull requests are
  trusted that far.
- **A trusted Jenkins job for releases.** The Release stage binds `jenkins_release_credential` on the `untrusted`
  agent that builds agents' pull requests, where a pull request's Jenkinsfile, a planted `gh`, or a process left by
  scripts/package can reach it (review 01, F1, F16). Releasing from a job on a trusted agent that builds `main` only
  was rejected (2026-11-11): the README requires the token to be one the agents already hold, so reaching it gains
  nothing. GitHub Actions' `release` job already runs on `main` only, on a fresh runner, with the workflow's own token.
- **Dropping `version` from `plugin.json`** so installs follow every commit instead of a raised version. Rejected
  (2026-11-06): a raise makes each release a deliberate step, and `plugins/agent-estate/hooks/plugin-version.py`
  holds sessions to it.
- **A gate for any language as commands in Copier answers** (say `test_command`, `lint_command`), rendered into the
  Jenkinsfile and `gate.yml`. Rejected for the generic template (2026-11-05): the logic would live in answer strings,
  untested and unlintable, duplicated across both CI files. A repo-owned `scripts/gate` (`gate: own`) holds it instead,
  tested and run alike locally and in CI.
- **Per-language presets** (`gate: rust`, `gate: node`, …). Rejected with the above: no fixed set covers "any project",
  and each preset is upkeep for a language few repos use. Only octoflow-ai's Python gate is the template's, because it
  is shared estate tooling, not a preset.
- **One helper for a Jenkins pull request's fetch and merge base**, shared by the Jenkinsfile's Change stage and
  `scripts/release raised` (hyprmuse's review 31, F2). Rejected (2026-11-06): the two render on separate answers (a
  Jenkinsfile with `release` off has no `scripts/release`, which with `ci: github-actions` has no Jenkinsfile), and
  `scripts/release` is plain shell its tests run straight from `template/`, so the helper would be a new script in
  every Jenkins repo to save two lines. Each place instead says the other reads the target alike. GitHub Actions takes
  the base by SHA and has no copy.
