---
name: spec-generic
description: Turn a feature request into a grounded spec and numbered implementation tickets under `.scratch/<feature-slug>/`, in any repo — no assumptions about the language, the deploy path or the estate. Use when starting a feature or a refactor, when a request is still vague and needs interviewing before code is written, or when an agreed change needs splitting into independently mergeable tickets. Covers the interview, grounding requirements at file:line, deriving the lane and the verification from the repo itself, and honest triage.
---

# Writing a spec in an unfamiliar repo

The output is files, not a conversation: a spec and its tickets under
`.scratch/<feature-slug>/`. Load `scratch-issue-tracker` for the layout and the
`Status:` values before writing anything.

This runs in the main thread because it needs the user. Do not delegate the
interview to a subagent — a subagent cannot ask a question, so it will guess, and
a guessed requirement reads exactly like a gathered one.

## 1 — Interview until the disagreements surface

Ask only about the parts where two readings lead to different code. Anything you
could read off the repo yourself, read: asking about it spends the user's
attention on something you had access to.

The four that pay in almost any repo:

- **What is the blast radius, and what part of it is irreversible?** Data
  written, messages sent, infrastructure changed, money moved. This decides the
  triage label more than anything else does.
- **What happens on failure — specifically, a failure halfway through?** "It
  retries", "it rolls back" and "it refuses to start next time" are three
  different features. Most of a spec's real content lives here.
- **Who or what runs it, and in what environment?** A human at a terminal, CI, a
  cron entry, a request handler. Decides whether it can prompt, how it gets its
  credentials, and whether anything reads its output.
- **Is this replacing something or sitting beside it?** A replacement needs a
  cutover and a rollback written down; an addition needs to say what it must not
  disturb.

When the user is thinking out loud rather than deciding, `mattpocock-skills:grilling`
is the better tool — come back here once there is something to write down.

## 2 — Ground every requirement

A spec here sits in the same tree as the code, so cite that code:
`src/auth/session.ts:212`, not "the existing session helper". A requirement you
cannot ground is not a requirement yet — it becomes a ticket with
`Status: needs-info` naming the question and who can answer it.

Read before writing, in this order, skipping what the repo does not have:

1. `CLAUDE.md` / `AGENTS.md` — the rules you are expected to already know.
2. `TODO.md` — what is already open; for an idea you are about to propose,
   `git log -S '<key words>' -- TODO.md` finds the commit that dropped it, if
   one did, and why (see `todo-ledger`).
3. `CONTEXT.md`, `docs/adr/`, `README` — the vocabulary and the standing decisions.
4. The actual call sites. Delegate a wide search to `Explore` when the change
   spans many files; keep the writing here.

**Say what the change must not break**, and find it rather than guess it: grep
for callers of what you are changing, and read the CI config for what the repo
already promises to keep green. In a library, the public surface is the contract;
in a service, its callers are.

## 3 — Name the lane, with its reason

Repos have a grain. Find it before choosing: the build files (`Makefile`,
`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`), the CI config, and
what the neighbouring files that solve a similar problem already do.

Then write the lane into the spec — the language, the layer, and the existing
module it extends — with one sentence on why. "New file under `internal/`,
because every other long-running worker lives there" is a lane; "in Python"
is not.

**A new language, framework or third-party dependency is the user's decision,
not a detail of the spec.** Raise it explicitly, with what it buys and what it
costs to carry. The default answer is the one already in the repo.

## 4 — Split into tickets

One file per ticket, `issues/NN-<slug>.md`, numbered from `01`.

**Independently mergeable.** A ticket that only makes sense alongside another one
is one ticket, not two. Use a `Blocked by:` line when the ordering is real, and
keep it to real ordering — a `Blocked by` chain through every ticket is a single
ticket wearing a costume.

**Each ticket names its verification, in the repo's own terms.** Derive the
command from the repo rather than inventing one: whatever CI runs is the
verification that counts. `make test`, `npm test`, `uv run pytest tests/`,
`cargo test`, a linter, or a named manual step. A fifth option exists — "cannot
be verified outside production" — and it is itself a finding worth writing down.

**Triage honestly.** `ready-for-agent` means an agent can finish it unattended
and be wrong without anyone getting hurt. Anything that is irreversible, that
runs privileged, that touches production data or that publishes outward is
`ready-for-human` even when it is fully specified. The label is the only barrier
between an unattended agent and a mistake that cannot be undone.

## Before finishing

- Every requirement cites a `file:line`, or is a `needs-info` ticket.
- The lane is named with its reason, and any new dependency was raised with the
  user rather than assumed.
- Every ticket says how it is verified, in a command the repo actually runs.
- Nothing irreversible or production-touching is `ready-for-agent`.
- The spec says what must not break, and what the rollback is.
- Nothing committed points at `.scratch/` — it is gitignored.
