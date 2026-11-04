# TODO

## Planned features

- **Move the global skills and hooks into the plugin.** The skills in `~/.claude/skills` this setup depends on
  (scratch-issue-tracker, ticket-sync, cross-review, triad, spec-generic, ticket-generic, open-tickets, todo-ledger,
  deep-modules, design-it-twice, external-edits, handover, direct-to-main, reconcile-prs) and the hooks in
  `~/.claude/hooks` (ticket-sync.py, the git pre-push review gate, no-verify-push.sh, context-handover.sh) live in no
  repo, so they have no history and reach no other machine. Moving them is more than a copy:
  - Plugin skills are namespaced (`agent-estate:cross-review`), and the skills, the docs this template renders and
    `~/.claude/CLAUDE.md` name each other unqualified.
  - The skills hard-code `~/.claude/hooks/...` paths; inside a plugin they become `${CLAUDE_PLUGIN_ROOT}/...`.
  - The review gate depends on `core.hooksPath` set through `GIT_CONFIG_*` in `~/.claude/settings.json`'s `env`,
    which a plugin cannot set. Something has to keep pointing it at the plugin's directory, for example a
    SessionStart hook that checks it.
  - The live `~/.claude` setup changes in one step: old copies removed, plugin installed, settings rewritten.

## Open issues

- **Copier runs `init/apply.py` three times per update.** It also runs it in the scratch renders of the old and new
  template versions. `apply.py` returns early outside a git work tree, which is also why `copier copy` into a
  directory that isn't a git repo silently skips every step.
- **The judged code can still tamper with the judge in the same run.** `scripts/gate` runs the pull request's tests
  (conftest, test code, the dependencies in its `uv.lock`) and then gate.py, as the same user, in the same `.venv`.
  Since 2026-11-04 it re-checks gate.py's hash on every run, after the tests, which stops a pull request from
  replacing the cached gate.py for later builds; but a test can still rewrite the `.venv`'s ruff, mypy or coverage, or
  `uv` itself, and so change the verdict on its own pull request, which auto-merge then merges. Review 02 on hyprmuse,
  F3: "the same-process part needs the judge kept out of the judged code's reach, or a recorded decision that it is
  accepted." Closed by running the tests in a separate step that cannot write where gate.py and its tools live (a
  container or a different user on the Jenkins agent), or by the user deciding agents' pull requests are trusted
  that far.
