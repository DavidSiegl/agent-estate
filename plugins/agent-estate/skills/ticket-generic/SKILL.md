---
name: ticket-generic
description: Pick up a ticket from `.scratch/<feature-slug>/issues/` and implement it in any repo — claiming it, finding the repo's conventions before writing code, verifying it the way the ticket says, and recording the outcome in the ticket and TODO.md. Use when starting work on a specified ticket, when resuming an interrupted one, or when asked what to work on next in a feature directory. For the BRZ database estate use `brz:ticket` instead.
---

# Implementing a ticket in an unfamiliar repo

Load `scratch-issue-tracker` first for the file layout and the `Status:` values.

## 1 — Pick and claim

Given a number or path, read that file. Given a feature slug, take the frontier:
open, unblocked, unclaimed, lowest number wins. A ticket is unblocked when every
file on its `Blocked by:` line is `resolved`.

**Refuse `ready-for-human` tickets.** Say what made it so — the irreversible
step, the privileged path, the production data — and hand it back. That label is
not advisory; it is the only barrier between an unattended agent and something
that cannot be undone.

**Judge the label, do not just read it.** `ready-for-agent` is not proof that
anyone triaged the ticket: `/to-spec` and `/to-tickets` apply it to everything
they write. Before claiming, check the ticket against the `ready-for-human`
criteria in `scratch-issue-tracker` yourself. If it meets one, set
`Status: ready-for-human`, say which, and hand it back as above.

**Claim before working**, not after: set `Status: claimed` and save. An
interrupted run leaves a claimed ticket, which is the correct trace.

If the ticket is `needs-info`, answer the question or ask the user. Do not
implement past an open question by picking the likelier reading.

## 2 — Find the lane before writing code

You are the visitor here; the repo has already decided most of this.

- **Check for a skill that covers what the ticket touches.** A repo or user skill
  matching this stack or this subsystem outranks anything you would work out from
  the files. Load it before writing.
- **Read `CLAUDE.md` / `AGENTS.md`.** These are rules, not suggestions.
- **Read the nearest sibling.** Open the file that already solves the closest
  problem and follow its structure: error handling, logging, how it is tested,
  how it is wired in. Consistency with the neighbours beats a better idea
  imported from elsewhere.
- **Find the test layer before you need it** — the test directory, the runner in
  the build file, and one existing test to copy the shape of.

If the ticket touches anything irreversible that the spec did not flag, stop and
say so rather than proceeding carefully.

## 3 — Implement

**Stay inside the ticket.** A problem you find outside its scope goes to
`Open issues` in `TODO.md` with a file pointer and what would close it — not into
this diff. Scope creep in a shared repo is how a one-line fix becomes
unreviewable.

**Match the surrounding code.** Comment density, naming, error handling. A file
that checks every error gets that from you too.

**Load `deep-modules` when the ticket adds or reshapes an interface** — a new
function, class or package, a split, a wrapper, a new option or error. Matching
the neighbours does not excuse a shallow module.

**Write the failing case first where the repo has a test layer** —
`mattpocock-skills:tdd` if you want the full loop. Where there is no unit layer
for what you are changing, the verification is the ticket's manual step, and
saying so beats inventing a test harness the ticket did not ask for.

**Do not add a dependency the ticket did not name.** That was a decision at spec
time; if it turns out to be needed, it is a `needs-info` question, not a commit.

## 4 — Verify the way the ticket says

Run what the ticket named, not what is convenient, and run it the way CI does.

Report what actually ran, in the words of the command. A ticket verified only by
reading the diff says so in those words — "not executed" is a legitimate outcome,
a claimed pass is not. If the command fails for reasons unrelated to your change,
say that too, with the output, rather than filtering it out of the report.

## 5 — Record it

**On the ticket**: `Status: resolved`, and under `## Comments` what was actually
done, what was verified, and what was left. Point at the commit.

**In `TODO.md`**, if the repo keeps one: load `todo-ledger` and reconcile the
file with what the work closed, narrowed or decided against, as it says. Commit
that edit **with** the code — edits after the last commit are lost when the
branch merges.

## Before finishing

- The ticket is `resolved` and says what was verified, in the words of what ran.
- Nothing outside the ticket's scope is in the diff.
- `TODO.md` is reconciled and committed alongside the code, where one exists.
- Any lane skill's own "Before finishing" list has been walked.
- The diff has been through a review pass before it goes anywhere shared:
  `/code-review` for correctness, and `cross-review` where the repo has a
  `.scratch/reviews/` directory — its push gate will ask for a record.
