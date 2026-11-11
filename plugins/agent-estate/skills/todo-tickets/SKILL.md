---
name: todo-tickets
description: Turn a repo's TODO.md into tickets — sorting each open entry into worth a ticket, unclear, not worth it, or stale, interviewing the user on the unclear ones, and writing tickets in the repo's tracker for what was settled. Use when asked to ticket, triage or work down a TODO.md, to turn its open issues or planned features into tickets, or to find out which TODO.md entries are worth doing.
---

# TODO.md to tickets

`TODO.md` records what is open and what was decided against (`todo-ledger`); a ticket is
the unit an agent picks up (`ticket-generic`). This skill moves the entries
worth doing from the first into the second: a ticketed entry leaves
`TODO.md`, and the ticket carries it from then on. The user decides what is worth
doing; you sort, ground and propose.

## 1 — Find the tracker and the file

Find the tracker as `open-tickets` step 1 does: `.scratch/` tickets (load
`scratch-issue-tracker`) or GitHub issues. Also note whether it **publishes**:
a GitHub tracker, or a `.scratch/` tracker with `git config agent.ticketSync`
set (`ticket-sync`), puts every ticket you write in front of whoever can read
the repo.

Read `<toplevel>/TODO.md`, and `CLAUDE.md` / `AGENTS.md` for the repo's rules.
No `TODO.md`: say so and stop.

## 2 — Collect the open entries

An entry is one top-level bullet (or table row) under a section that lists open
work: `Planned features`, `Open issues` and their subsections, a phased plan's
`Phase N`. Sections that record decisions — `Decided against`,
`Considered and rejected`, `Sequencing`, an old `Fixed` — hold no candidates.

Drop each entry an existing ticket already covers: one whose `Source:` line
quotes it (step 6 writes that line), or an open ticket or issue whose title
plainly names the same problem. List the existing ticket's ID beside it in
step 4 rather than leaving it out silently.

Done when every open entry is either a candidate or matched to a ticket, and
the counts add up to the number of entries.

## 3 — Ground and sort each candidate

Read the code each entry points at before judging it. Entries rot: the function
was renamed, the bug was fixed in passing, the file is gone. Then put the entry
in exactly one bucket:

| Bucket | Rule |
|---|---|
| `stale` | The code no longer has the problem, or the code it describes is gone. |
| `ticket` | It names the failure and one way to close it, you can ground both at `file:line`, and the fix is worth its cost. |
| `unclear` | Closing it needs a decision only the user can make: the entry offers alternatives ("closed by X, or by Y"), one of them is "the user deciding…", the acceptance is not stated, or you cannot tell whether it is worth the cost. |
| `not worth` | The fix plainly costs more than the problem does: cosmetic, conditional on its own cost ("closes when … if that costs less than …"), or guarding a case nobody hits. Say the cost in one line. |

An entry that is several problems in one bullet is sorted per problem; each
becomes its own row.

Done when every candidate sits in one bucket with a one-line reason, and every
`ticket` and `unclear` row cites the `file:line` it was grounded at.

## 4 — Show the buckets and confirm

One table per bucket, in the order `ticket`, `unclear`, `not worth`, `stale`,
then the entries already ticketed. Columns: the entry's lead (its bold title,
or first words), the reason, the grounding. For each `ticket` row add the
triage it will get (step 6).

Then call `AskUserQuestion`: proceed with these buckets, or adjust (under
"Other" they name entries to move). The question says that ticketed entries
leave `TODO.md`, and either that the tracker publishes them or that they will
then exist only in this checkout. Nothing is written before this answer.

## 5 — Interview the unclear ones

Run this in the main thread: a subagent cannot ask, so it guesses, and a guessed
answer reads exactly like a gathered one. The interview rules are
`spec-generic` step 1's — ask only where two readings lead to different code,
and read off the repo whatever you can.

Take the entries one at a time, up to four questions per `AskUserQuestion`
call. Make the options the concrete readings — the entry's alternative closers,
"accept it as is", "not worth doing" — each with what it costs, so the user
picks rather than composes. Each entry ends in one of:

- **Decided** — it joins the `ticket` bucket, with the answer as its
  acceptance.
- **Decided against** — it moves to the file's `Decided against` /
  `Considered and rejected` section with the user's reason and today's date, as
  `todo-ledger` says (a ledger without such a section: ask before adding one).
- **Still open** — the user cannot settle it now. It becomes a ticket with
  `Status: needs-info` naming the question and who can answer it.

Done when every `unclear` entry has one of those three outcomes.

## 6 — Write the tickets

Each `ticket` entry, and each `needs-info` one from step 5, becomes one ticket.

**Where** — GitHub: `gh issue create`, labelled with its triage status; a
repo set up without the GitHub tracker lacks those labels, so create a missing
one first (`gh label create`).
`.scratch/`: a feature directory per `TODO.md` subsection (`### ticket-sync` →
`.scratch/ticket-sync/`), and `.scratch/todo/` for entries under no
subsection; numbers continue after the highest file already in that
`issues/` directory.

**Body**, in this order:

```markdown
# <the problem, as a title>

Status: <triage>
Blocked by: <NN, or ->
Source: TODO.md — "<the entry's lead, verbatim>"

## Problem
<what fails, grounded at file:line; everything the entry said, since step 7
deletes it — review findings and dates included>

## Done when
<what closes it; the interview's answer, where there was one>

## Verification
<the command the repo's CI runs, or the named manual step>
```

Ground and verify as `spec-generic` steps 2 and 4 say. Triage as
`scratch-issue-tracker` says: anything irreversible, privileged, touching
production or publishing outward is `ready-for-human` however clear it is.

## 7 — Reconcile TODO.md

Load `todo-ledger` and edit the file:

- A ticketed entry is **deleted**, and so is one step 2 matched to an existing
  ticket: the ticket is now its record, so it must carry everything the entry
  said (step 6's Problem section).
- A `stale` entry is deleted once the user confirmed it in step 4.
- A decided-against entry moves as step 5 says.
- `not worth` entries stay unless the user asked to decide them against.

Commit the `TODO.md` edit, on its own, in the repo's commit style.

## Before finishing

- Every open entry was ticketed, matched to an existing ticket, decided
  against, deleted as stale, or left with its reason — none dropped silently.
- No ticketed entry is left in `TODO.md`.
- Every ticket has a `Source:` line, a grounded problem, and a verification in
  the repo's own terms.
- Nothing irreversible or outward-facing is `ready-for-agent`.
- `TODO.md` is committed; it names no `.scratch/` path.
- Give the user the list of tickets written, with IDs, and offer `open-tickets`
  to pick the first.
