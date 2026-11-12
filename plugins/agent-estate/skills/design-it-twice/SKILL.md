---
name: design-it-twice
description: Before committing to a major design decision, sketch two or more radically different alternatives, write the caller's code against each, compare them on the criteria for that level, and choose, combine or redesign. After John Ousterhout's "A Philosophy of Software Design". Use when choosing the interface of a new module, class, API or tool; an implementation strategy for one; a decomposition of a system into parts; or an architecture or infrastructure approach — and when an interface fails the deep-modules check with no obvious fix, or the user asks for alternatives or to "design it twice". Distinct from mattpocock-skills:codebase-design's procedure, which deepens existing code with parallel subagents; this one works inline on any new decision.
---

# Design it twice

The first design that comes to mind is unlikely to be the best one, however
sure it feels: the problems are hard, not the designer slow. So for
each **major** design decision, rough out several alternatives before building
any of them. It costs an hour or two for a class and more for a system, which
is small next to the days spent building on the wrong one.

A decision is major when undoing it later means changing its callers: an
interface others will code against, a decomposition others will extend, a
choice of infrastructure others will run. A private helper's body is not one.
Work it inline; the alternatives stay in one context so they can be compared.

## 1. Name the decision and its level

Write down, in two or three sentences:

- **The decision**: what is being designed. "The interface of the text class",
  not "the editor".
- **The level**, because the criteria differ (step 4):
  - *interface* — what callers see;
  - *implementation* — what sits behind an interface already chosen;
  - *system* — how the work is split into modules, services or machines.
- **What the higher-level software does with it**: the three or four
  operations its callers actually perform, in their own terms (cut and paste a
  selection; restart a container from the phone). These are the yardstick.

Done when a reader could check each alternative against those operations
without asking what they are.

## 2. Sketch alternatives that are radically different

At least two, usually three. Sketch only the most important operations:
signatures and a line each for an interface, a paragraph and a picture for a
system. Leave the full feature list out.

**Radically different** means different in kind: a different unit of
abstraction (lines, characters, ranges), a different owner for the key
decision (caller or callee, client or server, the agent or the gate), a
different place where the knowledge lives. Variants that differ only in names,
options or defaults are one alternative.

Include a second design even when certain the first is the only reasonable
one, and even if you expect it to be bad. Its weaknesses show what the good
design is getting right, and sometimes it turns out not to be bad.

Done when each alternative can be stated in one sentence that the others
contradict.

## 3. Write the caller's code against each

For each alternative, write the code (or the run-book, for a system) that the
operations from step 1 would need. This is the step that exposes the designs:
the most important property of an interface is how easy it is for higher-level
software to use, and that is only visible in the **caller code**.

Look in that code for the work the alternative pushes onto its callers: loops
over single elements, splitting and joining, bookkeeping between calls, an
error every caller must handle the same way, knowledge of a format the module
should own.

Done when every alternative has caller code for the same operations, so the
comparison is like for like.

## 4. Compare on the criteria for the level

List the pros and cons of each alternative against the criteria for its level,
in a table when there are more than two:

- **Interface.** Ease of use for higher-level software first. Then: which
  interface is simpler; which is more general-purpose — somewhat general, not
  built for one caller or for every imaginable one; which allows the
  more efficient implementation; and the `deep-modules` checks: what does each
  hide from its callers, and is the common case the simplest call?
- **Implementation.** Simplicity and performance. The interface is fixed, so
  caller code is out of play; compare what each implementation must keep true
  and what it costs per operation.
- **System.** Where each design decision lives and whether any lives in two
  places (information leakage). Which parts change together, and does
  each split hide something or only pass things through? Also how it fails and
  what it depends on, which is often the whole question in infrastructure.

Done when each criterion has an answer for each alternative, including the
answers that favour the alternative you do not want.

## 5. Choose, combine, or design again

Three outcomes, all legitimate:

- **One alternative wins.** Say which criteria decided it.
- **A combination is better than any of them.** Take the features that won
  their rows and check that the combination still has a simple interface. A
  combination that keeps both designs' interfaces is two designs, not one.
- **None is good.** When every alternative makes the callers do extra work,
  that is a **red flag**: none of them matches what the higher-level software
  actually does. Use the problems from step 3 to drive a new design, and run
  it through steps 3 and 4. Ousterhout's line and character interfaces both
  forced callers to manipulate text; that problem pointed to the
  range-oriented interface, which beat both.

Done when the choice names the criteria that decided it and the caller code
for the chosen design is the simplest written.

## 6. Record it where it will be read

- **A design inside a change**: present the alternatives, the comparison and
  the choice in the reply before writing the code. If the winner is much
  larger than the task, say so and let the user choose rather than taking it
  or the shortcut silently.
- **A design inside a spec**: the chosen design is the spec; each serious
  alternative gets its own file beside it, ending in the comparison table
  (`scratch-issue-tracker` for the layout). When the user, not the evidence,
  must choose, leave both open and list the questions that would decide it.
- **The rejected alternatives**: record them with the reason in the commit
  message of the change that chose the winner, and in a comment beside the code
  where its reader would otherwise reach for one of them — not in `TODO.md`,
  which holds only what is open (`todo-ledger`).

## Applying it at more than one level

A module goes through the procedure twice: first its interface, then, with the
interface fixed, its implementation. The book's text class compares line,
character and range interfaces, and then a linked list of lines, fixed-size
blocks and a gap buffer behind the range interface it chose.

## Before finishing

- The decision, its level and the callers' operations are written down.
- At least two alternatives differ in kind, not in names or options, and one
  of them was not the first idea.
- Every alternative has caller code for the same operations.
- Every criterion for the level is answered for every alternative.
- The choice names its criteria; if every alternative burdened the callers, a
  further design came from those problems.
- The comparison and the rejected alternatives are recorded where the next
  reader of the code or spec will find them.
