#!/usr/bin/env python3
"""PreToolUse(Bash) hook: refuses a Claude `gh pr create` into the default
branch when the branch changes what the repo's README names but leaves the
README itself unchanged, so the README is checked once per pull request,
before it can merge stale.

Reads the hook's JSON on stdin (`tool_input.command`, `cwd`). Exits 0 to let
the command run; exits 2 with the reason on stderr to refuse it.

Which commands are checked, and the base their changes are measured from, is
pr_create.pull_request_base's rule. Renames count as a delete and an add.

The README is the first file at the repo root named README, README.md and so
on; a repo without one is never checked. What it names are its inline code
spans and relative link targets that look like paths (contain `/` or `.`, no
spaces, not starting with `~`, `/` or `$`); a trailing `/` or `/*` is dropped.
A pull request is refused when the README is not among its changed files and
one of them
  - is a named path, or ends in `/` + a named path (`hooks/hooks.json` names
    plugins/agent-estate/hooks/hooks.json), or
  - is added or deleted under a named directory, since that may change what
    the README lists there. A file merely modified there is not enough.

`README_SYNC=checked` in the command lets it through: the README was read and
still holds. Any unexpected state (no git, not a work tree, unreadable input)
lets the command through.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from pr_create import git, pull_request_base

CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK_TARGET = re.compile(r"\]\(([^)\s#]+)")


def readme_of(root: Path) -> Path | None:
    """The README at root, or None when there is none."""
    found = sorted(p for p in root.iterdir() if p.is_file() and p.name.split(".")[0] == "README")
    return found[0] if found else None


def named_paths(text: str) -> set[str]:
    """The repo-relative paths a README's text names; see the module docstring."""
    names = set()
    for raw in CODE_SPAN.findall(text) + LINK_TARGET.findall(text):
        raw = raw.strip()
        m = raw.removeprefix("./").removesuffix("/*").rstrip("/")
        if (m and " " not in m and ("/" in raw or "." in raw)
                and m[0] not in "~/$" and "://" not in m):
            names.add(m)
    return names


def changed_files(root: str, base_ref: str) -> list[tuple[str, str]]:
    """(status letter, path) for each file the branch changes since base_ref."""
    out = git(root, "diff", "--no-renames", "--name-status", "-z", f"{base_ref}...HEAD")
    fields = out.split("\0")
    return [(fields[i][0], fields[i + 1]) for i in range(0, len(fields) - 1, 2)]


def reasons(files: list[tuple[str, str]], names: set[str]) -> list[str]:
    """One line per changed file the README names, saying which name it matched."""
    lines = []
    for status, path in files:
        for m in sorted(names):
            if path == m or path.endswith("/" + m):
                lines.append(f"  {path}  (README names `{m}`)")
                break
            if status in "AD" and (path.startswith(m + "/") or f"/{m}/" in path):
                verb = "adds" if status == "A" else "deletes"
                lines.append(f"  {path}  ({verb} a file under `{m}`, which README names)")
                break
    return lines


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    pr = pull_request_base(payload)
    if pr is None or "README_SYNC=checked" in (payload["tool_input"].get("command") or ""):
        return 0
    root, base_ref = pr
    try:
        readme = readme_of(Path(root))
        if readme is None:
            return 0
        files = changed_files(root, base_ref)
        if any(path == readme.name for _, path in files):
            return 0
        found = reasons(files, named_paths(readme.read_text(errors="replace")))
    except (OSError, subprocess.CalledProcessError):
        return 0
    if not found:
        return 0
    shown = found[:10] + ([f"  ... and {len(found) - 10} more"] if len(found) > 10 else [])
    print(f"This branch changes what {readme.name} describes, and leaves {readme.name} unchanged:\n"
          + "\n".join(shown) + "\n"
          f"Check what {readme.name} says about each (the agent-estate:readme-sync skill says how). "
          f"If something no longer holds, commit a fix to {readme.name}, push, and open the pull "
          "request again. If it all still holds, rerun the command with README_SYNC=checked in "
          "front of it.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
