---
name: scratch-issue-tracker
description: The local markdown issue tracker used across repos — specs and tickets as files under `.scratch/<feature-slug>/`, triaged with a `Status:` line. Use whenever a skill or agent says to publish to the issue tracker, fetch the relevant ticket, apply a triage label, or claim and resolve work; when writing a spec or splitting one into implementation tickets; or when picking up work and needing to find the spec that describes it. Covers the file layout, the five triage labels, the wayfinding map/child shape, and what being untracked means for agents.
---

# The `.scratch/` issue tracker

Specs and tickets live as markdown files in the repo working tree, not in Jira or
Bitbucket. A ticket is a file; its triage state is a line inside it.

## Layout

```
.scratch/
├── <feature-slug>/
│   ├── spec.md                the spec
│   └── issues/
│       ├── 01-<slug>.md       one file per ticket, numbered from 01
│       └── 02-<slug>.md
└── reviews/                   present only where the review gate is on
    └── 01-<branch-slug>.md    one file per branch under review
```

- One feature per directory.
- **One file per ticket, never a combined tickets file.** Numbers start at `01`
  and are never reused.
- Triage state is a `Status:` line near the top of each issue file.
- A review record is keyed on a branch, not a feature, so `reviews/` sits beside
  the feature directories rather than inside one. Its state line is `Verdict:`,
  deliberately not `Status:` — the wayfinding scan reads `Status:` and a review
  is not a ticket. See `cross-review`.
- Conversation appends to the bottom under a `## Comments` heading.

## Triage labels

Five roles, used verbatim as `Status:` values. The left column is the vocabulary
the `mattpocock-skills:*` skills speak in; when one of them names a role, write
the right-hand string.

| Role in the skills | `Status:` value | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | Not yet evaluated |
| `needs-info` | `needs-info` | Blocked on an answer from the user |
| `ready-for-agent` | `ready-for-agent` | Fully specified; an AFK agent can take it |
| `ready-for-human` | `ready-for-human` | Needs a human — prod access, a judgement call, a destructive path |
| `wontfix` | `wontfix` | Will not be actioned |

`ready-for-human` is not a formality. Anything irreversible, anything that runs
privileged, touches production data or publishes outward is `ready-for-human`
even when it is fully specified — the label is the only barrier between an
unattended agent and a mistake that cannot be undone. A repo's own spec and
ticket skills may name more.

## Operations

**"Publish to the issue tracker"** — create a file under
`.scratch/<feature-slug>/`, creating the directory if needed.

**"Fetch the relevant ticket"** — read the file at the referenced path. The user
normally passes the path or the issue number.

**Ground each requirement.** A spec written here sits next to the code it
describes, so cite `file:line` rather than paraphrasing. A requirement you could
not ground becomes a `needs-info` ticket, not a confident sentence.

## Wayfinding

Used by `/wayfinder`. The **map** is one file with a **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child**: `.scratch/<effort>/issues/NN-<slug>.md`. A `Type:` line records
  `research` / `prototype` / `grilling` / `task`; a `Status:` line records
  `claimed` / `resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked
  when every file it lists is `resolved`.
- **Frontier**: scan `issues/` for files that are open, unblocked and unclaimed;
  lowest number wins.
- **Claim**: set `Status: claimed` and save *before* starting work.
- **Resolve**: append the answer under `## Answer`, set `Status: resolved`, then
  append a context pointer (gist + link) to Decisions-so-far in `map.md`.

## `.scratch/` is untracked

It is gitignored. That is deliberate — specs are working memory, not deliverables —
but it has three consequences that bite silently:

- **It does not reach anyone else.** Nothing here survives a fresh clone or
  appears in a pull request. The exception is a repo that mirrors its tickets
  to GitHub issues (`ticket-sync`): there, every open ticket is published. A
  decision that outlives the feature belongs in `TODO.md` or an ADR (see
  `todo-ledger`), not only here.
- **It does not follow a worktree.** `git worktree add` checks out tracked files
  only, so an agent running in a worktree starts with no `.scratch/` at all. Pass
  such an agent the ticket's *content*, not its path.
- **Nothing committed may point at it.** A path in `docs/`, a code comment or a
  `Jenkinsfile` referencing `.scratch/` is a dangling reference for every reader
  but you.

## Adopting it in a repo

A repo uses it when git ignores `.scratch/` (`git check-ignore -q .scratch`). To add it elsewhere: add `.scratch/`
to that repo's `.gitignore`, and nothing else — the convention is this file, and
repos should point here rather than restate it.

`mkdir -p "$(git rev-parse --show-toplevel)/.scratch/reviews"` is a separate
opt-in: it switches the push gate on for that repo, and it does not require the
rest of the tracker. Build that path from the toplevel — the gate reads only the
repo root, and because the ignore pattern is unanchored, a copy made one
directory down is ignored by git and invisible to the gate at the same time.
