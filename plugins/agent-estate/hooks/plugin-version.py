#!/usr/bin/env python3
"""Refuses a pull request into the default branch that changes a Claude Code
plugin's files without raising that plugin's version, so every merge that
changes a plugin reaches the machines that have it installed.

    plugin-version.py              the PreToolUse(Bash) hook
    plugin-version.py BASE HEAD    CI's check of a pull request

Why: Claude Code keys an installed plugin on the `version` in its
`.claude-plugin/plugin.json`. With `autoUpdate` the marketplace's copy follows
the repo, but the installed copy is replaced only when that version changes;
a change merged under the old version never loads anywhere it is installed.
Seen 2026-11-06: an install of 0.1.0 stayed at its first commit while the
marketplace copy was several pull requests and a new skill ahead.

As the hook it reads the hook's JSON on stdin (`tool_input.command`, `cwd`),
and catches a Claude `gh pr create` before the pull request exists. Exits 0 to
let the command run; exits 2 with the reason on stderr to refuse it. Which
commands are checked, and the base their changes are measured from, is
pr_create.pull_request_base's rule.

With BASE and HEAD, any revisions of the repo in the cwd (a pull request's base
and head commits), it judges the change from their merge base to HEAD, so it
also covers a pull request opened in the browser; this repo's
.github/workflows/plugin-version.yml runs it. Exits 0 when the change passes,
1 with the reason on stderr when it does not, and 2 naming the error when it
cannot judge: CI fails closed where the hook lets the command through.

A plugin is a directory holding `.claude-plugin/plugin.json` at HEAD; its files
are everything under that directory. When the branch changes any of them, the
pull request is refused unless the plugin.json's `version` at HEAD is higher
than at the base: compared as dot-separated numbers when both are (`0.10.0` >
`0.9.3`), else it must merely differ. A plugin.json without a `version` and a
plugin new on the branch are never refused. Any unexpected state (no git, not a
work tree, unreadable input, a plugin.json that is not JSON) lets the hook's
command through.
"""
import json
import subprocess
import sys

from pr_create import git, pull_request_base

MANIFEST = ".claude-plugin/plugin.json"


def version_at(root: str, rev: str, path: str) -> str | None:
    """The `version` in the plugin.json at path as of rev; None when the file
    does not exist there or has no version. Raises ValueError naming the file
    when it is not a JSON object."""
    try:
        text = git(root, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None
    try:
        manifest = json.loads(text)
    except ValueError as e:
        raise ValueError(f"{rev}:{path} is not JSON: {e}") from e
    if not isinstance(manifest, dict):
        raise ValueError(f"{rev}:{path} is not a JSON object")
    v = manifest.get("version")
    return str(v) if v is not None else None


def raised(old: str, new: str) -> bool:
    """True when new is a higher version than old; see the module docstring."""
    try:
        return tuple(map(int, new.split("."))) > tuple(map(int, old.split(".")))
    except ValueError:
        return new != old


def stale_plugins(root: str, base_ref: str, head: str = "HEAD") -> list[str]:
    """One line per plugin that head changes since its merge base with base_ref
    without raising its version. Raises CalledProcessError when git fails (an
    unknown revision), ValueError when a plugin.json is not JSON."""
    changed = git(root, "diff", "--name-only", "-z", f"{base_ref}...{head}").split("\0")
    manifests = git(root, "ls-tree", "-r", "-z", "--name-only", head).split("\0")
    lines = []
    for manifest in (m for m in manifests if m == MANIFEST or m.endswith("/" + MANIFEST)):
        plugin = manifest.removesuffix(MANIFEST)  # "" for a plugin at the repo root
        if not any(f and f.startswith(plugin) for f in changed):
            continue
        new = version_at(root, head, manifest)
        old = version_at(root, base_ref, manifest)
        if new is not None and old is not None and not raised(old, new):
            lines.append(f"  {plugin or './'}  (changed; {manifest} still says {new})")
    return lines


def refusal(found: list[str], then: str) -> str:
    """The reason a change with the stale plugins found is refused, ending in
    then: what to do once the version is raised and committed."""
    return ("This branch changes a plugin without raising its version, so installs would never load the change:\n"
            + "\n".join(found) + "\n"
            "Raise `version` in that plugin.json: the patch number for a fix, the minor for a new skill, hook, "
            "agent or command, the major when something users rely on is removed or changes meaning. Commit it, "
            + then)


def hook() -> int:
    """The PreToolUse hook's exit status for the payload on stdin."""
    try:
        pr = pull_request_base(json.load(sys.stdin))
    except ValueError:
        return 0
    if pr is None:
        return 0
    try:
        found = stale_plugins(*pr)
    except (OSError, ValueError, AttributeError, subprocess.CalledProcessError):
        return 0
    if not found:
        return 0
    print(refusal(found, "push, and open the pull request again."), file=sys.stderr)
    return 2


def check(base: str, head: str) -> int:
    """CI's exit status for the change from base to head in the cwd's repo."""
    try:
        found = stale_plugins(".", base, head)
    except subprocess.CalledProcessError as e:
        print(f"plugin-version.py: {' '.join(e.cmd)}: {e.stderr.strip()}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"plugin-version.py: {e}", file=sys.stderr)
        return 2
    if not found:
        return 0
    print(refusal(found, "and push."), file=sys.stderr)
    return 1


def main() -> int:
    """Run as the hook with no arguments, as CI's check with BASE HEAD."""
    if len(sys.argv) == 1:
        return hook()
    if len(sys.argv) == 3:
        return check(sys.argv[1], sys.argv[2])
    print("usage: plugin-version.py [BASE HEAD]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
