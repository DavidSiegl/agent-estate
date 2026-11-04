---
name: ticket-sync
description: Two-way sync between a repo's `.scratch/` tickets and its GitHub issues — edits on either side reach the other, comments come back, issues opened on GitHub become tickets. Use when asked to sync, publish or mirror tickets to GitHub issues, to turn the sync on or off for a repo, when ticket-sync reports a conflict or a failure, or after editing ticket files by hand or with Bash in a repo that syncs.
---

# Ticket sync: `.scratch/` tickets ⇄ GitHub issues

`${CLAUDE_PLUGIN_ROOT}/hooks/ticket-sync.py` does the work. Its module docstring
(`ticket-sync.py --help`) is the reference for how a ticket maps to an issue,
which side wins, and what is trusted. Read it rather than guessing. Load
`scratch-issue-tracker` for the tickets themselves.

## How it runs

Hooks, in a repo that has opted in:

- **Session start**: full sync. Changes and problems arrive as context.
- **Before a Read of a ticket file**: syncs that ticket, so you read it current.
- **After a Write or Edit of a ticket file**: syncs it. If the sync rewrote the
  file (comments pulled), you are told to read it again before the next edit.

By hand, `${CLAUDE_PLUGIN_ROOT}/hooks/ticket-sync.py [repo-dir]` does a full sync and prints
what changed. It is safe to rerun. Run it after changing tickets with `sed` or
another Bash command, which no hook sees, and before reading tickets in bulk
with Bash (`open-tickets` does), when the session has been running a while.

## Opting in is the user's call

`git -C <repo> config agent.ticketSync <owner/name>` turns it on; `git config
--unset agent.ticketSync` turns it off. Set it only when the user asks for that
repo, and confirm `owner/name` with them rather than inferring it from `origin`.
Before the first sync, tell them what it does:

- every open ticket is published to whoever can read the GitHub repo (closed
  ones are left out), and
- every open issue you opened without a ticket is imported under
  `.scratch/github/issues/`, numbered with its issue number.

## Several machines

Each checkout keeps its own record of what it last synced
(`.scratch/.ticket-sync-state.json`), so two machines can sync one repo through
GitHub. A machine joining with an old copy of the tickets gets conflicts, not
overwrites: bring its `.scratch/` level with the newest copy first, or delete
its ticket files and let the sync pull them.

## Conflicts

When the file and the issue both changed since the last sync, nothing is
touched and the report carries a diff (`-` GitHub, `+` file). Merge the two
into the file, then `ticket-sync.py push <file>`. When GitHub's version should
win outright, `ticket-sync.py pull <file>`. When the edits are the user's and
not yours, ask before choosing.

A "number was taken twice" error means another machine created a ticket with
the same `<feature>/<NN>`, or the file was renamed. Renumber the local ticket
when they are different tickets; `push` when it is the same one, renamed.

## Other people's issues

Tickets drive agents, so the sync works only on issues the gh user opened:

- issues anyone else opened, bots included, are ignored: never imported,
  never synced. To work on one, open your own issue for it, or write the
  ticket by hand;
- an open issue you opened on GitHub without a marker is imported as
  `github/<its issue number>`, at the Status its labels or body give
  (`needs-triage` if neither does). An import never overwrites a file; one in
  its way is reported, and moving it out of `.scratch/github/` lets the next
  sync import;
- comments are pulled only from the repo's owner, members and collaborators.

So every machine syncing a repo must be logged in to gh as the same user.

## When it fails

The report quotes gh's error. Fix the cause if it is yours (a wrong
`agent.ticketSync`); an auth failure is the user's (`! gh auth login`). Then
rerun the full sync: it finishes any half-done ticket.

Changing the script: `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/ticket-sync_test.py` runs it
against a fake `gh`.
