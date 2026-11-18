# TODO

## Open issues

- **`scripts/release raised` names the target two ways in its failures.** Review 06, F6: "`exempt_at` and
  `version_at` print their argument, so the messages now read 'no commit refs/remotes/origin/main', 'cannot read
  .release-exempt at refs/remotes/origin/main' and 'no release version at refs/remotes/origin/main: …'. The rest of
  `raised` says 'main'." Accurate, but it reads inconsistently in CI's logs. Closes when
  those helpers' messages name what the caller calls the commit, if that costs less than the parameter it seems to
  need.

- **Three skills do the job of a mattpocock-skills skill without saying how they differ.** `handover` and
  `/handoff` both write a document for a fresh context to continue from (`handover` is hook-driven and read back after
  `/clear`; `/handoff` writes to `$TMPDIR` for another agent). `spec-generic` covers `/grill-with-docs`, `/to-spec`
  and `/to-tickets` in one pass, interviewing where `/to-spec` refuses to. `ticket-generic` and `/implement` both
  implement a ticket. The pocock ones only run when typed, so they never compete for a trigger, but a user or agent
  picking between them has nothing to go on. Closes when each pair is either merged into one, or the estate skill's
  description names the pocock one and when to prefer each, as `deep-modules` and `design-it-twice` do for
  `codebase-design`.

- **`automate-me`'s `claude-project-dir.mjs` has no test.** Review 01 (add-skills), F12: "no test beside it, where
  the plugin's other scripts each have one (`hooks/readme-sync_test.py`, `hooks/review-gate_test.sh`);
  `projectDirName`/`projectDir` are exported for a test that is not there. The hash-and-prefix fallback (:43-44,
  :76-79) is the part that can drift silently." Closes with a `node --test` file beside it covering the derived name,
  the over-200-character hash and the single-prefix fallback.

- **`gate: own` leaves its JUnit reports unignored.** Review 02, raised and not recorded: "`init/apply.py:52`
  GATE_OUTPUTS['own'] does not gitignore the `test-results*.xml` the own-gate header invites", so a repo whose gate
  writes them shows them as untracked files after every run. Closes when GATE_OUTPUTS['own'] lists `test-results*.xml`
  and `apply.py`'s test covers it.

### ticket-sync

Paths relative to `plugins/agent-estate/hooks/`.

- **Issues opened by other people are not synced at all.** Decided in dotfiles' cross-review 08 (2026-10-27): five
  rounds showed a two-way sync of issues whose authors can rewrite body, title and marker at will keeps opening holes in
  a ticket store agents act on (findings 1–2, 12–15, 19–21, 23–25, 27–30). `ticket-sync.py` ignores them
  (`Repo._ticket_of`, `Repo._add`). Closed, if they come to matter, by a one-way snapshot import that a maintainer
  triggers with a label (labels need triage rights), tying issue to ticket in the local record only, and never pulling
  the author's later edits.
- **Only the first 100 comments of an issue are seen.** `gh issue list --json comments` returns at most 100 per issue.
