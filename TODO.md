# TODO

## Open issues

- **`scripts/release raised` names the target two ways in its failures.** Review 06, F6: "`exempt_at` and
  `version_at` print their argument, so the messages now read 'no commit refs/remotes/origin/main', 'cannot read
  .release-exempt at refs/remotes/origin/main' and 'no release version at refs/remotes/origin/main: …'. The rest of
  `raised` says 'main'." Accurate, but it reads inconsistently in auto-merge's comments and Jenkins logs. Closes when
  those helpers' messages name what the caller calls the commit, if that costs less than the parameter it seems to
  need.

### ticket-sync

Paths relative to `plugins/agent-estate/hooks/`.

- **Issues opened by other people are not synced at all.** Decided in dotfiles' cross-review 08 (2026-10-27): five
  rounds showed a two-way sync of issues whose authors can rewrite body, title and marker at will keeps opening holes in
  a ticket store agents act on (findings 1–2, 12–15, 19–21, 23–25, 27–30). `ticket-sync.py` ignores them
  (`Repo._ticket_of`, `Repo._add`). Closed, if they come to matter, by a one-way snapshot import that a maintainer
  triggers with a label (labels need triage rights), tying issue to ticket in the local record only, and never pulling
  the author's later edits.
- **Only the first 100 comments of an issue are seen.** `gh issue list --json comments` returns at most 100 per issue.
