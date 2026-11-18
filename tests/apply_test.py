#!/usr/bin/env python3
"""Tests for init/apply.py: run `python3 tests/apply_test.py`. They cover only what it does
outside a git work tree, where its steps never start."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APPLY = Path(__file__).resolve().parent.parent / "init" / "apply.py"
ANSWERS = ["--repo=o/n", "--tracker=scratch", "--ticket-sync=false", "--review-gate=true"]


class OutsideAWorkTree(unittest.TestCase):
    def apply(self, operation):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, APPLY, *ANSWERS, f"--operation={operation}"], cwd=tmp,
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


if __name__ == "__main__":
    unittest.main()
