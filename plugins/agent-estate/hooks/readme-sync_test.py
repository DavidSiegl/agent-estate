#!/usr/bin/env python3
"""Tests for readme-sync.py: run `python3 readme-sync_test.py`. Each test feeds
the hook a `gh pr create` from branch `b` of a scratch repo with no remote,
so the base is the local `main`. Its README names `plugins/x/hooks/hooks.json`,
`init/apply.py` and the directory `skills/`."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().with_name("readme-sync.py")
README = """# r

- `plugins/x/hooks/hooks.json` is described [here](init/apply.py).
- `skills/` holds the skills. Run `uvx copier copy` or see `~/.claude/settings.json`.
"""
ENV = {**os.environ, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name",
       "GIT_CONFIG_VALUE_0": "t", "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "t@t"}
PR = "gh pr create --fill"


class ReadmeSync(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", README)
        for f in ("plugins/x/hooks/hooks.json", "init/apply.py", "skills/a/SKILL.md", "other.txt"):
            self.write(f, "1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "init")
        self.git("switch", "-qc", "b")

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, *args], check=True, env=ENV, capture_output=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, rel, text="2\n"):
        self.write(rel, text)
        self.git("add", rel)
        self.git("commit", "-qm", rel)

    def hook(self, cmd=PR, cwd=None):
        payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd or self.root)})
        r = subprocess.run([HOOK], input=payload, capture_output=True, text=True)
        return r.returncode, r.stderr

    def test_other_commands_pass(self):
        self.commit("init/apply.py")
        self.assertEqual(self.hook("git commit -m x")[0], 0)
        self.assertEqual(self.hook("gh pr view")[0], 0)
        self.assertEqual(self.hook("git push -u origin b")[0], 0)

    def test_unnamed_file_passes(self):
        self.commit("other.txt")
        self.assertEqual(self.hook()[0], 0)

    def test_named_file_refused(self):
        self.commit("init/apply.py")
        rc, err = self.hook()
        self.assertEqual(rc, 2)
        self.assertIn("init/apply.py", err)
        self.assertIn("README_SYNC=checked", err)

    def test_whole_branch_counts(self):
        self.commit("init/apply.py")
        self.commit("other.txt")
        self.assertEqual(self.hook()[0], 2)

    def test_named_by_suffix_refused(self):
        self.git("switch", "-q", "main")
        self.commit("README.md", README.replace("plugins/x/hooks/hooks.json", "hooks/hooks.json"))
        self.git("switch", "-q", "b")
        self.git("rebase", "-q", "main")
        self.commit("plugins/x/hooks/hooks.json")
        self.assertEqual(self.hook()[0], 2)

    def test_readme_in_branch_passes(self):
        self.commit("init/apply.py")
        self.commit("README.md", README + "more\n")
        self.assertEqual(self.hook()[0], 0)

    def test_checked_passes(self):
        self.commit("init/apply.py")
        self.assertEqual(self.hook("README_SYNC=checked " + PR)[0], 0)

    def test_base_other_than_default_passes(self):
        self.git("branch", "dev", "main")
        self.commit("init/apply.py")
        self.assertEqual(self.hook("gh pr create --base dev --fill")[0], 0)
        self.assertEqual(self.hook("gh pr create -B dev --fill")[0], 0)
        self.assertEqual(self.hook("gh pr create --base=main --fill")[0], 2)

    def test_directory_add_and_delete_refused_modify_passes(self):
        self.commit("skills/a/SKILL.md")
        self.assertEqual(self.hook()[0], 0)
        self.commit("skills/b/SKILL.md")
        self.assertEqual(self.hook()[0], 2)

    def test_directory_delete_refused(self):
        self.git("rm", "-q", "skills/a/SKILL.md")
        self.git("commit", "-qm", "rm")
        self.assertEqual(self.hook()[0], 2)

    def test_subdirectory_cwd(self):
        self.commit("init/apply.py")
        self.assertEqual(self.hook(cwd=self.root / "init")[0], 2)

    def test_no_readme_passes(self):
        self.git("rm", "-q", "README.md")
        self.git("commit", "-qm", "no readme")
        self.commit("init/apply.py")
        self.assertEqual(self.hook()[0], 0)

    def test_outside_a_repo_and_bad_input_pass(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.hook(cwd=d)[0], 0)
        r = subprocess.run([HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
