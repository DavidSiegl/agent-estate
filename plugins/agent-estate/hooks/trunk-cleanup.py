#!/usr/bin/env python3
"""Removes a repo's merged worktrees and branches, and names the branches that
have stayed off the default branch too long: the cleanup half of the
trunk-based skill.

    trunk-cleanup.py hook                 the SessionStart hook
    trunk-cleanup.py [--dry-run] [REPO]   on demand, REPO defaulting to the cwd

As the hook it reads the hook's JSON on stdin (`cwd`) and acts only in a repo
whose git config has `agent.trunkBased` set to true (the trunk-based skill's
`on`); elsewhere it prints nothing and changes nothing. On demand it acts in
any repo; --dry-run reports what it would remove and removes nothing. What it
prints is a report for Claude: SessionStart puts stdout in the session's
context. Always exits 0, so a failure here never blocks a session; a failure
is reported instead.

It first fetches origin with --prune (no credential prompt), then judges
against origin's default branch, refs/remotes/origin/HEAD; without that ref it
removes nothing and says how to set it. A failed fetch is reported and the
judgment uses the refs as last fetched, which can only make less look merged.

A linked worktree is removed when all of these hold, and kept, with the
reason, otherwise:
  - its HEAD is merged (below);
  - it is not locked, and not under a dot-directory of the main checkout other
    than .claude/ (a tool's own worktrees, such as .orchestrator/worktrees/,
    are the tool's to remove);
  - no process has its cwd inside it (read from /proc; without /proc every
    worktree is kept), and no Claude Code or pi session started in it was
    written to in the last LIVE_SESSION_SECONDS;
  - `git status --ignored` shows no change, no untracked file, and no ignored
    path outside REGENERABLE.
The main checkout is never removed. Worktree records whose directory is gone
are pruned (`git worktree prune`, which leaves locked ones).

A local branch other than the default is deleted when it is checked out in no
worktree (after the removals above) and its tip is merged. The deletion is a
compare-and-delete of the tip that was judged, so a branch that moved
meanwhile stays.

A commit is merged when it is an ancestor of origin's default branch, or is
the head commit of a merged pull request (`gh pr list --state merged`, which
covers squash and rebase merges); without a working gh only the first test is
made. A branch that never left the default branch's history counts as merged:
deleting it loses no commit.

Every branch that remains is reported with how far it is ahead of and behind
the default branch when its oldest unmerged commit is older than
STALE_BRANCH_SECONDS or its upstream is gone, which is the trunk-based skill's
cue to merge, rebase or ask the user about it.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# A session idle this long is taken as over: its transcript would have been
# written if it were still working there.
LIVE_SESSION_SECONDS = 24 * 3600
# The trunk-based skill's limit on how long work stays off the default branch.
STALE_BRANCH_SECONDS = 24 * 3600
# Ignored directories that builds and tools recreate, matched against every
# component of an ignored path; any other ignored path counts as work (above
# all .scratch/, which holds tickets and review records).
REGENERABLE = {"__pycache__", "node_modules", ".venv", "venv", "target", ".pytest_cache",
               ".mypy_cache", ".ruff_cache", ".tox", ".gradle", "dist", "build"}
FETCH_TIMEOUT = 30


def git(root, *args, check=True, timeout=None):
    """git's stdout for `git -C root args`; raises CalledProcessError when git
    exits non-zero and check is set, OSError when git cannot run,
    TimeoutExpired past timeout seconds."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=check, timeout=timeout, env=env).stdout


@dataclass
class Worktree:
    """One entry of `git worktree list --porcelain`. branch is the short name,
    None when detached; locked and prunable hold git's reason ("" when it gave
    none) or None when the entry is neither."""
    path: Path
    head: str
    branch: str | None = None
    locked: str | None = None
    prunable: str | None = None


@dataclass
class Report:
    """What one run did and found, as lines for the session."""
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    lagging: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def text(self, repo, dry_run):
        sections = [("Would remove" if dry_run else "Removed", self.removed),
                    ("Kept, though merged", self.kept),
                    ("Off the default branch too long (merge it, rebase it, or ask the user)", self.lagging),
                    ("Problems", self.problems)]
        body = [f"{title}:\n" + "\n".join(f"  {line}" for line in lines)
                for title, lines in sections if lines]
        if not body:
            return ""
        return f"trunk-cleanup ({repo}):\n" + "\n".join(body) + "\n"


def worktrees(root):
    """Every worktree of the repo at root, the main checkout first."""
    found = []
    for block in git(root, "worktree", "list", "--porcelain").split("\n\n"):
        wt = None
        for line in block.splitlines():
            word, _, rest = line.partition(" ")
            if word == "worktree":
                wt = Worktree(Path(rest), "")
            elif wt is None:
                continue
            elif word == "HEAD":
                wt.head = rest
            elif word == "branch":
                wt.branch = rest.removeprefix("refs/heads/")
            elif word == "locked":
                wt.locked = rest
            elif word == "prunable":
                wt.prunable = rest
        if wt:
            found.append(wt)
    return found


class Judge:
    """Decides whether a commit is merged into origin's default branch."""

    def __init__(self, root, default_ref):
        self.root = root
        self.default_ref = default_ref
        self.pr_heads = self._merged_pr_heads()

    def _merged_pr_heads(self):
        try:
            out = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", "1000",
                                  "--json", "headRefOid"], cwd=self.root, capture_output=True,
                                 text=True, check=True, timeout=FETCH_TIMEOUT).stdout
            return {pr["headRefOid"] for pr in json.loads(out)}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            return set()

    def merged(self, commit):
        if commit in self.pr_heads:
            return True
        return subprocess.run(["git", "-C", str(self.root), "merge-base", "--is-ancestor",
                               commit, self.default_ref], capture_output=True).returncode == 0


def project_dir_name(path):
    """Claude Code's transcript directory name for a session started at path;
    a name over 200 characters is matched by its first 200 and a "-", since
    Claude Code appends a hash to it (automate-me's claude-project-dir.mjs has
    the rule)."""
    name = re.sub(r"[^A-Za-z0-9]", "-", str(path))
    return name if len(name) <= 200 else name[:200] + "-"


def recent_session(path, now):
    """True when a Claude Code transcript or a pi session file of a session
    started at path was written in the last LIVE_SESSION_SECONDS. pi sessions
    are looked for only where pi keeps them by default, under
    $PI_CODING_AGENT_DIR (~/.pi/agent) and not in a sessionDir set elsewhere."""
    config = os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"
    projects = Path(config) / "projects"
    name = project_dir_name(path)
    try:
        dirs = [d for d in projects.iterdir()
                if d.name == name or (name.endswith("-") and d.name.startswith(name))]
    except OSError:
        dirs = []
    dirs.append(pi_session_dir(path))
    return any(now - f.stat().st_mtime < LIVE_SESSION_SECONDS
               for d in dirs for f in d.rglob("*.jsonl"))


def pi_session_dir(path):
    """pi's default session directory for a session started at path
    (getDefaultSessionDirPath in pi-coding-agent's dist/core/session-manager.js)."""
    agent = os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi" / "agent"
    name = "--" + re.sub(r"[/\\:]", "-", re.sub(r"^[/\\]", "", str(path))) + "--"
    return Path(agent).expanduser() / "sessions" / name


def process_cwds():
    """The cwd of every process this user can see; None when /proc cannot be
    read, so that no worktree can be shown to be free."""
    try:
        procs = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except OSError:
        return None
    cwds = set()
    for p in procs:
        try:
            cwds.add(Path(os.readlink(p / "cwd")))
        except OSError:
            continue
    return cwds


def unsaved_work(path):
    """The first `git status` line in the worktree at path that is work: a
    change, an untracked file, or an ignored path outside REGENERABLE; None
    when there is none."""
    for line in git(path, "status", "--porcelain", "--ignored", "--untracked-files=all").splitlines():
        if line.startswith("!! ") and REGENERABLE & set(Path(line[3:]).parts):
            continue
        return line
    return None


def keep_reason(wt, main, judge, cwds, now):
    """Why the linked worktree wt must stay, or None when it may go."""
    if not judge.merged(wt.head):
        return "not merged"
    if wt.locked is not None:
        return f"locked {wt.locked}".strip()
    try:
        inside = wt.path.relative_to(main)
        if inside.parts and inside.parts[0].startswith(".") and inside.parts[0] != ".claude":
            return f"under {inside.parts[0]}/, which its tool manages"
    except ValueError:
        pass
    if cwds is None:
        return "cannot read /proc to rule out a live session"
    if any(c.is_relative_to(wt.path) for c in cwds):
        return "a process is working in it"
    if recent_session(wt.path, now):
        return "a Claude Code or pi session used it in the last day"
    work = unsaved_work(wt.path)
    if work:
        return f"unsaved work: {work}"
    return None


def label(wt):
    return f"{wt.path} [{wt.branch or 'detached ' + wt.head[:8]}]"


def clean_worktrees(root, judge, report, dry_run, now):
    """Removes the linked worktrees keep_reason lets go, and prunes records of
    deleted ones."""
    all_wts = worktrees(root)
    main = all_wts[0].path
    cwds = process_cwds()
    for wt in all_wts[1:]:
        if wt.prunable is not None:
            continue
        why = keep_reason(wt, main, judge, cwds, now)
        if why == "not merged":
            continue
        if why:
            report.kept.append(f"{label(wt)}: {why}")
            continue
        if not dry_run:
            try:
                git(root, "worktree", "remove", str(wt.path))
            except subprocess.CalledProcessError as e:
                report.kept.append(f"{label(wt)}: git worktree remove refused: {e.stderr.strip()}")
                continue
        report.removed.append(f"worktree {label(wt)}")
    if not dry_run:
        git(root, "worktree", "prune")


def clean_branches(root, default, judge, report, dry_run, now):
    """Deletes merged branches no worktree has checked out; reports the
    others that are old or whose upstream is gone."""
    checked_out = {wt.branch for wt in worktrees(root) if wt.branch}
    fmt = "%(refname:short)%00%(objectname)%00%(upstream:track)"
    for line in git(root, "for-each-ref", f"--format={fmt}", "refs/heads").splitlines():
        name, tip, track = line.split("\0")
        if name == default or name in checked_out:
            continue
        if judge.merged(tip):
            if not dry_run:
                try:
                    git(root, "update-ref", "-d", f"refs/heads/{name}", tip)
                except subprocess.CalledProcessError as e:
                    report.problems.append(f"could not delete branch {name}: {e.stderr.strip()}")
                    continue
                git(root, "config", "--remove-section", f"branch.{name}", check=False)
            report.removed.append(f"branch {name} ({tip[:8]})")
            continue
        report_lag(root, name, tip, judge.default_ref, track, report, now)


def report_lag(root, name, tip, default_ref, track, report, now):
    """Adds branch name to report.lagging when its oldest commit off the
    default branch is older than STALE_BRANCH_SECONDS or its upstream is gone."""
    times = git(root, "log", "--format=%ct", f"{default_ref}..{tip}").split()
    age = int(now) - int(times[-1]) if times else 0
    gone = track == "[gone]"
    if age < STALE_BRANCH_SECONDS and not gone:
        return
    behind = git(root, "rev-list", "--count", f"{tip}..{default_ref}").strip()
    notes = [f"{len(times)} ahead", f"{behind} behind", f"oldest commit {age // 86400} days old"]
    if gone:
        notes.append("upstream gone without the branch being merged")
    report.lagging.append(f"{name}: " + ", ".join(notes))


def clean(repo, dry_run=False):
    """Runs the cleanup on the repo containing the directory repo and returns
    the report's text, "" when there is nothing to say. Raises OSError or
    SubprocessError when git cannot run or fails outside the steps the module
    docstring says are reported."""
    report = Report()
    root = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    try:
        git(root, "fetch", "--quiet", "--prune", "--no-recurse-submodules", "origin", timeout=FETCH_TIMEOUT)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        detail = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) else "timed out"
        report.problems.append(f"git fetch origin failed, judging on refs as last fetched: {detail}")
    try:
        default_ref = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    except subprocess.CalledProcessError:
        report.problems.append("no refs/remotes/origin/HEAD, so nothing can be shown merged; "
                               "set it with `git remote set-head origin --auto`")
        return report.text(root, dry_run)
    judge = Judge(root, default_ref)
    now = time.time()
    clean_worktrees(root, judge, report, dry_run, now)
    clean_branches(root, default_ref.removeprefix("origin/"), judge, report, dry_run, now)
    return report.text(root, dry_run)


def hook():
    """The SessionStart hook: clean the repo at the payload's cwd if it opted in."""
    try:
        cwd = json.load(sys.stdin).get("cwd") or "."
    except (ValueError, AttributeError):
        return
    if git(cwd, "config", "--get", "agent.trunkBased", check=False).strip() == "true":
        print(clean(cwd), end="")


def main():
    if sys.argv[1:] == ["hook"]:
        run = hook
    else:
        p = argparse.ArgumentParser(description="Remove merged worktrees and branches.")
        p.add_argument("--dry-run", action="store_true", help="report, remove nothing")
        p.add_argument("repo", nargs="?", default=".")
        args = p.parse_args()

        def run():
            print(clean(args.repo, args.dry_run) or "trunk-cleanup: nothing to report")
    try:
        run()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"trunk-cleanup: stopped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
