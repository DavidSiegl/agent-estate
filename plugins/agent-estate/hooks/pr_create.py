"""What the PreToolUse(Bash) hooks that check a pull request before it opens
(readme-sync.py, plugin-version.py) share: recognising a Claude `gh pr create`
into the default branch, and the ref its changes are measured from.

The match is plain text, as in no-verify-push.sh: the repo is the hook's cwd,
`--head` is ignored, and a pull request opened any other way than a literal
`gh pr create` is not seen.
"""
import re
import shlex
import subprocess

PR_CREATE = re.compile(r"\bgh\b[^;&|\n]*\bpr\s+create\b")


def git(root: str, *args: str) -> str:
    """git's stdout for `git -C root args`; raises CalledProcessError when git
    exits non-zero, OSError when git cannot run."""
    return subprocess.run(["git", "-C", root, *args], capture_output=True,
                          text=True, check=True).stdout


def pull_request_base(payload: dict) -> tuple[str, str] | None:
    """(repo toplevel, base ref) when the hook payload's `tool_input.command`
    opens a pull request into the default branch of the repo at its `cwd`;
    None otherwise.

    The pull request's base is `--base`/`-B` from the command, else the default
    branch (origin/HEAD, else `main`); a base other than the default branch
    gives None. The base ref is origin/<base> when it exists, else the local
    <base>, else None. Its changes are then `BASE_REF...HEAD`. Malformed input
    and any git failure (no git, not a work tree) give None too, so a hook built
    on this lets the command through whenever it cannot tell.
    """
    try:
        cmd = payload.get("tool_input", {}).get("command") or ""
        cwd = payload.get("cwd") or "."
    except AttributeError:
        return None
    if not PR_CREATE.search(cmd):
        return None
    try:
        root = git(cwd, "rev-parse", "--show-toplevel").strip()
        default = _default_branch(root)
        if (_base_of(cmd) or default) != default:
            return None
        ref = next((r for r in (f"origin/{default}", default) if _has_ref(root, r)), None)
    except (OSError, subprocess.CalledProcessError):
        return None
    return (root, ref) if ref else None


def _has_ref(root: str, ref: str) -> bool:
    return subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", ref + "^{commit}"],
                          capture_output=True).returncode == 0


def _base_of(cmd: str) -> str | None:
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


def _default_branch(root: str) -> str:
    try:
        return git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
    except subprocess.CalledProcessError:
        return "main"
