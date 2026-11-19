---
name: handover
description: Write a handover so work continues in a fresh context after /clear. Use when a hook reports the context is getting long, or when asked to hand over, flush or reset context.
argument-hint: "[note for the next context]"
---

# Handover

The next context starts with nothing but this file, `CLAUDE.md` and the repo.
The handover is the bridge: everything the work needs that the repo and git do
not already hold. `${CLAUDE_PLUGIN_ROOT}/hooks/context-handover.sh` (its header has the
mechanics) injects it into the session after `/clear`, once.

## Steps

When the hook's reminder triggers this, do not ask the user first: the
threshold is the decision, and the user may not be watching. A *soft* reminder
means finish the step in hand, up to its commit, then hand over; a *hard* one
means hand over now. The exception is a later reminder after the user, shown
a handover, told you to carry on: their word stands, so keep the file current
as step 4 says and do not stop, clear or notify again.

1. **Reach a safe stopping point.** Finish the edit or command in flight; leave
   no file half-changed. When a logical change is complete and its tests pass,
   commit it as `CLAUDE.md` says. Start nothing new.
2. **Get the path**: `${CLAUDE_PLUGIN_ROOT}/hooks/context-handover.sh path`. The hook's
   reminder names the same path.
3. **Write the handover** there, with these sections. Facts at `file:line`, sha
   and command, never "as discussed"; the reader was not there.
   - **Goal**: what the user asked for, in their words where they matter, and
     what done looks like.
   - **State**: repo, branch, last commit, uncommitted changes and why they are
     uncommitted.
   - **Running**: every background task you started that has not sent its
     completion notice (a `run_in_background` command, a background agent, a
     `Monitor`), each with its task id, what it does, its output or log file,
     and what to do with its result. Stop with `TaskStop` any whose result no
     longer matters, and leave it out. A task outlives `/clear`, and its notice
     arrives in the next context, so write the wait as "wait for the
     completion notice of task `<id>`", never as a process to find with
     `pgrep` or poll with `kill -0`. Write "none" when nothing runs.
   - **Done**: what is finished and how it was verified.
   - **Next**: the ordered remaining steps, the first one concrete enough to
     start on without rereading anything.
   - **Decisions**: choices made with their reason, approaches tried and
     rejected with why, so the next context does not retry them.
   - **Open**: questions waiting on the user, unexplained failures, and the
     exact error text.
   - **Read first**: the few files and skills the next context needs to load.

   Add `$ARGUMENTS` as a note when given. Done when a reader with only this
   file could take the first step of **Next** correctly.
4. **Hand over and stop.** When the hook's reminder triggered this, run
   `${CLAUDE_PLUGIN_ROOT}/hooks/context-handover.sh clear`: it arranges for `/clear` and a
   prompt to continue once this turn ends. Tell the user in one line that the
   handover is at that path and the context will clear itself. If `clear`
   exits non-zero, the session is blocked on the user, who alone can run
   `/clear` and may be away: say so, and send one `PushNotification`, leading
   with the action, e.g.
   `BLOCKED: handover written (<repo>: <task>) — /clear to continue`; when
   **Open** holds a question for the user, name it instead of the task.

   A handover the user asked for gets no `clear` and no push; they are at the
   keyboard and run `/clear` when they choose. Tell them in one or two lines
   that the handover is at that path and that `/clear` continues from it.

   Either way, end the turn there: work done after writing makes the handover
   stale, and an auto-clear waits for the turn to end. When the user says to
   carry on instead, update the file before the next stopping point.
