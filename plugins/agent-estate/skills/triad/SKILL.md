---
name: triad
description: Cross-validate a ticket across three separate Claude sessions — a product session that owns the spec and acceptance criteria, an implementer that challenges the spec before building, and a reviewer that reads only the diff — so that every artifact is checked by a session that did not produce it, and scope disputes are ruled on by neither party. Use when a `ready-for-agent` ticket will be implemented unattended, when a spec is contested or its acceptance is not obvious from tests, when asked to spawn or coordinate implementer/reviewer/product sessions, or when a ticket carries `## Acceptance`, `## Challenge` or an `Accepted:` line. Extends `cross-review`, which is the two-session core; not a replacement for it.
---

# Three-session cross-validation

`cross-review` buys one thing: a reviewer that did not write the code. It leaves
three gaps, and the triad exists to close them:

1. **Nobody validates the spec.** The session that wrote it is the session that
   reads it into code, so a wrong requirement is implemented faithfully.
2. **The code is checked by reading, never by running against what was asked.**
   The reviewer checks the diff against the ticket; nobody checks the delivered
   behaviour against the acceptance criteria as a black box.
3. **The implementer rules on its own review.** A finding of the form "the ticket
   did not ask for that" is decided by the party that benefits from the answer.

Three roles, each producing one artifact and validating another's:

| Role | Produces | Validates | May write |
|---|---|---|---|
| **Product** (P), the home session | spec, tickets, `## Acceptance`; rulings on scope | delivered behaviour, by running the criteria | `.scratch/<slug>/` — never code, never the review record |
| **Implementer** (I), spawned | code, tests, the record's facts | the spec, by challenging it before claiming | code; a ticket's `Status`, `## Challenge`, `## Comments`; the record's `Base`/`Files`/`Tickets` — never `spec.md`, `Accepted:`, `Head:`, `Verdict:` |
| **Reviewer** (R), spawned | findings, `Head:`, `Verdict:` | the diff, against the ticket | `.scratch/reviews/**` only |

The code gets two decorrelated lenses — R reads it, P runs it — and every line
in the tracker has exactly one owner. That is the cross-validation.

## When it earns its cost

Three sessions per ticket is expensive. Use the triad when:

- the ticket is `ready-for-agent` — nobody human will read the implementer's
  interpretation of the spec, so a session has to;
- the spec is contested, or "done" is not obvious from the tests;
- the user asks for separate sessions by name.

Skip it for a one-file fix with an obvious test — `cross-review` alone. And a
`ready-for-human` ticket has no implementer session at all; the human
implements, and review still applies.

## The separation rules

Everything below follows from these, and they are the part not to bend.

- **Separate `claude` invocations.** Not subagents, and the only `--resume`
  permitted is a role resuming *itself*. A session that can read how another
  role argued will absorb the argument.
- **Every hand-off is a file path and a command line.** Facts on disk, never a
  summary in a prompt. Load `scratch-issue-tracker` for the layout.
- **Write scope is structural where a role is spawned** — `--allowedTools` /
  `--disallowedTools` on the launch line — and by instruction in the home
  session, which has whatever the user has.
- **Nothing is closed by argument.** A finding closes on a counter-fact at
  `file:line`; a scope dispute on a spec line; a challenge on an amended ticket.
- **The user is the bus by default.** Each role prints the next command and
  stops. Unattended mode, where P runs the other two, is below.

## The ticket carries the state

`templates/ticket.md` in this skill directory is the shape; copy it. Beyond the
tracker's `Status:` and `Blocked by:` it adds:

| Line / section | Written by | Meaning |
|---|---|---|
| `Accepted:` | **P only** | `not yet` / `yes (<sha>, <date>)` / `no — see Comments`. Deliberately not `Status:`, which the frontier scan reads. |
| `## Acceptance` | P, before I is launched | Numbered criteria `A1..An`, each observable without reading the code |
| `## Challenge` | I, before claiming | What the spec could not tell it; `none — checked A1–An against file:line` is a valid entry, an absent section is not |
| `## Comments` | anyone | Conversation, rulings, rounds |

**An acceptance criterion is something P can run.** "Given X, when Y, then Z",
followed by how to check it: a command, or a named manual observation. A
criterion that only a code reader could confirm is a review concern, not
acceptance — move it to `## Verification`. A criterion nobody can check outside
production is a `needs-info` before it is a criterion.

The criteria do three jobs: I writes tests for them, R checks each has a test,
and P runs them at the end. They are frozen once I is launched; changing one is
a round (below).

## Role P1 — specify

Load `brz:spec` (BRZ estate) or `spec-generic`, and write `## Acceptance` into every
ticket as part of that. Then print the implementer's launch line and stop:

```bash
ROOT=$(git rev-parse --show-toplevel) || exit 1
cd "$ROOT" && claude "/triad implement $ROOT/.scratch/<slug>/issues/NN-<slug>.md" \
  --disallowedTools "Edit(/$ROOT/.scratch/**/spec.md)"
```

The rule is absolute — `/` followed by `$ROOT`, which itself starts with `/` —
for the reason `cross-review` gives for the reviewer's: a relative rule resolves
against the session's current directory, so once the implementer `cd`s into a
subdirectory it stops matching, and the spec is editable after all.

From here until acceptance, P does not read the diff. It will be tempted to,
when a challenge or a ruling comes back; the answer to both lives in the spec,
not in the code.

## Role I1 — challenge, then implement

Given a ticket path, you are the implementer, and the spec is the thing under
test first.

1. **Challenge before claiming.** Read the spec, the ticket, and every
   `file:line` it cites. Write `## Challenge` with anything of these three
   kinds: a requirement you cannot ground in the code; an acceptance criterion
   you cannot see how to make observable or test; two readings of a sentence
   that lead to different code. If any is real, set `Status: needs-info`, name
   who answers, and **stop** — do not implement past it by picking the likelier
   reading. If none, write the explicit `none` with what you checked.
2. **Implement** via `brz:ticket` or `ticket-generic`: claim, build, verify. Every
   `A<n>` gets a test where the lane has a test layer, and `## Comments` names
   which test covers which criterion, or says which criterion has no test and why.
3. **Commit, open the review record** — `cross-review` Role 1, facts only — and
   print the reviewer's launch line from that skill. Stop.

Never touch `spec.md`, `Accepted:`, `Head:` or `Verdict:`. If the spec is wrong,
that is a challenge, not an edit.

## Role R — review

`cross-review` Role 2, unchanged, plus one pass the record must show:

**Acceptance conformance.** For each `A<n>` on the ticket, name the test or
verification step that covers it. A criterion with no covering test is a
finding — `A3 has no covering test` — at the severity of the behaviour it
leaves unverified, not a note.

Read-only, as ever. The reviewer does not run the acceptance criteria; that is
P's lens, and running them here would collapse two lenses into one.

## Role I2 — adjudicate

`cross-review` Role 3 — `fixed`, `deferred`, `rejected` with a counter-fact —
with one addition:

| Disposition | What it requires |
|---|---|
| `escalated` | The finding turns on **whether the ticket required it**, not on what the code does. One line each for the reviewer's position and yours, then hand it to P. |

The test for `escalated` is simple: if your rejection would begin "the ticket
didn't ask for", you do not get to decide it. You are the party that benefits
from that answer.

## Role P2 — rule on scope

Given an `escalated` finding, rule by pointing at a line, never by reading the
code:

- **Required** — cite the spec or ticket line that requires it. The finding is
  real; I fixes it in a round.
- **Not required** — cite the absence, then decide: amend the ticket (a round,
  with the criterion added) or decline it, with the reason, in the ruling
  below; it goes in `TODO.md` only if it stays open for later work
  (`todo-ledger`).

Write the ruling on the record finding as `Ruling (P): …` and under the ticket's
`## Comments`. A ruling that cannot point at a line means the spec is
ambiguous, and the fix is to the spec.

## Role P3 — accept

After `Verdict: pass`, run every `A<n>` — actually run it, as a black box: the
command, the CLI, the observed output. Do not read the diff first, and do not
accept on the strength of the implementer's `## Comments` — that is I's claim
of verification, and acceptance exists to check it.

- Every criterion holds: `Accepted: yes (<head-sha>, <date>)`.
- One does not: `Accepted: no — see Comments`, the failing criterion and what
  was observed under `## Comments`, `Status:` back to `ready-for-agent`. The
  implementer picks it up as a round. An acceptance failure is not a review
  finding; it does not go on the record.

Only after writing the line may P read the diff, and only to sharpen a failing
criterion's description.

## Unattended mode

For `ready-for-agent` tickets P may run I and R itself, from Bash, instead of
printing the lines for the user. The record and the ticket are still the state;
treat each session's printed output as a status line, not as evidence.

```bash
ROOT=$(git rev-parse --show-toplevel) || exit 1
cd "$ROOT" || exit 1

# implementer — a hard allowlist under -p, so every tool it needs is named
out=$(claude -p "/triad implement $TICKET" --output-format json \
  --allowedTools Read Grep Glob Bash Edit Write Skill Agent Task \
  --disallowedTools "Edit(/$ROOT/.scratch/**/spec.md)") || exit 1
impl=$(jq -r '.session_id' <<<"$out")

# reviewer — cross-review's Role 1 launch line, taken from that skill with its
# logging. It is not copied here, so the two cannot drift apart.

# adjudication — the implementer resuming itself, the one permitted resume
claude -p --resume "$impl" "/triad adjudicate $RECORD" \
  --allowedTools Read Grep Glob Bash Edit Write Skill Agent Task \
  --disallowedTools "Edit(/$ROOT/.scratch/**/spec.md)"
```

`Agent` and `Task` both, and the absolute deny rule, for the reasons in
`cross-review`'s launch-line notes.

The bare `Bash` on the implementer is the cost of unattended work, and the
`ready-for-agent` label is the judgement that it is affordable. If it is not,
the ticket was mislabelled — hand it back rather than narrowing the allowlist
until the implementer cannot run its tests. Hooks run in the spawned sessions
too, so the push gate applies to the implementer's pushes.

## Rounds

- **Code changed** — a `cross-review` round; R updates `Head` and `Verdict`.
- **Spec or a criterion changed** — P appends `## Round N` to the ticket saying
  what changed and which ruling or challenge caused it; I re-challenges that
  ticket before continuing. Criteria never change silently.
- **Acceptance failed** — `Status: ready-for-agent` with the observation; I
  treats it as a new ticket cycle, challenge included, because a criterion that
  failed after a passing review is evidence that one of them was misread.

## Before finishing a ticket

- `## Challenge` exists, with an explicit `none` or a resolved `needs-info`.
- The record carries `Verdict: pass` for the head sha, written by R.
- Every `escalated` finding has a `Ruling (P):` that cites a line.
- `Accepted: yes` names the same head sha, written by P, from running the
  criteria — not from reading the diff or the implementer's report.
- No role wrote a line that belongs to another. If one did, the line is void
  and its owner rewrites it.
