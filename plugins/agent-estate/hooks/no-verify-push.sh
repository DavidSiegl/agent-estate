#!/usr/bin/env bash
# PreToolUse(Bash) guard for the review gate, git/pre-push: refuses a Claude
# command that pushes with --no-verify, which makes git skip every pre-push
# hook and with it the gate.
#
# A plain text match, not a parser: any command that contains both `push` and
# `--no-verify` is refused, `git commit --no-verify && git push` included. A
# false refusal costs one explained retry; what it misses is a flag spelt so
# that no text match sees it, which is a deliberate bypass, not a slip.
# REVIEW_GATE=off in the command lets it through, as it does the gate.
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[[ $cmd == *push* && $cmd == *--no-verify* ]] || exit 0
[[ $cmd == *REVIEW_GATE=off* ]] && exit 0

cat >&2 <<'EOF'
No --no-verify on a push: it skips git's pre-push hooks, and with them the review
gate (the agent-estate plugin's hooks/git/pre-push) and the repo's own pre-push hook. Push
without it. If a hook refuses the push, its message says what it needs: for
the review gate, a cross-review record that passed the commit being pushed.
EOF
exit 2
