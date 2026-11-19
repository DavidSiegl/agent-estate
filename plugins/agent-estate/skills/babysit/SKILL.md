---
name: babysit
description: Watch an open PR — fix failing CI, handle the straightforward review comments, and drive it to a mergeable state. Claude Code analog of Cursor's built-in /babysit. Use after opening a PR when the user wants the agent to shepherd it without re-prompting.
---

# Babysit a PR

Claude Code analog of Cursor's built-in `/babysit`. The implementation is a loop over `gh` CLI plus the Claude Code `loop` skill for pacing.

## When to use

- There's an open PR and the user explicitly wants it kept green.
- The user invokes `/babysit` directly.
- A subagent that opens a PR does NOT babysit — return to the parent and let the parent decide.

## Steps

1. **Check out the PR and fetch its state.** `gh pr checkout <number>` (in a worktree when the current checkout holds other work), so the skills below, which act on the current branch's PR, act on this one.

   ```bash
   gh pr view <number> --json number,title,state,mergeable,reviewDecision,mergeStateStatus,comments,reviews
   gh pr checks <number> --json name,bucket,link
   # Review threads and whether each is resolved; gh pr view carries neither.
   gh api graphql -F o='{owner}' -F r='{repo}' -F n=<number> -f query='
     query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
       reviewThreads(first:100){nodes{isResolved path line comments(first:1){nodes{author{login} body}}}}}}}'
   ```

2. **Triage in priority order.**
   - Merge conflicts (`mergeStateStatus == DIRTY`): run the **reconcile-prs** skill on this PR. It merges the base in rather than rebasing, so nothing is force-pushed.
   - Failing checks (`gh pr checks` entries whose `bucket` is `fail` or `cancel`; this covers commit statuses such as Jenkins' and timed-out runs): run the **fix-ci** skill.
   - Review comments: run the **get-pr-comments** skill for the summary, then act only on feedback you actually agree with. When a comment has a single mechanical answer — a rename, a guard clause, a formatting nit — make the edit and quote the comment in the commit message. When it hinges on a judgement call, or you can't tell what's being asked, don't guess: leave it and reply with what you would have done.
   - Review-bot comments (Bugbot and similar automation): classify fix/dismiss/ask before acting. Ask by default on security, data, and high-severity findings.

3. **Loop.** Use the Claude Code `loop` skill to pace re-checks. Pick the interval from what you're watching:
   - Active CI run: poll `gh pr checks --watch` (it blocks until checks finish, so no separate loop interval needed).
   - Awaiting reviewer: 20–30 min heartbeat.
   - Idle but want to catch new comments: hourly.

4. **When to stop.**
   - Build is green, every review thread `isResolved`, branch merges cleanly → call it ready.
   - You've run three rounds of fix → push → recheck and it still isn't fully green → stop, summarise what's still broken, and hand control back.
   - The next fix would force a design choice → pause and put it to the user with `AskUserQuestion` (pi has no question tool: there, list the same options numbered, end the turn and wait for the answer).

5. **Report.** Summarize fixes applied, comments addressed, comments deferred (with reason), current PR status. Cite each commit by SHA.

## Hard rules

- Don't rewrite history on a branch others may have pulled. If a rebase or force-push looks necessary, clear it with the user first.
- Don't tweak a test's expected values just to get a pass. Only change an assertion when the behaviour genuinely changed and the assertion was pinned to the old behaviour.
- Never skip hooks (`--no-verify`). In a repo with `.scratch/reviews/`, the push gate refuses a commit no review record passes: run each fix through the **cross-review** skill before pushing it.
- Never bypass a failing check by marking it as not required.
- `gh pr ready` only when all checks are green and no review thread is unresolved.

## Cross-refs

- Opening a PR does not start a babysit; it starts only when asked.
- Use `unslop` on any prose you write here (PR comments, commit messages, status reports).

## Provenance

This is a Claude Code analog of Cursor's `/babysit`, not a port — Cursor's implementation is closed source. The skill is independently authored, with its own prose and structure; the workflow is informed by Cursor's public `/babysit` behavior. The only overlap with other PR tools is the `gh` CLI commands it runs, which are functional invocations rather than copied text.
