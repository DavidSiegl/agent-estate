#!/usr/bin/env python3
"""PreToolUse(Bash) hook: refuses a Claude `gh pr create` into the default
branch when the branch changes what the repo's README names but leaves the
README itself unchanged, so the README is checked once per pull request,
before it can merge stale.

Reads the hook's JSON on stdin (`tool_input.command`, `cwd`). Exits 0 to let
the command run; exits 2 with the reason on stderr to refuse it.

The pull request's base is `--base`/`-B` from the command, else the default
branch (origin/HEAD, else `main`); a base other than the default branch is not
checked. Its changes are the current branch's: `git diff BASE...HEAD`, BASE
being origin/<base> when it exists, else the local <base>, else nothing is
checked. Renames count as a delete and an add.

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
still holds. The match is plain text, as in no-verify-push.sh: the repo is the
hook's cwd, `--head` is ignored, and a pull request opened any other way than a
literal `gh pr create` is not seen. Any unexpected state (no git, not a work
tree, unreadable input) lets the command through.
"""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

PR_CREATE = re.compile(r"\bgh\b[^;&|\n]*\bpr\s+create\b")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK_TARGET = re.compile(r"\]\(([^)\s#]+)")


def git(root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", root, *args], capture_output=True,
                          text=True, check=True).stdout


def has_ref(root: str, ref: str) -> bool:
    return subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", ref + "^{commit}"],
                          capture_output=True).returncode == 0


def base_of(cmd: str) -> str | None:
    """The `--base`/`-B` the command names, or None when it names none."""
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    for i, w in enumerate(words):
        if w in ("--base", "-B") and i + 1 < len(words):
            return words[i + 1]
        if w.startswith("--base="):
            return w.removeprefix("--base=")
    return None


def default_branch(root: str) -> str:
    try:
        return git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
    except subprocess.CalledProcessError:
        return "main"


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
        cmd = payload.get("tool_input", {}).get("command") or ""
        cwd = payload.get("cwd") or "."
    except (ValueError, AttributeError):
        return 0
    if not PR_CREATE.search(cmd) or "README_SYNC=checked" in cmd:
        return 0
    try:
        root = git(cwd, "rev-parse", "--show-toplevel").strip()
        default = default_branch(root)
        base = base_of(cmd) or default
        if base != default:
            return 0
        base_ref = next((r for r in (f"origin/{base}", base) if has_ref(root, r)), None)
        readme = readme_of(Path(root))
        if base_ref is None or readme is None:
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
