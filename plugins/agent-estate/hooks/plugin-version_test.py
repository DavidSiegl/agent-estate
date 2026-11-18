#!/usr/bin/env python3
"""Tests for plugin-version.py: run `python3 plugin-version_test.py`. Each test
feeds the hook a `gh pr create` from branch `b` of a scratch repo with no
remote, so the base is the local `main`. Its plugin `plugins/p` is at 1.9.0."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().with_name("plugin-version.py")
MANIFEST = "plugins/p/.claude-plugin/plugin.json"
ENV = {**os.environ, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name",
       "GIT_CONFIG_VALUE_0": "t", "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "t@t"}
PR = "gh pr create --fill"


def manifest(version=None):
    return json.dumps({"name": "p"} | ({"version": version} if version else {}))


class Scratch(unittest.TestCase):
    """The scratch repo of the module docstring, on branch b."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.write(MANIFEST, manifest("1.9.0"))
        for f in ("plugins/p/skills/a/SKILL.md", "README.md"):
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


class PluginVersion(Scratch):
    def hook(self, cmd=PR):
        payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(self.root)})
        r = subprocess.run([HOOK], input=payload, capture_output=True, text=True)
        return r.returncode, r.stderr

    def test_plugin_change_without_raise_refused(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        rc, err = self.hook()
        self.assertEqual(rc, 2)
        self.assertIn("plugins/p/", err)
        self.assertIn("1.9.0", err)

    def test_added_file_counts(self):
        self.commit("plugins/p/skills/new/SKILL.md")
        self.assertEqual(self.hook()[0], 2)

    def test_raise_passes_numerically(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        self.commit(MANIFEST, manifest("1.10.0"))
        self.assertEqual(self.hook()[0], 0)

    def test_lower_version_refused(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        self.commit(MANIFEST, manifest("1.8.9"))
        self.assertEqual(self.hook()[0], 2)

    def test_change_outside_plugin_passes(self):
        self.commit("README.md")
        self.assertEqual(self.hook()[0], 0)

    def test_other_commands_pass(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        self.assertEqual(self.hook("git push -u origin b")[0], 0)
        self.assertEqual(self.hook("gh pr create --base other")[0], 0)

    def test_no_version_passes(self):
        self.git("switch", "-q", "main")
        self.commit(MANIFEST, manifest())
        self.git("switch", "-q", "b")
        self.git("rebase", "-q", "main")
        self.commit("plugins/p/skills/a/SKILL.md")
        self.assertEqual(self.hook()[0], 0)

    def test_new_plugin_passes(self):
        self.commit("plugins/q/.claude-plugin/plugin.json", manifest("0.1.0"))
        self.assertEqual(self.hook()[0], 0)

    def test_plugin_at_repo_root(self):
        self.git("switch", "-q", "main")
        self.commit(".claude-plugin/plugin.json", manifest("2.0.0"))
        self.git("switch", "-q", "b")
        self.git("rebase", "-q", "main")
        self.commit("README.md")
        rc, err = self.hook()
        self.assertEqual(rc, 2)
        self.assertIn("./", err)

    def test_bad_input_passes(self):
        r = subprocess.run([HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


class Ci(Scratch):
    """plugin-version.py BASE HEAD, as CI runs it on a pull request: from the
    default branch's checkout, judging branch b against main."""

    def check(self):
        self.git("switch", "-q", "main")
        r = subprocess.run([HOOK, "main", "b"], cwd=self.root, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True)
        return r.returncode, r.stderr

    def test_ci_fails_a_change_without_raise_naming_it(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        rc, err = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("plugins/p/", err)
        self.assertIn("still says 1.9.0", err)

    def test_ci_passes_a_raise(self):
        self.commit("plugins/p/skills/a/SKILL.md")
        self.commit(MANIFEST, manifest("1.10.0"))
        self.assertEqual(self.check(), (0, ""))

    def test_ci_passes_a_change_outside_plugins(self):
        self.commit("README.md")
        self.assertEqual(self.check(), (0, ""))

    def test_ci_fails_closed_on_an_unknown_revision(self):
        r = subprocess.run([HOOK, "main", "nosuch"], cwd=self.root, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("nosuch", r.stderr)

    def test_ci_fails_closed_on_a_manifest_that_is_not_a_json_object(self):
        for text in ("{", "[]"):
            with self.subTest(text):
                self.commit(MANIFEST, text)
                self.commit("plugins/p/skills/a/SKILL.md", text)
                rc, err = self.check()
                self.assertEqual(rc, 2)
                self.assertIn(MANIFEST, err)
                self.git("switch", "-q", "b")


if __name__ == "__main__":
    unittest.main()
