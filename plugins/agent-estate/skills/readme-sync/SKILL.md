---
name: readme-sync
description: Keep a repo's README true as the code changes — checking what it says about the files a change touches, fixing what no longer holds, and committing that before the branch's pull request opens. Use when the readme-sync hook refuses a pull request, when a change renames, adds or removes a file, command, option or step the README describes, when asked to check or update a README, and when reconciling a branch before it merges. Covers what to check, how to fix it without restating the code, and the hook's escape.
---

# Keeping the README true

A README is read before the code and trusted more than it deserves: a command that
no longer works, a path that moved, a list missing its newest entry all cost the next
reader more than no README would. It drifts one change at a time, so it is checked once
per pull request, before the change reaches the default branch.

## The hook

`hooks/readme-sync.py` (PreToolUse on Bash) refuses a `gh pr create` into the default
branch when the branch changes a file the root README names, or adds or deletes a file
under a directory it names, and leaves the README unchanged. Its docstring has the exact
rule. The refusal lists each file and the name it matched.

It only says where to look; whether the README still holds is your call:

- **Something no longer holds** → fix the README, commit and push it, open the pull
  request again.
- **All of it still holds** → rerun the same command with `README_SYNC=checked` in front.
  Only after reading the passages: the prefix says you did.

It does not see a change the README describes in words without naming a file — a new
option, a changed default, a dropped step. That part is yours whenever you change
behaviour a user drives.

## What to check

For each passage that mentions what the change touched:

- **Commands and code blocks still work** as written: flags, arguments, file names,
  defaults. Run them when it is cheap and safe; otherwise read the code that parses them.
- **Paths exist** where the README says. After a move or rename, grep the README (and
  other docs) for the old name.
- **Lists are complete.** A README that lists a directory's contents (skills, hooks,
  scripts, questions) gains or loses an entry with the directory. A list that says "and
  more" need not be exhaustive, but must not name what is gone.
- **Described behaviour is still the behaviour**: what a tool does, what it refuses,
  what it needs installed or configured.

## How to fix it

- **Match the README's existing voice and depth.** One sentence where its neighbours
  have one sentence; no new section for what fits an existing one.
- **Point, don't restate.** Where the detail lives in a docstring, a script's header or
  a generated doc, the README names that place ("its docstring lists every step")
  rather than copying it, so there is one home to keep true.
- **Delete what is gone.** No "removed in …" notes; the history is in git.
- **Land it with the change**: on the same branch, so the pull request carries both.

## Before opening a pull request

Walk the branch's diff once against the whole README, not just the passages the hook
points at: commands in the setup and usage sections, and every list of contents. Doing
it before `gh pr create` saves the refusal.
