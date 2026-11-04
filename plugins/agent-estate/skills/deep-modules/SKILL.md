---
name: deep-modules
description: Guard against shallow modules and information leakage while writing or changing code, after John Ousterhout's "A Philosophy of Software Design". Use when a change adds or reshapes an interface — a new function, method, class, package or service; splitting or merging code; adding a wrapper, a parameter, a configuration option or an error a caller must handle — and when reviewing a diff for its design. Covers the checks to run on each interface, the red flags with their fixes, when to split and when to join, and where each rule stops applying. Distinct from mattpocock-skills:codebase-design, which is the vocabulary for designing an interface from scratch; this is the check on code as it is written.
---

# Deep modules

A module is anything with an interface and an implementation: a function, a
class, a package, a service. Its **benefit** is the functionality it provides;
its **cost** is its interface, because that is what everyone else must learn.
The best modules are **deep** — a lot of functionality behind a simple
interface. A **shallow** module's interface is nearly as complex as its
implementation, so it adds something to learn without taking anything away.

**The interface is everything a caller must know**, not just the signature: the
behaviour, the side effects, the errors, the order in which things must be
called, the configuration it needs. If a caller has to know it to use the module
correctly, it is interface. Most of the cost usually sits in this informal
part, so a short signature is not proof of depth.

**Judge a design by the complexity it leaves, not by its size.** Complexity
shows up as three symptoms: *change amplification*, where one decision
changed means edits in many places; *cognitive load*, how much a developer must
know to make a change; and *unknown unknowns*, where it is not clear which code
a change must touch at all. A version with more lines that lowers cognitive load
is the simpler one. Unknown unknowns are the worst of the three, because they
surface only as bugs.

## Check every interface the change adds or widens

Three questions, before and after writing it:

1. **What does a caller no longer need to know?** Name it: a file format, a
   retry policy, a protocol, the layout of a structure. If the honest answer is
   "nothing", the module is shallow — `addNullValueForAttribute(a)` that does
   `data.put(a, null)` costs a name, a signature and a doc comment, and hides
   nothing.
2. **Is the common case the simplest call?** The usual use needs no options,
   no setup sequence, no knowledge of the rare features. Give it defaults; put
   the rare features behind separate calls.
3. **Can you say what it does in a sentence or two without saying how?** If
   the description must be long to be complete, or no precise name comes, the
   boundary is probably in the wrong place.

Question 1 also applies below the level of a module, to every new type, field,
flag, parameter or layer: it is the cost rule in the Design section of
`CLAUDE.md`.

## Red flags, and what to do instead

**Shallow module.** The interface is not much simpler than the implementation.
Merge it into its caller or its callee, or pull enough behind it that it hides
something.

**Pass-through method.** It does little but call another with the same or a
similar signature, so two layers offer the same abstraction. Let callers
call the lower one directly, move the responsibility so only one layer has it,
or merge the two. A dispatcher that chooses between implementations, and several
implementations of one interface, are not pass-throughs.

**Pass-through variable.** A value is threaded through methods that do not use
it, to reach one that does. Put it on an object both ends already share,
or in a context object passed to constructors — not in a global, which rules out
two instances in one process, tests included.

**Decorator for a small feature.** A wrapper that repeats the wrapped API to add
one capability. Add the capability to the class itself if most users want
it, merge it into the one use case that needs it, or merge it into an existing
wrapper. A wrapper is right for adapting an external interface you cannot change.

**Interface that mirrors the implementation.** The API exposes the internal
representation: lines in, lines out, because the text is stored as lines.
Offer the operations callers need and convert inside.

**Information leakage.** One design decision lives in two places, so changing it
means changing both. The back-door form is the dangerous one: two modules
that never call each other but both know a file format, a column order, an
output's layout. Give the decision one owner — merge the two, or move it into a
module of its own, but only if that module's interface is simpler than the
knowledge it holds; otherwise the leak just moves into the interface.

**Temporal decomposition.** The code is split by when things happen — read,
change, write — rather than by what each part must know, so the reader and the
writer both learn the format. Structure by knowledge; order can live in
the caller.

**Getters and setters.** A pair of one-line methods per field is a shallow
interface over the representation: callers still depend on every field
and its meaning. Offer the operations callers perform on the state instead, and
keep the fields private. Where accessors are the codebase's convention (Java
beans, ORM entities), follow it, as `CLAUDE.md` asks, but add none for a field
no caller reads.

**Implementation inheritance.** A subclass that reads or writes its parent's
state shares the parent's design decisions, so changing one class can mean
learning the whole hierarchy. Prefer composition with small helper
objects. Inheriting an interface is fine: each further implementation makes the
interface deeper.

**Overexposure.** Using a common feature forces the caller to learn about rare
ones. Default them, and move them behind their own calls.

**Special-general mixture.** Code for one use case sits inside a general
mechanism — a text buffer with a `backspace` method. Push the
special case up into its caller, or down behind a general interface, as a device
driver does.

**Configuration parameter as a punt.** An option exported because the right
value was not worked out. Ask whether the caller can choose a better value
than the module can. If not, compute it; if so, give it a default that is right
for nearly everyone.

**Error as a punt.** An error raised for a case the module could handle, so
every caller has to. Define it out of existence — "ensure x does
not exist" cannot fail on a missing x — handle it once at a low level, or catch a
family of errors in one place.

**Repetition.** The same logic, near-verbatim, in several places: the
abstraction that should own it is missing.

## Splitting and joining

**Length alone is never the reason to split**. A long function with a
simple interface that reads top to bottom is deep, which is good. Make it deep
first, then short enough to read; never trade depth for length.

Split only to get a cleaner abstraction, in one of two ways:

- **Extract a subtask** that is cleanly separable: a reader of the child needs
  nothing from the parent, and a reader of the parent need not read the child.
  Such a child is usually general enough to have other callers.
- **Divide a function that does unrelated things**, so each part has a simpler
  interface — but only if most callers then need just one of the parts.

**Conjoined methods** are the sign a split went wrong: you cannot understand one
without reading the other, or callers must invoke both and pass state between
them. Join them back.

Bring code together when the pieces share information, when joining them gives
a simpler interface, when it removes duplication, or when they are always used
together — in both directions. Keep them apart when one is a general
mechanism and the other a use of it.

## Where each rule stops

Every rule above has a limit:

- **Expose what callers genuinely need**. Hiding a tuning knob that
  different callers must set differently, or swallowing an error a caller must
  react to, is a defect, not depth. Masking an error is only right where no
  caller could do anything better with it. Where the user's rules require every
  error to be checked and returned, that still holds: defining an error out of
  existence changes what counts as an error, it never discards one.
- **Pull complexity down only when it belongs there**: it relates to the
  module's job, it simplifies the callers, and it simplifies the interface.
  Otherwise it is leakage in the other direction.
- **Somewhat general-purpose**: the interface general enough for more
  than today's caller, the functionality only what today needs. If using the
  module for the current need takes a lot of code, it is too general.
- **Depth is not a line count.** Padding an implementation does not deepen it;
  what counts is what callers are spared.

## Scope

Apply the guard to the interfaces this change adds or alters. A shallow module or
a leak you find in code the change does not touch is reported, not refactored:
put it in `TODO.md` under `Open issues` with a file pointer (`todo-ledger`), since
a design fix outside the ticket makes the diff unreviewable.

When an interface fails the check and no fix is obvious, design it again rather
than patching it: `design-it-twice` compares radically different alternatives
through the caller code each one forces.

## Before finishing

- Every interface the change added or widened has a named piece of knowledge it
  hides, and its common case is its simplest call.
- No new pass-through method, pass-through variable or one-feature wrapper.
- No design decision now lives in two modules, by interface or by back door.
- No function was split for length; every split extracts a separable subtask or
  divides unrelated work, and no two new functions must be read together.
- Every new option and every new error passed the "could the module decide this
  itself?" question — and nothing a caller needs was hidden to pass it.
- Design problems found outside the change are in `TODO.md`, not in the diff.
