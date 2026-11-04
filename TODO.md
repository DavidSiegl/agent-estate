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
- **CI for the quality gate.** Optional GitHub Actions workflow in the template (`python_gate_ci`), running
  `scripts/gate origin/main` on pull requests.

## Open issues

- **Copier runs `init/apply.py` three times per update.** It also runs it in the scratch renders of the old and new
  template versions. `apply.py` returns early outside a git work tree, which is also why `copier copy` into a
  directory that isn't a git repo silently skips every step.
