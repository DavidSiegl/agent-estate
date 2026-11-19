---
name: open-tickets
description: List a repo's open tickets, show them to the user grouped and ranked, and ask which to implement — then hand each chosen one to `ticket-generic`. Use when asked what tickets are open, what is left to do in a repo, or to pick the next ticket(s) to work on; also for a GitHub repo's open issues when it has no `.scratch/` tracker.
---

# Open tickets: list, ask, implement

The user picks; you never start one they did not choose.

## 1 — Find the tracker

The repo is the argument (a path or `owner/name`), else the current repo. For a
local repo, run every command with `git -C <repo>` and read every path from its
`git rev-parse --show-toplevel`, never from the current directory.

- **`.scratch/` tracker** (`git check-ignore -q .scratch` succeeds and
  `<toplevel>/.scratch/*/issues/` exists): load `scratch-issue-tracker` for the
  layout and the `Status:` values.
- **GitHub issues** (an `owner/name`, or a local repo with no `.scratch/`
  tickets): `gh issue list --repo <owner/name> --state open --limit 200 --json
  number,title,body,labels,assignees`. If `gh` fails, show its error and stop;
  an auth failure is the user's to fix (`! gh auth login`). If it returns 200
  issues, the list is truncated: say so in step 3.

Neither present: say so and stop.

## 2 — Collect every open ticket

For a `.scratch/` tracker, read the head of every `.scratch/*/issues/*.md`: the
`# ` title line, `Status:` and `Blocked by:`. A ticket is **open** unless its
status is `resolved` or `wontfix`. Its ID is `<feature>/<NN>`
(`opsbox0/05`): that is what the user types back.

Put each open ticket in a **lane**: the first row of this table that matches.
The order matters, since a claimed ticket can also be blocked.

| Lane | Rule |
|---|---|
| `claimed` | `Status: claimed`: another session may be on it right now |
| `human` | `ready-for-human` |
| `needs-info` | `needs-info`, `needs-triage`, no `Status:` line, or any value not named here; the reason column shows the actual value |
| `blocked` | any ticket on its `Blocked by:` line is not `resolved` |
| `takeable` | everything else, i.e. `ready-for-agent` and unblocked |

`Blocked by:` is free-form: `-` and blank mean nothing, and you will also see
other features (`trivy-images 04`, `homelab-lint/01`) and notes in parentheses.
Look up each ticket it names and read its status. When a reference doesn't
resolve to a file, the ticket counts as `blocked`, and the table says which
reference.

For GitHub issues, use the same table with these stand-ins: an assignee for
`claimed`; its triage label for `Status:`, where no triage label counts as
`ready-for-agent`; an open issue named in the body as "blocked by #N" or
"depends on #N" for `Blocked by:`.

Done when every open ticket sits in exactly one lane, and the number of open
ticket files (or issues returned) equals the number of rows.

## 3 — Show them

One table per lane, in the order `takeable`, `needs-info`, `blocked`, `human`,
`claimed`, ranked by feature and then by number within each. Leave out empty
lanes. Columns: ID, title, and the reason it sits in that lane (its blockers,
its open question in a few words, the step that makes it human). Below the
tables, give one line of counts per lane and the number of resolved and wontfix
tickets you left out.

## 4 — Ask

Call `AskUserQuestion` with `multiSelect: true`. The options are up to four
`takeable` tickets, lowest feature/number first, with the title as the
description. When fewer than two exist, fill the remaining places with
`needs-info` tickets ("answer its question") and then with "Nothing for now".
Note in the question that they can type other IDs under "Other".
pi has no question tool: there, list the same options numbered, say they may
name other IDs, end the turn and wait for the answer.

When nothing is `takeable` or `needs-info`, skip the question: after the tables,
say that nothing is ready for an agent, and ask in prose whether they want to
drive one of the `human` tickets or clear a blocker.

What a choice means:

- **`human`**: `ticket-generic` hands these back, so tell the user which step
  needs them, then ask whether they want to drive it now with you assisting.
- **`blocked`**: name the blocker and offer to work on it instead.
- **`claimed`**: ask before taking it over. Other sessions commit in the same
  worktree, so the claim may belong to one that is editing those files right
  now.
- **`needs-info`**: put the ticket's open question to the user; once it is
  answered, the ticket is takeable.
- **"Nothing for now"**: stop.

## 5 — Implement the chosen ones

One at a time, in the order the user gave. Each one goes through
`ticket-generic`, from claiming to recording, with its own commit. Before
starting the next, re-read its `Status:` and `Blocked by:`: the ticket you just
finished may have unblocked it, or another session may have claimed it.

A GitHub issue goes through `ticket-generic` too, with the issue standing in
for the ticket. Every step applies except the edits to a ticket file, which has
no counterpart: leave the issue's assignees, labels and comments alone. Put
`Fixes #N` in the commit message.

After the last one, give the list again with only what is still open, so the
user can see what remains.
