#!/usr/bin/env python3
"""Tests for trunk-cleanup.py: run `python3 trunk-cleanup_test.py`. Each test
works in a clone of a scratch bare repo whose default branch is main, with
agent.trunkBased on, a stub `gh` that reports the merged pull request heads in
$MERGED_HEADS, and a CLAUDE_CONFIG_DIR with no transcripts."""
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().with_name("trunk-cleanup.py")
GH = """#!/bin/sh
printf '[%s]' "$(printf '%s\\n' $MERGED_HEADS | sed 's/.*/{"headRefOid":"&"}/' | paste -sd, -)"
"""


class Scratch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(GH)
        (bin_dir / "gh").chmod(stat.S_IRWXU)
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MERGED_HEADS": "",
                    "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
                    "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "t",
                    "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "t@t"}
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            self.env.pop(k, None)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.tmp / "origin.git"], check=True)
        self.root = self.tmp / "repo"
        subprocess.run(["git", "clone", "-q", self.tmp / "origin.git", self.root], check=True,
                       env=self.env, capture_output=True)
        self.commit("README.md")
        self.git("push", "-q", "origin", "main")
        self.git("remote", "set-head", "origin", "--auto")
        self.git("config", "agent.trunkBased", "true")

    def git(self, *args, cwd=None, env=None):
        return subprocess.run(["git", "-C", cwd or self.root, *args], check=True, text=True,
                              env={**self.env, **(env or {})}, capture_output=True).stdout.strip()

    def commit(self, rel, cwd=None, when=None):
        cwd = cwd or self.root
        (Path(cwd) / rel).write_text(rel + "\n")
        self.git("add", rel, cwd=cwd)
        dates = {"GIT_AUTHOR_DATE": f"@{when}", "GIT_COMMITTER_DATE": f"@{when}"} if when else {}
        self.git("commit", "-qm", rel, cwd=cwd, env=dates)
        return self.git("rev-parse", "HEAD", cwd=cwd)

    def merge_to_main(self, branch):
        self.git("push", "-q", "origin", f"{branch}:main")
        self.git("fetch", "-q", "origin")

    def hook(self):
        payload = json.dumps({"cwd": str(self.root)})
        r = subprocess.run([HOOK, "hook"], input=payload, capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def run_cli(self, *args):
        r = subprocess.run([HOOK, *args, str(self.root)], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def branches(self):
        return set(self.git("for-each-ref", "--format=%(refname:short)", "refs/heads").split())

    def worktree(self, name, branch):
        path = self.tmp / name
        self.git("worktree", "add", "-q", "-b", branch, str(path))
        return path


class Branches(Scratch):
    def test_not_opted_in_does_nothing(self):
        self.git("config", "--unset", "agent.trunkBased")
        self.git("branch", "done")
        self.assertEqual(self.hook(), "")
        self.assertIn("done", self.branches())

    def test_merged_branch_deleted_unmerged_kept(self):
        self.git("switch", "-qc", "done")
        self.commit("a")
        self.merge_to_main("done")
        self.git("switch", "-qc", "open")
        self.commit("b")
        self.git("switch", "-q", "main")
        out = self.hook()
        self.assertIn("branch done", out)
        self.assertEqual(self.branches(), {"main", "open"})

    def test_squash_merged_branch_deleted_by_pull_request(self):
        self.git("switch", "-qc", "squashed")
        tip = self.commit("a")
        self.git("switch", "-q", "main")
        self.env["MERGED_HEADS"] = tip
        self.hook()
        self.assertNotIn("squashed", self.branches())

    def test_checked_out_branch_kept(self):
        self.git("switch", "-qc", "here")
        self.hook()
        self.assertIn("here", self.branches())

    def test_old_unmerged_branch_reported(self):
        self.git("switch", "-qc", "old")
        self.commit("a", when=int(time.time()) - 3 * 86400)
        self.git("switch", "-q", "main")
        out = self.hook()
        self.assertIn("old: 1 ahead, 0 behind, oldest commit 3 days old", out)
        self.assertIn("old", self.branches())

    def test_dry_run_removes_nothing(self):
        self.git("branch", "done")
        out = self.run_cli("--dry-run")
        self.assertIn("Would remove:\n  branch done", out)
        self.assertIn("done", self.branches())

    def test_no_origin_head_removes_nothing(self):
        # git 2.48+ fetch would otherwise set it again.
        self.git("config", "remote.origin.followRemoteHEAD", "never")
        self.git("remote", "set-head", "origin", "--delete")
        self.git("branch", "done")
        self.assertIn("git remote set-head origin --auto", self.hook())
        self.assertIn("done", self.branches())


class Worktrees(Scratch):
    def test_merged_clean_worktree_removed_with_branch(self):
        path = self.worktree("wt", "w")
        (path / "__pycache__").mkdir()
        (path / ".gitignore").write_text("__pycache__/\n")
        self.git("add", ".gitignore", cwd=path)
        self.git("commit", "-qm", "ignore", cwd=path)
        (path / "__pycache__" / "x.pyc").write_text("")
        self.merge_to_main("w")
        out = self.hook()
        self.assertIn(f"worktree {path} [w]", out)
        self.assertFalse(path.exists())
        self.assertNotIn("w", self.branches())

    def test_untracked_file_keeps_it(self):
        path = self.worktree("wt", "w")
        (path / "notes").write_text("x")
        out = self.hook()
        self.assertIn("unsaved work: ?? notes", out)
        self.assertTrue(path.exists())
        self.assertIn("w", self.branches())

    def test_ignored_scratch_keeps_it(self):
        path = self.worktree("wt", "w")
        (path / ".gitignore").write_text(".scratch/\n")
        self.git("add", ".gitignore", cwd=path)
        self.git("commit", "-qm", "ignore", cwd=path)
        self.merge_to_main("w")
        (path / ".scratch").mkdir()
        (path / ".scratch" / "t.md").write_text("x")
        self.assertIn("unsaved work: !! .scratch/", self.hook())
        self.assertTrue(path.exists())

    def test_locked_keeps_it(self):
        path = self.worktree("wt", "w")
        self.git("worktree", "lock", "--reason", "mine", str(path))
        self.assertIn("locked mine", self.hook())
        self.assertTrue(path.exists())

    def test_live_process_keeps_it(self):
        path = self.worktree("wt", "w")
        p = subprocess.Popen(["sleep", "30"], cwd=path)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        self.assertIn("a process is working in it", self.hook())
        self.assertTrue(path.exists())

    def test_recent_transcript_keeps_it(self):
        path = self.worktree("wt", "w")
        project = self.tmp / "claude" / "projects" / "".join(c if c.isalnum() else "-" for c in str(path))
        project.mkdir(parents=True)
        (project / "s.jsonl").write_text("{}")
        self.assertIn("a Claude session used it", self.hook())
        self.assertTrue(path.exists())

    def test_deleted_directory_pruned(self):
        path = self.worktree("wt", "w")
        subprocess.run(["rm", "-rf", str(path)], check=True)
        self.hook()
        self.assertNotIn(str(path), self.git("worktree", "list"))
        self.assertNotIn("w", self.branches())


if __name__ == "__main__":
    unittest.main()
