#!/usr/bin/env python3
"""Tests for init/apply.py: run `python3 tests/apply_test.py`. They cover what it does outside
a git work tree, where its steps never start, and its AGENTS.md step in a scratch repo with
the scratch tracker, no ticket sync and no gate, so no step calls gh."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APPLY = Path(__file__).resolve().parent.parent / "init" / "apply.py"
ANSWERS = ["--repo=o/n", "--tracker=scratch", "--ticket-sync=false", "--review-gate=true"]
# The environment without git's repository overrides, which a hook or `git rebase -x` exports:
# with GIT_DIR set, apply.py and git init would act on that repo instead of the scratch one.
ENV = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}


class OutsideAWorkTree(unittest.TestCase):
    def apply(self, operation):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, APPLY, *ANSWERS, f"--operation={operation}"], cwd=tmp, env=ENV,
                               capture_output=True, text=True, check=False)
            return r, list(Path(tmp).iterdir())

    def test_copy_fails_naming_the_reason_and_writes_nothing(self):
        r, written = self.apply("copy")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is not in a git work tree", r.stderr)
        self.assertEqual(written, [])

    def test_update_is_a_scratch_render_left_alone(self):
        r, written = self.apply("update")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(written, [])


class AgentsPointer(unittest.TestCase):
    POINTER = "Read docs/agents/README.md"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        subprocess.run(["git", "init", "-q", self.root], env=ENV, check=True)
        self.agents = self.root / "AGENTS.md"

    def apply(self):
        r = subprocess.run([sys.executable, APPLY, *ANSWERS, "--operation=update"], cwd=self.root, env=ENV,
                           capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_missing_is_created_holding_the_pointer(self):
        self.apply()
        self.assertIn(self.POINTER, self.agents.read_text(encoding="utf-8"))

    def test_present_without_it_gains_the_pointer_after_its_own_text(self):
        self.agents.write_text("# Ours\n\nKeep this.\n", encoding="utf-8")
        self.apply()
        text = self.agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Ours\n\nKeep this.\n"), text)
        self.assertIn(self.POINTER, text)

    def test_present_with_it_is_left_as_it_is(self):
        self.apply()
        before = self.agents.read_text(encoding="utf-8")
        out = self.apply()
        self.assertEqual(self.agents.read_text(encoding="utf-8"), before)
        self.assertNotIn("AGENTS.md", out)

    def test_an_older_wording_of_the_pointer_is_not_added_to(self):
        self.agents.write_text("# Ours\n\nSee docs/agents/README.md first.\n", encoding="utf-8")
        self.apply()
        self.assertEqual(self.agents.read_text(encoding="utf-8"), "# Ours\n\nSee docs/agents/README.md first.\n")

    def test_a_symlink_to_claude_md_is_left_alone(self):
        os.symlink("CLAUDE.md", self.agents)
        self.apply()
        self.assertTrue(self.agents.is_symlink())
        self.assertNotIn(self.POINTER, (self.root / "CLAUDE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
