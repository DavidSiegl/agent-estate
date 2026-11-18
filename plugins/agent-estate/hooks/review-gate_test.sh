#!/usr/bin/env bash
# Tests for the review gate, git/pre-push: run `bash review-gate_test.sh`; exits
# non-zero on a failure. Real pushes into a bare remote, with core.hooksPath
# set the way ../git-hooks-path.sh sets it for Claude: a main checkout with
# .scratch/reviews, a branch b with an unreviewed commit, a linked worktree on b.
set -u
HOOKS=${HOOKS:-$(cd "$(dirname "$0")/git" && pwd)}
T=$(mktemp -d) || exit 1
trap 'chmod -R u+rwX "$T"; rm -rf "$T"' EXIT
export GIT_CONFIG_COUNT=3 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=$HOOKS \
    GIT_CONFIG_KEY_1=user.name GIT_CONFIG_VALUE_1=t GIT_CONFIG_KEY_2=user.email GIT_CONFIG_VALUE_2=t@t
g() { git "$@" >/dev/null 2>&1; }

g init -q --bare -b main "$T/remote.git"
g init -q -b main "$T/repo" && g -C "$T/repo" commit --allow-empty -m m
g -C "$T/repo" remote add origin "$T/remote.git"
g -C "$T/repo" branch b && g -C "$T/repo" checkout -q b && g -C "$T/repo" commit --allow-empty -m b && g -C "$T/repo" checkout -q main
g -C "$T/repo" tag v1 b
g -C "$T/repo" worktree add "$T/repo-wt" b
g init -q -b main "$T/plain" && g -C "$T/plain" commit --allow-empty -m p && g -C "$T/plain" remote add origin "$T/remote.git"
M=$(git -C "$T/repo" rev-parse main); B=$(git -C "$T/repo" rev-parse b)
mkdir -p "$T/repo/.scratch/reviews"
printf 'Head: %s\nVerdict: pass\n' "$M" > "$T/repo/.scratch/reviews/01-main.md"
printf 'Head: %s\nVerdict: findings\n' "$B" > "$T/repo/.scratch/reviews/02-b.md"

fail=0
# expected exit (0 pushed, 1 refused), directory, push arguments; REVIEW_GATE
# may be set in the environment of the call.
check() {
    local want=$1 dir=$2 out rc
    shift 2
    out=$(git -C "$dir" push -q "$@" 2>&1)
    rc=$?
    [ "$rc" = 0 ] || rc=1
    if [ "$rc" = "$want" ]; then echo "ok   $rc  [$dir] $*"; else echo "FAIL $rc (want $want)  [$dir] $*"; echo "$out" | head -4; fail=1; fi
}
R=$T/repo W=$T/repo-wt

check 0 "$R" origin main
check 1 "$R" origin b
check 1 "$R" origin main:other b
check 1 "$R" --all origin
check 1 "$R" origin v1
check 1 "$W" -u origin b
check 1 "$W" origin HEAD:refs/heads/other
check 0 "$R" origin main            # up to date: no ref to update
REVIEW_GATE=off check 0 "$R" origin b
check 0 "$R" origin :b              # a deletion sends no commit
check 0 "$T/plain" origin main:plain
# A record the gate cannot read fails open.
chmod 000 "$T/repo/.scratch/reviews/02-b.md"
check 0 "$R" origin b:unreadable
chmod 644 "$T/repo/.scratch/reviews/02-b.md"
g -C "$R" push -q origin :unreadable

printf 'Head: %s\nVerdict: pass\n' "$B" > "$T/repo/.scratch/reviews/02-b.md"
check 0 "$W" -u origin b
check 0 "$R" origin v1
# A worktree with a .scratch/reviews of its own still reads the main checkout's.
mkdir -p "$W/.scratch/reviews"
check 0 "$W" origin b:wt
# Off the remote again, so that the record alone decides (see below for a commit it has).
g -C "$R" push -q origin :b :wt
printf 'Head: %s\nVerdict: findings\n' "$B" > "$T/repo/.scratch/reviews/02-b.md"
check 1 "$W" origin b:wt2

# A tag on a commit already on the remote's default branch (refs/remotes/origin/HEAD) needs no
# record: a release tag on the merge GitHub made. Not a branch to that commit, not a tag on a
# commit on another remote branch, not another remote, a URL, or a remote with a pushurl.
g -C "$R" checkout -q -b c main && g -C "$R" commit --allow-empty -m c && g -C "$R" checkout -q main
REVIEW_GATE=off check 0 "$R" origin c:main
g -C "$R" checkout -q -b d main && g -C "$R" commit --allow-empty -m d && g -C "$R" checkout -q main
REVIEW_GATE=off check 0 "$R" origin d
g -C "$R" remote set-head origin main
g -C "$R" tag v2 c && g -C "$R" tag v3 d
check 0 "$R" origin v2
check 0 "$W" origin refs/tags/v2:refs/tags/v2-wt
check 1 "$R" origin c:refs/heads/c2
check 1 "$R" origin v3
g init -q --bare -b main "$T/other.git" && g -C "$R" remote add other "$T/other.git"
check 1 "$R" other v2
check 1 "$R" "$T/remote.git" refs/tags/v2:refs/tags/v2-by-url
git -C "$R" config remote.origin.pushurl "$T/other.git"
check 1 "$R" origin refs/tags/v2:refs/tags/v2-pushurl
git -C "$R" config --unset remote.origin.pushurl

# The repo's own hooks still run: pre-push after the gate, the others through passthrough.
printf '#!/bin/sh\nexit 1\n' > "$T/repo/.git/hooks/pre-push" && chmod +x "$T/repo/.git/hooks/pre-push"
check 1 "$R" origin main:local-hook
rm "$T/repo/.git/hooks/pre-push"
printf '#!/bin/sh\ntouch "%s/pre-commit-ran"\n' "$T" > "$T/repo/.git/hooks/pre-commit" && chmod +x "$T/repo/.git/hooks/pre-commit"
g -C "$R" commit -q --allow-empty -m c
if [ -e "$T/pre-commit-ran" ]; then echo "ok   the repo's pre-commit ran"; else echo "FAIL the repo's pre-commit did not run"; fail=1; fi

# A repo that keeps its hooks under its own core.hooksPath (husky) still gets them.
mkdir "$T/repo/.husky"
printf '#!/bin/sh\nexit 1\n' > "$T/repo/.husky/pre-commit" && chmod +x "$T/repo/.husky/pre-commit"
cp "$T/repo/.husky/pre-commit" "$T/repo/.husky/pre-push"
git -C "$R" config core.hooksPath .husky
if git -C "$R" commit -q --allow-empty -m h 2>/dev/null; then echo "FAIL .husky/pre-commit did not run"; fail=1; else echo "ok   .husky/pre-commit ran"; fi
check 1 "$R" origin "$M:refs/heads/husky"   # reviewed: refused by .husky/pre-push alone
# One that points core.hooksPath at the gate's own directory does not recurse.
git -C "$R" config core.hooksPath "$HOOKS"
if timeout 20 git -C "$R" commit -q --allow-empty -m loop; then echo "ok   no recursion"; else echo "FAIL commit with core.hooksPath = the gate's directory"; fail=1; fi
check 0 "$R" origin "$M:refs/heads/loop"
git -C "$R" config --unset core.hooksPath

# no-verify-push.sh, the PreToolUse guard: payloads as Claude Code sends them.
guard() { # expected exit, command
    local rc
    jq -nc --arg c "$2" '{tool_name:"Bash", tool_input:{command:$c}}' | bash "$HOOKS/../no-verify-push.sh" 2>/dev/null
    rc=$?
    if [ "$rc" = "$1" ]; then echo "ok   $rc  guard: $2"; else echo "FAIL $rc (want $1)  guard: $2"; fail=1; fi
}
P=pu; P=${P}sh   # keeps the word out of this script's own command line
guard 2 "git $P --no-verify origin b"
guard 2 "cd x && git $P origin b --no-verify 2>&1"
guard 2 "git commit --no-verify -m x && git $P"
guard 0 "git $P origin b"
guard 0 "git commit --no-verify -m x"
guard 0 "REVIEW_GATE=off git $P --no-verify origin b"
exit $fail
