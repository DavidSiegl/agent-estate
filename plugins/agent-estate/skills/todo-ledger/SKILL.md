---
name: todo-ledger
description: Maintain a repo's TODO.md while working on a dev branch — deleting what was fixed, keeping what stays open honest, and recording what was decided against, as refactors and features land. Use whenever a change closes or narrows something the file lists, when a review turns up an issue not being fixed now, when an approach is considered and rejected, or when reconciling TODO.md before a branch merges. Covers the ledger shape (Planned / Open issues) and the phased-plan shape.
---

# Maintaining TODO.md

The file records what is still open and what was decided against. Its job is
to stop the same questions being re-litigated and to keep an honest account of
what is actually true now. It is not a changelog: what was fixed lives in the
code and the git history, not here. Two shapes are in use; both follow the same
rules.

**Ledger**: `## Planned features` → `## Open issues`.

**Phased plan**: a guiding rule, `## Phase 0..N` ordered by
risk/benefit, `## Considered and rejected`, `## Sequencing`.

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

**Record what you decided against, with the reason.** The phased plan keeps a
`## Considered and rejected` section for exactly this: *"Recorded so these do not
get re-litigated."* An evaluated-and-declined dependency, a rewrite that was
priced and dropped — these cost real time to re-derive. A ledger has no such
section; ask the user before adding one rather than filing the decision under a
heading that means something else.

**Find something you are not fixing now?** It goes in `Open issues` with a file
and function pointer, a description of the failure, and what would close it.

## Mechanics

- **Entries go inside their section.** These files often carry prose footnotes
  after a list or table; appending to the end of the file puts an entry below
  them and breaks the rendering. Check what the section's last line actually is.
- **An old `Fixed` or `Retired` section** from before this rule: do not add to
  it, and do not delete it in passing — tell the user it is there.
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

- Everything this change closed is deleted from the file.
- Everything it narrowed says what remains.
- Anything decided against is recorded with its reason.
- No cross-reference points at an entry or section that has gone.
- Identifiers in the prose match the code as it is now.
- The file is committed alongside the code it describes.
