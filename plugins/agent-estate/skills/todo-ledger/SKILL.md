---
name: todo-ledger
description: Maintain a repo's TODO.md while working on a dev branch — deleting what was fixed or decided against, and keeping what stays open honest, as refactors and features land. Use whenever a change closes or narrows something the file lists, when a review turns up an issue not being fixed now, when an entry is dropped or an approach rejected, or when reconciling TODO.md before a branch merges. Covers the ledger shape (Planned / Open issues) and the phased-plan shape.
---

# Maintaining TODO.md

The file records what is still open, and only that. Its job is to keep an
honest account of what is actually true now. It is not a changelog and not an
archive: what was fixed lives in the code and the git history, and what was
decided against lives in the history of this file — the commit that deleted the
entry says why. Two shapes are in use; both follow the same rules.

**Ledger**: `## Planned features` → `## Open issues`.

**Phased plan**: a guiding rule, `## Phase 0..N` ordered by
risk/benefit, `## Sequencing`.

## While the work is happening

**Closing something means deleting it.** An entry the change closes leaves the
file entirely, in the same edit — no `Fixed` section, no strike-through, no
"done" marker. The same goes for an entry that stopped applying because the code
it described is gone. What was done belongs in the commit message, and anything
a future reader of the code needs belongs in a comment beside the code.

**An issue that was narrowed but not closed gets rewritten, not removed.**
Describe only what remains, precisely enough that the next reader does not
believe the whole class is handled — "a cluster reached on 6432 has its primary
resolved inside the tool, so two runs naming different entry nodes take
different locks".

**Say what is unverified.** If a change depends on something outside the repo —
a plugin being installed, a server-side project existing, an analyser being
enabled — `Open issues` says what still has to be confirmed: the entry the
change would have closed stays, rewritten to say so, and a dependency no entry
covered gets a new one. Neither is deleted as done.

**Dropping something means deleting it too.** An entry the user decided
against — not worth its cost, superseded, rejected after pricing — leaves the
file like a closed one. Its reason goes in the message of the commit that
deletes it, in a sentence a later `git log -S '<entry lead>' -- TODO.md` reader
can act on: what was decided, by whom, and why. An approach rejected before it
ever became an entry is not added just to record the rejection; its reason goes
in the commit message of the change that chose otherwise, or beside the code if
a reader of that code would otherwise try it.

**Ask whether a drop deserves an ADR.** A commit message is found only by
someone who searches with the entry's own words. When the rejection is not
obvious — a reasonable reader of the code would propose the same thing again —
ask the user whether it gets an ADR in the repo's `docs/adr/` (or wherever the
repo already records its decisions), and write it if they agree, in the format
`mattpocock-skills:domain-modeling` gives: the context, what was rejected, the
date, and why. An easily reversed or plainly not-worth drop gets no ADR.

**Find something you are not fixing now?** It goes in `Open issues` with a file
and function pointer, a description of the failure, and what would close it.

## Mechanics

- **Entries go inside their section.** These files often carry prose footnotes
  after a list or table; appending to the end of the file puts an entry below
  them and breaks the rendering. Check what the section's last line actually is.
- **An old `Fixed`, `Retired`, `Decided against` or `Considered and rejected`
  section** from before these rules: do not add to it, and do not delete it in
  passing — tell the user it is there.
- **Absolute dates.** "Last week" is unreadable six months on.
- **Cross-references rot.** When an entry or section is deleted, grep for
  references to it — "the cleanup mode above" survives long after cleanup stops
  being a planned feature, and "see the open issue" outlives the issue it points
  at.
- **Names rot too.** After a rewrite, `check_disk_space` in the prose is no
  longer the `checkDiskSpace` in the code. Keep identifiers matching what a grep
  would find today; historical names belong only in entries that are explicitly
  historical.

## On a dev branch

**Commit the TODO.md edit with the change it describes.** Not in a follow-up
commit, and never left uncommitted: edits made after the last commit are lost
when the branch merges, silently, because a merge carries commits and not
working trees.

**Reconcile before the branch merges.** Walk the branch's diff and check that
every entry the work closed is gone, and that nothing in `Open issues`
describes code that no longer exists.

**If an entry you did not close has vanished, say so rather than restoring it.**
Entries disappear in rebases, merges and other people's commits. Flag it and let
the owner decide — they may have dropped it deliberately. The same applies in
reverse: if you delete something by accident, report it before quietly putting
it back.

## Before finishing

- Everything this change closed or dropped is deleted from the file.
- Everything it narrowed says what remains.
- Every entry deleted as decided against has its reason in the commit message,
  and the user was asked about an ADR for each one likely to be proposed again.
- No cross-reference points at an entry or section that has gone.
- Identifiers in the prose match the code as it is now.
- The file is committed alongside the code it describes.
