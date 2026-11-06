#!/usr/bin/env python3
"""PreToolUse(Bash) hook: refuses a Claude `gh pr create` into the default
branch when the branch changes a Claude Code plugin's files without raising
that plugin's version, so every merge that changes a plugin reaches the
machines that have it installed.

Why: Claude Code keys an installed plugin on the `version` in its
`.claude-plugin/plugin.json`. With `autoUpdate` the marketplace's copy follows
the repo, but the installed copy is replaced only when that version changes;
a change merged under the old version never loads anywhere it is installed.
Seen 2026-11-06: an install of 0.1.0 stayed at its first commit while the
marketplace copy was several pull requests and a new skill ahead.

Reads the hook's JSON on stdin (`tool_input.command`, `cwd`). Exits 0 to let
the command run; exits 2 with the reason on stderr to refuse it. Which commands
are checked, and the base their changes are measured from, is
pr_create.pull_request_base's rule.

A plugin is a directory holding `.claude-plugin/plugin.json` at HEAD; its files
are everything under that directory. When the branch changes any of them, the
pull request is refused unless the plugin.json's `version` at HEAD is higher
than at the base: compared as dot-separated numbers when both are (`0.10.0` >
`0.9.3`), else it must merely differ. A plugin.json without a `version` and a
plugin new on the branch are never refused. Any unexpected state (no git, not a
work tree, unreadable input, a plugin.json that is not JSON) lets the command
through.
"""
import json
import subprocess
import sys

from pr_create import git, pull_request_base

MANIFEST = ".claude-plugin/plugin.json"


def version_at(root: str, rev: str, path: str) -> str | None:
    """The `version` in the plugin.json at path as of rev; None when the file
    does not exist there or has no version."""
    try:
        text = git(root, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None
    v = json.loads(text).get("version")
    return str(v) if v is not None else None


def raised(old: str, new: str) -> bool:
    """True when new is a higher version than old; see the module docstring."""
    try:
        return tuple(map(int, new.split("."))) > tuple(map(int, old.split(".")))
    except ValueError:
        return new != old


def stale_plugins(root: str, base_ref: str) -> list[str]:
    """One line per plugin the branch changes without raising its version."""
    changed = git(root, "diff", "--name-only", "-z", f"{base_ref}...HEAD").split("\0")
    manifests = git(root, "ls-tree", "-r", "-z", "--name-only", "HEAD").split("\0")
    lines = []
    for manifest in (m for m in manifests if m == MANIFEST or m.endswith("/" + MANIFEST)):
        plugin = manifest.removesuffix(MANIFEST)  # "" for a plugin at the repo root
        if not any(f and f.startswith(plugin) for f in changed):
            continue
        new = version_at(root, "HEAD", manifest)
        old = version_at(root, base_ref, manifest)
        if new is not None and old is not None and not raised(old, new):
            lines.append(f"  {plugin or './'}  (changed; {manifest} still says {new})")
    return lines


def main() -> int:
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
    print("This branch changes a plugin without raising its version, so installs would never load the change:\n"
          + "\n".join(found) + "\n"
          "Raise `version` in that plugin.json: the patch number for a fix, the minor for a new skill, hook, "
          "agent or command, the major when something users rely on is removed or changes meaning. Commit it, "
          "push, and open the pull request again.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
