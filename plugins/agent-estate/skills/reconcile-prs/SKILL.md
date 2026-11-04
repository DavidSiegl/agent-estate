---
name: reconcile-prs
description: Find a repo's open pull requests that conflict with their base branch and reconcile each one, merging the base into the PR branch, resolving textual and semantic conflicts, verifying, and pushing. Use when asked to fix, resolve or reconcile merge conflicts on PRs, or to bring PR branches up to date with main.
---

# Reconcile pull requests with their base

The job is done when every open PR the user named (or every open PR in the
repo, if none was named) either merges cleanly into its *current* base, with the
merge verified and pushed and no stale conflict notice or conflict-only draft
left on it, or is reported as blocked with the reason. A PR that
was already clean is reported as clean, not touched.

## 1. Survey

```bash
git fetch -q origin
gh pr list --state open --json number,title,headRefName,baseRefName,mergeable,mergeStateStatus,isCrossRepository
```

GitHub's `mergeable` is a cache: `UNKNOWN` right after a push, and sometimes
`CONFLICTING` for a minute after the conflict is gone. Settle each PR locally:

```bash
git merge-tree --write-tree origin/<head> origin/<base> >/dev/null && echo clean
```

`BLOCKED` with `MERGEABLE` is a check or review gate, not a conflict: report it,
leave it.

A cross-repository PR (`isCrossRepository: true`) is pushable only when its
author allowed maintainer edits; otherwise report what conflicts and stop there.

## 2. Merge the base in, in a worktree

Work in a worktree in the scratchpad, so the user's checkout and its
uncommitted work stay untouched:

```bash
git worktree add <scratchpad>/pr-<n> -B <head> origin/<head>
git -C <scratchpad>/pr-<n> merge --no-edit origin/<base>
```

Merge, never rebase: the branch is published, and a rebase rewrites what
reviewers and CI already saw. If `git log` shows the repo's PR branches catch up
some other way, follow the repo.

## 3. Resolve

For each conflict hunk, read both sides and the commits that made them
(`git log -p origin/<base> -- <file>` since the merge base) until you can say
what each side *meant*. The resolution keeps both intents; it is rarely "ours"
or "theirs" whole. Shapes that recur:

- Both sides appended to the same list, ignore file or import block: keep both.
- One side refactored code (extracted a function, changed a signature) that the
  other side edited in place: keep the refactor and carry the edit into it.

Then hunt **semantic conflicts**, which git merges silently and the tests may
or may not catch: code from the base that uses something the PR changed.
For every function, type, field or flag whose signature or meaning the PR
changed, grep the base's new code for its uses
(`git diff <merge-base> origin/<base>`) and adapt each one. The same check runs
the other way: the PR's new callers of anything the base changed.

Done when no conflict marker is left in the tree
(`git diff --check` and `grep -rn '^<<<<<<<\|^>>>>>>>'`), and every changed
interface has had its uses on the other side checked.

## 4. Verify

Run what the repo's CI runs: find it in the `Jenkinsfile`, `.github/workflows/`,
`Makefile` or `package.json` rather than guessing. At minimum the full test
suite; the linters too when they judge changed lines. A line you adapted for a
semantic conflict must be executed by some test: if none runs it, say so.

A failure that also fails on the base or on the PR head alone is not the
merge's doing: report it as pre-existing, with the evidence.

## 5. Commit and push

Commit the merge alone, staging the resolved files by name. Keep git's default
`Merge ... into ...` subject; the body names each semantic fix, since nothing
in the conflict markers recorded it. Any other change the user asked for goes
in its own commit after the merge.

Before pushing, `git fetch` again: if the base moved while you worked, merge it
again (back to step 2). Then push to the PR branch and re-query
`gh pr view <n> --json mergeable,mergeStateStatus`; if it still says
`CONFLICTING`, settle it locally as in step 1 before believing it.

Then clear what the conflict left on the PR itself. A tool that opened it may
have written a conflict notice into the body (a `> [!WARNING]` naming the
conflicting files) and opened it as a draft for that reason. Remove that notice
with `gh pr edit <n> --body-file`, keeping the rest of the body verbatim, and
`gh pr ready <n>` only when the body names no other reason for the draft (a
failed gate, changes requested). Check first that undrafting does not trigger an
auto-merge the user did not ask for (`.github/workflows/`, `gh pr view --json
autoMergeRequest`).

Remove the worktree when its PR is pushed.

## 6. Report

Per PR: what conflicted, how each conflict and semantic fix was resolved, what
verified it, and what still blocks the merge (a red check, a missing review).
Leave merging the PR itself to the user unless they asked for it.
