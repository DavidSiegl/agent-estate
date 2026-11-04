# Review NN — <branch>

Repo: <repo>
Branch: <branch>
Base: <base-sha> (<review-base ref, e.g. origin/dev>)
Stakes: <high / normal / low> (<the spec or ticket fact that sets it>)
Head: <not yet reviewed>
Verdict: requested
Opened: YYYY-MM-DD
Reviewer: <not yet reviewed>
Passes: <not yet reviewed>

## Files

<one path per line, from git diff --name-only BASE>

## Tickets

<paths under .scratch/<slug>/issues/, or "none">

## Round 1

### F1 — <one-line defect>

Severity: <blocking / should-fix / nit>
File: <path>:<line>
Pass: <the pass that raised it: brz:pg-ops-reviewer, brz:jenkins-lint, /code-review, spec-conformance>
Failure: <what goes wrong when the code runs, not which rule was broken>
Disposition: open

### Raised and not recorded

<one line per finding below the round's bar, or outside the fix in a later round>

## Could not verify

<paths that need a real host, named — never dropped>

## Not reviewed

<passes not spawned, and why the diff did not earn them>
