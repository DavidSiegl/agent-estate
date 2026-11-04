#!/usr/bin/env bash
# SessionStart hook: points core.hooksPath at git/ beside this file for every
# command Claude runs through the Bash tool in this session, so the review gate
# (git/pre-push) sees Claude's pushes and git/passthrough still runs the repo's
# own hooks; the user's own git commands are untouched.
#
# It appends exports to $CLAUDE_ENV_FILE, which Claude Code runs before each
# Bash command (https://code.claude.com/docs/en/hooks.md, SessionStart). git
# reads config from GIT_CONFIG_COUNT, GIT_CONFIG_KEY_<n> and GIT_CONFIG_VALUE_<n>
# (git-config(1), ENVIRONMENT); entries already in the session's environment are
# kept, and this one is added after them. A plugin cannot set env through
# settings, which is why this is a hook.
#
# Without $CLAUDE_ENV_FILE it changes nothing and tells Claude the gate is off,
# rather than failing the session start.
set -uo pipefail

hooks=$(cd "$(dirname "${BASH_SOURCE[0]}")/git" && pwd) || {
	echo "agent-estate: the review gate is off this session: no hooks/git beside $0"
	exit 0
}
if [[ -z ${CLAUDE_ENV_FILE:-} ]]; then
	echo "agent-estate: the review gate is off this session: Claude Code gave no CLAUDE_ENV_FILE"
	exit 0
fi
n=${GIT_CONFIG_COUNT:-0}
if ! printf 'export GIT_CONFIG_KEY_%d=core.hooksPath GIT_CONFIG_VALUE_%d=%q GIT_CONFIG_COUNT=%d\n' \
	"$n" "$n" "$hooks" "$((n + 1))" >>"$CLAUDE_ENV_FILE"; then
	echo "agent-estate: the review gate is off this session: could not write $CLAUDE_ENV_FILE"
fi
exit 0
