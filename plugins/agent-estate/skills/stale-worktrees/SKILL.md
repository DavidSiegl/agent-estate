---
name: stale-worktrees
description: Find git worktrees left behind by earlier agent sessions and remove the ones whose work is safe elsewhere, with their branches — never one holding uncommitted changes, unpushed commits or a live session. Use when asked to clean up, prune or list stale worktrees, when `git worktree list` shows `prunable` entries, or when a worktree's branch is `[gone]` upstream.
argument-hint: "[repo path | all]"
---

# Remove stale worktrees

Agents leave worktrees in the scratchpad (`/tmp/claude-<uid>/…`), in
`.claude/worktrees/` (Claude Code's own isolation), in a tool's directory
(`.orchestrator/worktrees/`) and as siblings of the checkout (`<repo>-<slug>`).
Where it lives does not tell an agent's worktree from the user's own, so the
verdict rests on the worktree's **state**, and the user approves every removal.

Scope: the repo at the current directory, or the one named; `all` means every
git repo directly under `~/GitHub`.

Done when every linked worktree in scope is listed with a verdict and its
evidence, and those the user approved are removed with their branches.

## 1. Survey

```bash
git worktree list --porcelain
git fetch -q --prune origin
```

The first entry is the main checkout: never a candidate. For each other entry
note its path, `HEAD`, branch (or `detached`), and the `locked` and `prunable`
lines. `prunable` means the directory is gone and only git's record of it
remains; its branch may still hold the only copy of commits.

## 2. Judge each worktree

A worktree is **stale** only when all four hold. Record the command output that
shows each one; it is the evidence in the report.

1. **No live session.** No process has its cwd inside it:
   ```bash
   for p in /proc/[0-9]*; do readlink "$p/cwd"; done 2>/dev/null | grep -F "<path>"
   ```
   and no Claude session wrote there recently: the project directory under
   `~/.claude/projects/` is the path with every `/` and `.` turned into `-`; its
   newest `*.jsonl` should be older than a day. A session idle for less than
   that may resume.
2. **Nothing uncommitted.** `git -C <path> status --porcelain --ignored` shows
   no tracked change and no untracked file. Of the ignored files, build output
   and caches (`__pycache__/`, `target/`, `node_modules/`, `.venv/`) are
   regenerable; anything else — above all `.scratch/`, which holds tickets and
   review records — counts as work until you have checked it is also in the
   main checkout (`diff -r`).
3. **Its commits are elsewhere.** `HEAD` is an ancestor of the default branch on
   the remote:
   ```bash
   git merge-base --is-ancestor <HEAD> "$(git symbolic-ref --short refs/remotes/origin/HEAD)"
   ```
   A squash or rebase merge fails that test though the work landed. Then the
   branch's pull request settles it: merged, with `headRefOid` equal to `HEAD`.
   ```bash
   gh pr list --head <branch> --state merged --json number,headRefOid,mergedAt
   ```
   A branch whose upstream still exists and contains `HEAD` is safe too, but it
   is unfinished work: stale only if the user says the branch is abandoned.
4. **Nobody else owns it.** Not `locked` (the lock's reason, if any, follows the
   word). Not inside a tool's own directory such as `.orchestrator/`: that tool
   tracks its worktrees and removing one under it can break its state, so
   report it and name the tool's own cleanup.

A worktree failing any test is **kept**; say which test and what it would take
(push the branch, commit or discard the file, wait for the session).

## 3. Ask

Show one table per repo: path, branch, verdict, and the evidence for it (the
merged PR number, the ancestor check, the newest session file's date). Then ask
which stale ones to remove, with AskUserQuestion, all stale ones as the first
option. Removing is the step that cannot be undone; nothing goes before this
answer.

## 4. Remove

For each approved worktree:

```bash
git worktree remove <path>          # prunable entries: git worktree prune
git branch -d <branch>
```

`git worktree remove` refuses a dirty tree and `git branch -d` an unmerged
branch: both refusals mean step 2 missed something, so go back to it rather than
reach for `--force` or `-D`. The one exception is a branch proven by test 3's
pull request (squash-merged): delete it with `-D` and cite the PR. A detached
worktree has no branch to delete.

Delete the remote branch only when the user asks; a merged PR's branch is
usually gone already (`[gone]` in `git branch -vv`).

Leave the session directories under `~/.claude/projects/` alone: they are the
transcripts, not the worktree.

## 5. Report

Per repo: what was removed (worktree, branch, the evidence), what was kept and
why, and a final `git worktree list` showing what remains.
