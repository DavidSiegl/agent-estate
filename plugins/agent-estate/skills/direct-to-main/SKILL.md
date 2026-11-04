---
name: direct-to-main
description: Let coding agents commit and push straight to this repo's main/master branch, or take that back. Argument on, off or status.
disable-model-invocation: true
argument-hint: on | off | status
---

# Direct to main

Sets whether agents in the repo at the current directory work on its default
branch instead of a branch of their own. The setting is `agent.directToMain` in
the repo's local git config:

- it lasts until turned off, across sessions and `/clear`;
- it covers every worktree of the repo, since a worktree shares the main
  checkout's `.git/config` (unless `extensions.worktreeConfig` is on, which none
  of these repos use);
- it is never committed, so no clone but this one sees it.

The rule that reads it is in `~/.claude/CLAUDE.md`, Git → Commit handling. It
changes which branch agents commit and push to, nothing else: when to push, and
`${CLAUDE_PLUGIN_ROOT}/hooks/git/pre-push` refusing an unreviewed push, stay as they are.

## Steps

1. Find the repo: `git rev-parse --show-toplevel`. When that fails, say the
   current directory is not in a repo, and stop.
2. Find its default branch: `git symbolic-ref --short refs/remotes/origin/HEAD`,
   less the `origin/`. With no `origin/HEAD`, whichever of `main` and `master`
   exists locally.
3. Apply the argument (`$ARGUMENTS`):
   - `on`: `git config --local agent.directToMain true`
   - `off`: `git config --local --unset agent.directToMain`. Exit status 5 means
     it was not set, which is the state asked for.
   - `status`, or no argument: `git config --local --get agent.directToMain`.
     Exit status 1 means unset, which is `off`.
   - anything else: say the three arguments, and stop.
4. Report in one line: the repo's path, its default branch, and the state now
   (`on` or `off`). After `on` with a session that already has a branch of its
   own open in this repo, say that the branch stays as it is: merging it is a
   separate step.
