---
name: external-edits
description: Preserve changes to a file that you did not make yourself. Use when an Edit or Write is refused because the file changed since you read it, when a file you edited earlier no longer matches what you wrote, when resuming a session before touching a file you edited in it, when the user mentions committing, reverting, stashing or hand-editing work you were involved in, or when a subagent or another session shares a file with you. Covers attributing a change, rebasing yours onto it, and the deletions that clobber silently.
---

# Edits you did not make

A file you edited is not yours. Between your edit and your next look at it, the user
hand-edits it, commits, amends, reverts, stashes, runs a formatter, or another session
writes to it. Your memory of what you wrote goes stale the moment you stop looking at
the file.

**The file on disk is the base.** You rebase your change onto it; it never rebases
onto you.

## How you find out

- An Edit or Write is refused because the file changed since you read it. The refusal
  is the signal working, not an obstacle to route around.
- You read a file and it does not match what you remember writing.
- The user mentions a commit, revert, stash, pull, merge, or "I changed X".
- You are resuming a session. Everything you remember editing sits behind a gap you
  did not watch — check before touching any of it.
- A subagent, teammate, or another session was working in the same file.

## Rebase onto disk

1. **Re-read the whole file.** The whole file, not the region you were editing — a
   change three functions away still decides whether your edit fits.
2. **Attribute the difference.** `git diff` for unstaged work, `git log -p -- <file>`
   for commits, `git stash list`, `git log --oneline` for commits you did not make.
   A commit you did not author, or an unstaged hunk sitting over a commit that holds
   your work, is theirs.
3. **Keep what you find.** Every difference between what you wrote and what is there
   now is theirs to keep, until you have a reason from the file or the user.
4. **Apply your change on top**, shaped to fit the code as it now reads — their
   names, their structure, their formatting.
5. **Report** what changed while you were away.

Done when every difference between your version and the file on disk is accounted
for: kept, or changed with the user told which and why.

## The deletion is the one you will miss

An addition announces itself; a removal does not. When they deleted a comment, a
guard, a parameter, or a whole function you wrote, re-applying your edit from memory
puts it back — and the diff you produce looks clean, because you cannot see a
restoration against a base you never read.

So treat absence as a decision. A line of yours that is gone stays gone.

## When your whole change is gone

A `git checkout -- <file>`, a reset, a dropped stash, a force-push: your change is not
missing, it was rejected. Ask before writing it again, and say you noticed it was
reverted. Re-applying it silently is how the same argument happens twice.

## Machine changes

A formatter, `gofmt -w`, `go mod tidy`, codegen, a lint autofix: keep the result and
match the new style. It carries no intent to preserve, and fighting it just loses the
next run.

## What to report

Two sentences at most, in the turn where you found it:

- what changed while you were away, and whose it was
- that your work is built on top of it
- anything of yours that is gone, which you left gone

Say it plainly and move on — this is a status line, not an apology.
