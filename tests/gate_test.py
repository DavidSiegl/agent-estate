#!/usr/bin/env python3
"""Tests for the template's python scripts/gate: run `python3 tests/gate_test.py` (needs jinja2,
which renders the template as Copier would). Each test runs the rendered gate in a scratch
repository whose tag `main` sits on its first commit, with a `curl` that always fails and an
empty gate.py cache, so a run that reaches the download stops there: these tests cover what the
gate decides before it judges anything."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = next((ROOT / "template").glob("*scripts*/*gate == 'python'*"))
ENV = {**os.environ, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name",
       "GIT_CONFIG_VALUE_0": "t", "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "t@t"}


class Gate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "trunk")
        self.write("pkg/x.py", "1")
        gate = self.write("scripts/gate", jinja2.Environment(keep_trailing_newline=True)
                          .from_string(TEMPLATE.read_text()).render(ci="jenkins", python_package="pkg"))
        gate.chmod(gate.stat().st_mode | stat.S_IEXEC)
        self.git("add", "--all")
        self.git("commit", "-qm", "first")
        self.git("tag", "main")
        self.write("pkg/x.py", "2")
        self.git("commit", "-qam", "second")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text("#!/bin/sh\necho 'curl: offline' >&2\nexit 22\n")
        curl.chmod(0o755)

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, *args], check=True, env=ENV, capture_output=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def run_gate(self, *args):
        env = {**ENV, "PATH": f"{self.bin}:{ENV['PATH']}", "XDG_CACHE_HOME": str(self.tmp / "cache")}
        return subprocess.run(["scripts/gate", *args], cwd=self.root, env=env,
                              capture_output=True, text=True, check=False)

    def test_the_default_base_is_the_branch_main_never_a_tag_main(self):
        r = self.run_gate()
        self.assertEqual(r.returncode, 2)
        self.assertIn("gate: refs/heads/main is not a commit", r.stderr)

    def test_a_base_that_is_no_commit_fails_naming_it_before_the_download(self):
        r = self.run_gate("nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("gate: nope is not a commit", r.stderr)
        self.assertNotIn("curl", r.stderr)


if __name__ == "__main__":
    unittest.main()
