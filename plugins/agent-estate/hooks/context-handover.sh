#!/usr/bin/env bash
# Context handover: tell Claude when its context is getting long, carry the
# handover it writes across a /clear, and, inside herdr, run that /clear and
# restart the work without the user.
#
#   context-handover.sh nudge    PostToolUse / UserPromptSubmit hook. Past a
#                                threshold, injects a reminder to run the
#                                `handover` skill, which says what follows.
#   context-handover.sh restore  SessionStart(clear|compact) hook. Injects the
#                                pending handover, then moves it aside so it is
#                                loaded once.
#   context-handover.sh path     Prints where the handover for this Claude
#                                process belongs. For the skill, from Bash.
#   context-handover.sh clear    For the skill, from Bash, once the handover is
#                                written. Inside herdr, starts a detached job
#                                that waits for the turn to end, sends /clear,
#                                and once `restore` has injected the handover
#                                prompts the fresh context to continue; prints
#                                where it logs and exits 0. Exits 1, with the
#                                reason on stderr and nothing started, when
#                                there is no handover or no herdr pane to drive;
#                                the user must then /clear by hand. A failure
#                                after the job started shows a herdr
#                                notification and leaves the handover pending.
#
# Hooks get no context usage in their input; only the status line does. So
# statusline-command.sh writes the input tokens of the last API response (cache
# reads and writes included, output excluded) to
# $XDG_RUNTIME_DIR/claude-context-tokens-<session_id>, and `nudge` reads it.
# Without a status line render (claude -p) that file never appears and nothing
# fires.
#
# Thresholds are absolute tokens, not a share of the window: recall and
# reasoning degrade with the tokens in context whatever the window's size
# (https://trychroma.com/research/context-rot), and with a 1M window a
# percentage fires far too late.
#   CLAUDE_HANDOVER_SOFT_TOKENS (default 200000): one reminder to hand over at
#     the next stopping point.
#   CLAUDE_HANDOVER_HARD_TOKENS (default 350000): a reminder to hand over now,
#     and another every 50000 tokens above it.
#
# A handover is keyed by $CLAUDE_PID, not session_id: /clear starts a new session
# in the same process, so the pid is what both sides of the /clear share.
#
# nudge and restore fail open: any unexpected state exits 0 with no output.
set -uo pipefail

soft=${CLAUDE_HANDOVER_SOFT_TOKENS:-200000}
hard=${CLAUDE_HANDOVER_HARD_TOKENS:-350000}
step=50000
runtime=${XDG_RUNTIME_DIR:-/tmp}
store=${XDG_STATE_HOME:-$HOME/.local/state}/claude-handover

# handover_path prints the pending handover's path for this Claude process, or
# fails when the process cannot be identified.
handover_path() {
    [ -n "${CLAUDE_PID:-}" ] || return 1
    printf '%s/%s.md\n' "$store" "$CLAUDE_PID"
}

# emit prints hook output that adds $2 to Claude's context for event $1.
emit() {
    jq -n --arg event "$1" --arg ctx "$2" \
        '{hookSpecificOutput: {hookEventName: $event, additionalContext: $ctx}}'
}

nudge() {
    local payload event sid agent tokens mark last band file
    payload=$(cat) || return 0
    IFS=$'\037' read -r event sid agent <<<"$(
        jq -r '[.hook_event_name // "", .session_id // "", .agent_id // ""]
               | join("\u001f")' <<<"$payload" 2>/dev/null
    )" || return 0
    # A subagent's context is its own; the status line reports the main one.
    [ -n "$sid" ] && [ -z "$agent" ] || return 0

    tokens=$(cat "$runtime/claude-context-tokens-$sid" 2>/dev/null) || return 0
    [[ $tokens =~ ^[0-9]+$ ]] || return 0

    # Holds the highest band already reminded about in this session: $soft, or
    # $hard plus a multiple of $step. Cleared below $soft, so a compaction that
    # frees space re-arms it.
    mark="$runtime/claude-handover-nudged-$sid"
    if [ "$tokens" -lt "$soft" ]; then
        rm -f "$mark"
        return 0
    fi
    if [ "$tokens" -lt "$hard" ]; then
        band=$soft
    else
        band=$(( hard + (tokens - hard) / step * step ))
    fi
    last=$(cat "$mark" 2>/dev/null || echo 0)
    [ "$band" -gt "$last" ] || return 0
    printf '%s\n' "$band" >"$mark" || return 0

    file=$(handover_path) || return 0
    if [ "$band" -eq "$soft" ]; then
        emit "$event" "Context holds $((tokens / 1000))k tokens (soft handover threshold $((soft / 1000))k). At the next stopping point, load the \`handover\` skill; the handover belongs at $file."
    else
        emit "$event" "Context holds $((tokens / 1000))k tokens (hard handover threshold $((hard / 1000))k). Load the \`handover\` skill now; the handover belongs at $file."
    fi
}

restore() {
    local file used
    cat >/dev/null
    file=$(handover_path) || return 0
    [ -s "$file" ] || return 0
    # Keep the last one consumed, in case the next session needs it again.
    used="${file%.md}.used.md"
    mv -f "$file" "$used" || return 0
    emit SessionStart "$(printf 'Handover from the previous context of this session (%s). Continue from it; verify its claims against the repo before relying on them.\n\n%s' "$used" "$(cat "$used")")"
}

clear_schedule() {
    local file log
    file=$(handover_path) || { echo "context-handover: CLAUDE_PID unset; not inside Claude Code" >&2; return 1; }
    [ -s "$file" ] || { echo "context-handover: no handover at $file; write it first" >&2; return 1; }
    if [ "${HERDR_ENV:-}" != 1 ] || [ -z "${HERDR_PANE_ID:-}" ] || ! command -v herdr >/dev/null; then
        echo "context-handover: not in a herdr pane; the user must /clear" >&2
        return 1
    fi
    log="${file%.md}.clear.log"
    # setsid: the job must outlive the Bash tool call that starts it.
    setsid -f "$0" clear-job "$HERDR_PANE_ID" "$file" </dev/null >>"$log" 2>&1 || {
        echo "context-handover: could not start the clear job" >&2
        return 1
    }
    echo "auto-clear scheduled for herdr pane $HERDR_PANE_ID once this turn ends; log at $log"
}

# clear_job pane file: the detached half of `clear`. Logs each step on stdout.
clear_job() {
    local pane=$1 file=$2 state i
    say() { printf '%s %s\n' "$(date -Is)" "$*"; }
    fail() {
        say "FAILED: $*"
        herdr notification show "Claude handover: auto-clear failed" \
            --body "$*. The handover is pending at $file; /clear by hand." --sound request >/dev/null 2>&1
        exit 1
    }
    agent_state() { herdr agent get "$pane" 2>/dev/null | jq -r '.result.agent.agent_status // empty'; }

    say "waiting for the turn in $pane to end"
    herdr agent wait "$pane" --timeout 900000 >/dev/null 2>&1 || fail "the turn did not end within 15 minutes"
    state=$(agent_state)
    # blocked: a permission prompt or question; the user's to answer, not ours.
    case $state in
        idle|done) ;;
        *) fail "agent is '$state', not ready for input" ;;
    esac

    say "sending /clear"
    herdr agent prompt "$pane" /clear >/dev/null 2>&1 || fail "herdr could not send /clear"
    # restore moves the handover aside once it has injected it.
    for i in $(seq 120); do
        [ -e "$file" ] || break
        sleep 0.5
    done
    [ ! -e "$file" ] || fail "/clear sent but the handover was not loaded within 60s"

    # Other SessionStart hooks may still be running; ticket-sync takes up to 120s.
    herdr agent wait "$pane" --timeout 180000 >/dev/null 2>&1 || fail "the fresh context did not become ready"
    say "prompting the fresh context"
    herdr agent prompt "$pane" "Continue from the handover injected at session start." >/dev/null 2>&1 \
        || fail "herdr could not send the continue prompt"
    say "done"
}

case "${1:-}" in
    nudge)   nudge ;;
    restore) restore ;;
    path)
        handover_path || { echo "context-handover: CLAUDE_PID unset; not inside Claude Code" >&2; exit 1; }
        mkdir -p "$store" || exit 1
        ;;
    clear)     clear_schedule || exit 1 ;;
    clear-job) clear_job "$2" "$3" ;;
    *) echo "usage: context-handover.sh nudge|restore|path|clear" >&2; exit 1 ;;
esac
exit 0
