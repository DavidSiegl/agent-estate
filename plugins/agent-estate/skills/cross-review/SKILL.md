---
name: cross-review
description: Run a branch past a reviewer that is a different Claude session, and record the verdict where it survives a /clear — opening a review record, running the reviewer from a fresh context, and adjudicating its findings. Use before pushing a dev branch, when the review gate refuses a push, when asked to review work another session implemented, or when a review record under `.scratch/reviews/` needs a verdict. Distinct from the review passes themselves (`brz:ops-review` in the BRZ estate, `/code-review` elsewhere); this is who runs them and what closes them.
---

# Cross-session review

The review passes answer *how* a branch is reviewed — `brz:ops-review` in the
BRZ estate, `/code-review` and a spec-conformance pass elsewhere. This answers
*who* reviews it, *where the verdict lives*, and *what it takes to close a
finding*.

## Why a record, and why a second session

Fanning out to subagents buys a context that did not write the code. That
isolation is then spent at the collation step, where the session that wrote the
change decides which criticism of it survives. A record and an adjudication rule
put that decision on disk instead of inside the author's head.

Three consequences shape everything below:

- **The reviewer is a separate `claude` invocation**, not a subagent and never a
  `--continue`. A reviewer that can read how the change was argued for will
  absorb the argument.
- **The verdict outlives the conversation.** A review that exists only in a
  transcript is gone at the next `/clear`, and it was expensive to derive.
- **The implementer never writes the `Head` or `Verdict` lines.** Those are the
  reviewer's. Everything else in the record is the implementer's to maintain.

## The record

```
<main checkout>/.scratch/reviews/NN-<branch-slug>.md
```

**The path is anchored at the main checkout's toplevel, not at your working
directory.** The gate reads `.scratch/reviews/` there and at the toplevel of the
checkout the push runs in, so a `.scratch/reviews/` created one directory down is
a directory the gate will never read. It will also not show up in `git status` to
tell you so: the `.gitignore` entry is `.scratch/`, unanchored, which ignores the
name at every depth. In a linked worktree, `git rev-parse --show-toplevel` is the
worktree's own path, not the main checkout's, which is the parent of
`git rev-parse --path-format=absolute --git-common-dir`. Build the path from that
every time rather than trusting the shell's cwd.

Numbered from `01` per repo, never reused. `templates/record.md` in this skill
directory is the shape; copy it rather than retyping it.

| Line | Written by | Meaning |
|---|---|---|
| `Base:` | implementer | merge-base sha, and the ref it came from |
| `Stakes:` | implementer | `high` / `normal` / `low`, and the fact in the spec or ticket that sets it — see below |
| `Head:` | **reviewer** | the sha actually reviewed |
| `Verdict:` | **reviewer** | `requested` / `findings` / `pass` / `blocked` |
| `Reviewer:` | reviewer | model and date — this is the cross in cross-validation |
| `Passes:` | reviewer | which passes ran, and which did not |

`Verdict: pass` means every finding is dispositioned, not that none were raised.

## Stakes and severity

How hard a branch is reviewed follows from what a defect that slips through
costs, not from how much code there is. The implementer sets `Stakes:` from a
fact in the spec or ticket; the reviewer may raise it, saying why, and never
lowers it.

| Stakes | When | Round 1 | A later round records |
|---|---|---|---|
| `high` | production data, security, a deploy, a check that fails builds or refuses pushes | every pass the diff earns, `/code-review high` | `blocking` and `should-fix` |
| `normal` | any other code that runs | `/code-review high` | `blocking` only |
| `low` | output that only informs (a report-only check, a log line), docs, a tool only the user runs | `/code-review medium` | `blocking` only |

Every finding carries one severity:

- **`blocking`** — run as written, the code gives a wrong result, crashes, fails
  what it should pass or passes what it exists to catch, on an input the spec
  puts in scope; or the diff departs from the spec.
- **`should-fix`** — a real defect with a smaller consequence: an input the spec
  does not clearly cover, a test that cannot fail, a comment or doc that states
  something false.
- **`nit`** — nothing is false or broken: wording, names, wrap, a copied block,
  a style rule from `CLAUDE.md`.

Severity decides which findings a later round may record and when a finding is
checked (see Rounds). It never lets a finding skip a disposition.

`.scratch/` is gitignored — see `scratch-issue-tracker`. So a record never
reaches a colleague, never appears in a pull request, and dies with the working
tree. That is why a finding that is *not* being fixed goes to `TODO.md`, which is
committed, and not only here.

## Role 1 — open (the implementing session)

**Commit first.** The reviewer reads `git diff`, so anything uncommitted is
invisible to it, and a review of a tree that has since moved is worse than none.

```bash
ROOT=$(git rev-parse --show-toplevel) || exit 1   # not a repo: there is nothing to gate
# The records' home: the main checkout's, also when ROOT is a linked worktree.
REVIEWS=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.scratch/reviews
BASE=$(git merge-base HEAD origin/dev)   # or this repo's review base (brz:estate lists the BRZ ones)
mkdir -p "$REVIEWS"
git diff --name-only "$BASE"
```

A session whose cwd is the parent of several repos is not in a repo at all.
`git rev-parse` fails there, and the record belongs under whichever repo the
branch lives in, not beside them.

Fill in `Base`, `Stakes`, `Files`, `Tickets`, and nothing else. **Facts only — no summary
of what you did or why.** The framing is precisely what the isolation exists to
keep out; `brz:ops-review` states the same rule for subagents and it matters more
here, because this record is all the reviewer gets.

Then launch the reviewer yourself and wait for it. A headless `claude -p` started
from the Bash tool is a separate invocation with a fresh context, which is all
the isolation needs; the user does not have to run it.

```bash
LOG=<your scratchpad>/review-NN.jsonl
cd "$ROOT" && claude -p "/cross-review $REVIEWS/NN-<slug>.md" \
  --output-format stream-json --verbose \
  --allowedTools Read Grep Glob Bash Skill Agent Task "Edit(/$REVIEWS/**)" \
  > "$LOG" 2> "$LOG.err"
```

Run it with `run_in_background: true`, so the harness wakes you when it exits,
and with the sandbox disabled: the nested CLI needs the API and its own
`~/.claude` state. A review that fans out to the ops passes takes about four minutes.

Details in that line, each of which fails loudly if you get it wrong:

- **`cd "$ROOT"` and an absolute record path.** The reviewer's `git diff`
  resolves against the directory it starts in, which for a worktree is the
  worktree, not the checkout that holds the record.
- **`Edit(/$REVIEWS/...)`, an absolute rule.** `$REVIEWS` already starts with `/`, so
  the rule reads `//home/...`, which is the permission syntax for an absolute
  path. A relative `Edit(.scratch/reviews/**)` resolves against the reviewer's
  *current* directory, so once its Bash `cd`s into a subdirectory, the write to
  its own record is denied.
- **`--allowedTools` goes last.** It is variadic, so a prompt placed after it is
  swallowed as another tool name and the session aborts with *"Input must be
  provided either through stdin or as a prompt argument"*.
- **`Edit(...)`, never `Write(...)`.** `Edit` rules cover every file-editing
  tool; a `Write(...)` rule matches nothing, and the CLI warns that it is not
  matched by file permission checks.
- **`Agent` and `Task` both.** The subagent tool is `Agent` in current CLIs and
  `Task` in older ones; without it the reviewer cannot fan out to its review
  agents.

While it runs, check on it from the log rather than guessing:

```bash
jq -r 'select(.type=="assistant") | .message.content[]
  | if .type=="tool_use" then "TOOL \(.name) \(.input|tostring|.[0:120])"
    elif .type=="text" then "TEXT \(.text[0:160])" else empty end' "$LOG" | tail
jq -r 'select(.type=="user") | .message.content[]?
  | select(.type=="tool_result" and .is_error==true) | .content|tostring|.[0:200]' "$LOG"
```

A tool denied by the allowlist shows up in the second query; stop the run and fix
the launch line rather than letting it review with a pass missing.

**The verdict lives in the record, not the log.** When the run exits, first ask
the log whether it ran at all, then read the record:

```bash
jq -r 'select(.type=="result") | "\(.is_error) \(.api_error // "-") \(.result[0:160])"' "$LOG"
grep -m1 '^Head:' "$REVIEWS/NN-<slug>.md"
```

The run failed when `is_error` is `true`, or when `Head:` is not the sha you
asked it to review. `subtype` reads `success` even then. A usage limit gives
`usage_limit_reached` and the reset time in the result text, after a few
seconds and two turns. The record keeps the previous round's `Verdict`, so a
round-2 failure still reads `findings`. Read `$LOG.err` too, say why to the
user, and relaunch the same round after the reset.

With `-p` the allowlist is a hard restriction (an unlisted tool is denied
outright, no prompt), which is what makes Role 2's read-only rule structural:
the reviewer can write its record and nothing else. It is a guard rail, not a
sandbox, since `Bash` can still write a file. Swap the bare `Bash` for
`"Bash(git *)"` when the diff is privileged enough to want that shut.

When the user asks to run the reviewer themselves, print the same line without
`-p`, the output flags and the redirects, and stop. Interactively the allowlist
is an auto-approval list instead, so an edit outside the record stops and asks
the user, which is the same guard with a human in it.

## Role 2 — review (a separate session)

Given a record path, you are the reviewer. You did not write this code and you
must not go looking for the reasoning behind it: read the record, the ticket it
names, and the diff. Nothing else.

1. Verify the record's `Base` still resolves and that `HEAD` is what you are
   about to review. Note both in the record.
2. Run the passes the diff earns, at the depth `Stakes:` gives (the table
   above; in a later round, see Rounds). In the BRZ estate, load `brz:ops-review` and
   run what its table earns; `brz:pg-ops-reviewer` and `brz:jenkins-lint` pin
   their own models. Elsewhere, run `/code-review <level> <Base>..<HEAD sha>`,
   plus the spec conformance pass below when the record names a ticket. Give it
   the range, both ends as shas: a lone sha is taken as the commit to review, so
   on a stacked branch it reviews the branch below instead. Note in `Passes:`
   which ran, with the range, and which the diff did not earn.
3. Confirm every finding against the file before recording it — a pass working
   from a hunk can be confidently wrong about scope.
4. Write the findings into the record, worst first, each with its severity,
   `file:line`, the concrete failure, and `Disposition: open`.
5. Set `Head:` to the reviewed sha, `Reviewer:` to your model and the date, and
   `Verdict:` to `findings`, `pass` or `blocked`.

**Read-only.** Do not fix what you find, do not commit, do not touch `TODO.md`.
A reviewer that starts editing has stopped being independent, and the implementer
loses the chance to disagree.

`blocked` is for a diff you could not review — it needs a host, or an answer from
the user. Say which, on the record. It is a legitimate outcome; a hedged `pass`
is not.

### Spec conformance

Has no agent file: spawn a `general-purpose` agent with this prompt, filling in
the paths and the base.

> Read `.scratch/<slug>/spec.md` and its `issues/`. Read `git diff <BASE>`.
> Report drift in both directions: requirements with no implementation, and
> changed code no requirement asked for. Do not judge whether the code is
> correct — only whether it is what was specified. Read-only.

### Should the reviewer run a different model?

Model diversity decorrelates blind spots, which is the point of the exercise. It
also costs: a weaker reviewer against a stronger implementer produces noise that
the implementer then has to adjudicate. Default to the same model in a genuinely
fresh context, and switch models when the diff is small and the blast radius is
a production database — `--model sonnet` on the launch line above. Either way
`Reviewer:` records which it was.

## Role 3 — adjudicate (back in the implementing session)

Every finding ends in exactly one of these, written on the record:

| Disposition | What it requires |
|---|---|
| `fixed` | The fix, committed, and the raising pass re-run against the new head |
| `deferred` | An entry in `Open issues` in `TODO.md`, with the reviewer's wording preserved and what would close it — load `todo-ledger` |
| `rejected` | A **counter-fact at `file:line`** showing the failure cannot occur |

**A finding is never closed by argument.** "The reviewer misread the scope" is
not a disposition; the line of code that proves it is. If you cannot produce the
counter-fact, the finding is real — fix it or defer it.

Where you and the reviewer still disagree after that, say so to the user with
both positions and let them call it. That is the case the record exists for.

## Rounds

Fixing findings moves `HEAD`, and the gate compares against the sha that was
reviewed. So a fix means another round: append `## Round N` to the record, launch
a fresh reviewer on it the same way as Role 1, and let it update `Head` and
`Verdict`.

**A later round reviews the fix, not the branch again.** The reviewer checks that
each disposition holds at the new head, then reviews the diff since the last
reviewed head (`<previous Head>..<new HEAD sha>`, the range form of Role 2),
and records a new finding only at a severity the Stakes table allows for later
rounds. Anything below that bar, or in code the fix did not
touch, goes under "Raised and not recorded" with one line each. Which passes to
re-run is the reviewer's call, not the author of the fix's.

**A closing round settles nits.** When a round leaves only `nit`s open, the
implementer fixes or defers them in one commit that touches comments, docs and
`TODO.md` alone, and says so in the round's request. The reviewer checks that the
commit touches nothing else and that each disposition holds, records nothing new,
and sets `pass`. A commit that touches code makes it an ordinary round.

**Round 3 is the last one the implementing session launches on its own.** When it
ends with a `blocking` or `should-fix` finding open, give the user each open
finding with its severity and your proposed disposition, and let them choose:
another round, deferral to `TODO.md`, or a ruling. A closing round does not count
towards the three.

## The gate

`${CLAUDE_PLUGIN_ROOT}/hooks/git/pre-push` refuses a push, from a repo with a
`.scratch/reviews/` directory, that would update a ref to a commit no record
carries `Verdict: pass` for, unless the remote already has that commit (a release
tag on the merge GitHub made, say). It is a git hook, so it sees exactly the refs git
is about to update, however the command was written. Only Claude's commands run
it: the plugin's SessionStart hook `git-hooks-path.sh` sets `core.hooksPath` to
`${CLAUDE_PLUGIN_ROOT}/hooks/git` for the commands Claude runs, and `passthrough` there runs the repo's own hooks, from wherever the
repo's own `core.hooksPath` would have taken git. `--no-verify` would skip the
gate, so `${CLAUDE_PLUGIN_ROOT}/hooks/no-verify-push.sh` refuses any command that pushes with
it. The records are those of the main checkout and of the checkout the push runs
in. The hook's docstring has the full rule; `${CLAUDE_PLUGIN_ROOT}/hooks/review-gate_test.sh`
exercises it.

- **Opt a repo in**: `mkdir -p "$(git rev-parse --show-toplevel)/.scratch/reviews"`,
  run in the main checkout.
  Repos without it are never gated, and so is anything outside a repo.
- **Bypass**: `REVIEW_GATE=off git push …`. That is the user's to type. Do not
  add it yourself, and do not suggest it as the way past a finding — say what the
  gate is asking for instead.

The gate fails open. If it fails itself (an unreadable record, say), it allows
the push with a warning, because a broken gate must never be the reason work
cannot ship.

## Before finishing

- The record has a `Head` matching the sha under discussion, and a `Verdict`.
- The implementing session wrote neither of those lines.
- The record has a `Stakes` line, and every finding a severity.
- Every finding has a disposition, and every `rejected` has a counter-fact.
- No round past the third ran without the user choosing it.
- Every `deferred` finding is in `TODO.md` and committed.
- A `pass` is reported as reviewed, never as tested.
