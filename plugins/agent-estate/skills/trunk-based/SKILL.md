---
name: trunk-based
description: Trunk-based development in a git repo. Branches live for hours, not days. They start from a fresh default branch, take in its new commits often, and merge back fast. Merged branches and worktrees are cleaned up, automatically in a repo that opts in. Use when starting, updating or finishing a branch; when a session start reports branches off the default branch too long; when asked to clean up, prune or list stale branches or worktrees, or when `git worktree list` shows `prunable` entries or a branch is `[gone]` upstream; and with on, off or status to set automatic cleanup for the repo.
argument-hint: "[on | off | status | clean [repo | all]]"
---

# Trunk-based development

The default branch (`main` or `master`, whichever `origin/HEAD` names) is the
only long-lived branch. Everything else is a short detour from it. Whether an
agent branches at all is `~/.claude/CLAUDE.md`'s rule (Git → Commit handling,
`agent.directToMain`). This skill covers what happens once it does.

## The branch lifecycle

1. **Start from the trunk as it is now.** Run `git fetch origin`, then branch
   from `origin/<default>`, not from a local default branch that may lag:
   `git switch -c <name> origin/<default>`, or
   `git worktree add <path> -b <name> origin/<default>`.
2. **One logical change per branch, small enough to merge the same day.** If
   the work will take longer, split it into pieces that each leave the default
   branch working and merge them one at a time. Don't stack branches on
   unmerged branches.
3. **Take in the trunk often**: before every push, and whenever you resume
   work on the branch. How depends on whether the branch is published:
   - Not pushed yet: `git rebase origin/<default>`.
   - Pushed: `git merge origin/<default>`. A rebase would rewrite what
     reviewers, CI and the review gate's records (they name commits) already
     saw. If the repo's history shows its pull requests catch up another way,
     follow the repo. `reconcile-prs` covers conflicts.
4. **Merge as soon as it is green.** Open the pull request when the change is
   whole, not when it is perfect. Small follow-ups go in their own branches.
5. **Clean up.** A merged branch and its worktree are deleted (below). Never
   reuse a merged branch for new work. Start again from step 1.

When a session start reports a branch as off the default branch too long,
deal with it before new work. If the branch is yours and unfinished, bring it
up to date (step 3) and finish or split it. If it is not yours, or its upstream
is gone without a merge, ask the user whether to finish it, hand it over or
drop it. Only the user decides to delete unmerged work.

## Cleanup

`${CLAUDE_PLUGIN_ROOT}/hooks/trunk-cleanup.py` removes merged worktrees and
branches and reports the branches that lag. Its docstring is the rule for what
counts as merged and what keeps a worktree: unsaved work, a live process or a
recent session, a lock, or being a tool's own. Everything it removes is
provably on `origin/<default>` already, or is the head of a merged pull
request.

### Automatic, per repo

Setting `agent.trunkBased` in the repo's local git config makes the plugin's
SessionStart hook run the cleanup at every session start and resume. It
removes without asking and puts its report in the session's context. Like
`agent.directToMain`, it covers every worktree of the repo and is never
committed.

The skill's argument (`$ARGUMENTS`) sets it for the repo at the current
directory (`git rev-parse --show-toplevel`; outside a repo, say so and stop):

- `on`: `git config --local agent.trunkBased true`, then run the cleanup once
  (below) so the user sees what it does.
- `off`: `git config --local --unset agent.trunkBased`. Exit status 5 means it
  was already unset.
- `status`: `git config --local --get agent.trunkBased`. Exit status 1 means
  off.

Report the repo's path and the state now in one line.

### On demand

With `clean`, no argument, or a request to clean up, scope the run to one of
these: the repo at the current directory, a repo the user names, or with `all`
every git repo directly under `~/GitHub`.

- In a repo with `agent.trunkBased` on, run
  `${CLAUDE_PLUGIN_ROOT}/hooks/trunk-cleanup.py <repo>` and relay its report.
- In any other repo, the user approves removals. Run it with `--dry-run`
  first and show what it would remove and what it keeps, and why. Then ask
  with AskUserQuestion, with "remove all of these" as the first option. Run it
  without `--dry-run` only on a yes. For a subset, remove each approved item by
  hand: `git worktree remove <path>`, then `git branch -d <branch>`. Use
  `git branch -D` only for a branch the dry run listed, because `-d` checks
  against the current HEAD and refuses a branch that was squash-merged.

What it keeps stays kept. Never reach for `git worktree remove --force` or
`git branch -D` on an item it kept. Its reason says what would free the item:
commit or discard the file, push the branch, wait for the session, or ask the
tool that owns it. Delete remote branches only when the user asks. A merged
pull request's branch is usually gone already. Leave the transcripts under
`~/.claude/projects/` alone.
