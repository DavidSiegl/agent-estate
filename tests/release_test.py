#!/usr/bin/env python3
"""Tests for the template's scripts/release: run `python3 tests/release_test.py`.
Each test runs it, straight from template/, in a scratch repository on branch
`change`, cut from a `main` that a bare origin also holds, with pyproject.toml's
[project] version 0.9.0 there. `due` and `publish` run against a fake `gh` that records
its calls and answers from the releases a test gives it."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = next((ROOT / "template").glob("*scripts*/*release*"))
ENV = {**os.environ, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "user.name",
       "GIT_CONFIG_VALUE_0": "t", "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "t@t"}
# A gh that answers `release view [TAG]` from $RELEASES (tags, newest first, one per
# line), exits 1 with $GH_FAIL on stderr when that is set, and appends every
# `release create` call's arguments to $GH_LOG.
FAKE_GH = r"""#!/bin/sh
if [ -n "${GH_FAIL:-}" ]; then echo "$GH_FAIL" >&2; exit 1; fi
case "$1 $2" in
"release view")
    shift 2
    case "${1:-}" in
    -*|"") tag=$(printf '%s' "$RELEASES" | head -n 1) ;;
    *) tag=$(printf '%s\n' "$RELEASES" | grep -x -- "$1") ;;
    esac
    [ -n "$tag" ] || { echo "release not found" >&2; exit 1; }
    echo "$tag" ;;
"release create") shift 2; echo "$*" >> "$GH_LOG" ;;
*) echo "unexpected gh $*" >&2; exit 3 ;;
esac
"""


def pyproject(version):
    """A pyproject.toml whose [project] has ``version``, between tables whose own
    version lines must not be taken for it."""
    return (f'[tool.other]\nversion = "9.9.9"\n\n[project]\nname = "p"\n'
            f'version = "{version}"\n\n[tool.x]\nversion = "8"\n')


class Release(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("init", "-q", "-b", "main")
        self.commit({"pyproject.toml": pyproject("0.9.0"), "p/cli.py": "1"}, "base")
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.git("switch", "-qc", "change")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.gh_log = self.tmp / "gh.log"

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, *args], check=True, env=ENV, capture_output=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def commit(self, files, message="c"):
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "--all")
        self.git("commit", "-qm", message)

    def on_main(self, files):
        """Commits ``files`` on main, pushes it, and cuts ``change`` afresh from it."""
        self.git("switch", "-q", "main")
        self.commit(files)
        self.git("push", "-q", "origin", "main")
        self.git("switch", "-q", "-C", "change")

    def package(self, body):
        """Gives the repo an executable scripts/package running ``body``."""
        self.write("scripts/package", "#!/bin/sh\nset -e\n" + body).chmod(0o755)

    def run_release(self, *args, releases="", gh_fail=""):
        env = {**ENV, "PATH": f"{self.bin}:{ENV['PATH']}", "RELEASES": releases,
               "GH_FAIL": gh_fail, "GH_LOG": str(self.gh_log)}
        return subprocess.run(["sh", str(SCRIPT), *args], cwd=self.root, env=env,
                              capture_output=True, text=True, check=False)

    def created(self):
        """The arguments of each `gh release create` call, one string per call."""
        return self.gh_log.read_text().splitlines() if self.gh_log.exists() else []

    # --- raised -------------------------------------------------------------

    def test_raised_passes_a_version_greater_number_by_number(self):
        for version in ("0.9.1", "0.10.0", "1.0.0"):
            with self.subTest(version):
                self.commit({"pyproject.toml": pyproject(version), "p/cli.py": version})
                r = self.run_release("raised", "main")
                self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_raised_fails_a_kept_or_lowered_version_naming_both(self):
        for version in ("0.9.0", "0.8.9"):
            with self.subTest(version):
                self.commit({"pyproject.toml": pyproject(version), "p/cli.py": version})
                r = self.run_release("raised", "main")
                self.assertEqual(r.returncode, 1)
                self.assertIn(f"version is {version}, not greater than main's 0.9.0", r.stderr)

    def test_raised_passes_a_change_to_exempt_paths_alone(self):
        only = ["docs/agents/README.md", "README.md", "TODO.md", "CLAUDE.md", "tests/test_x.py",
                "scripts/gate", "scripts/release", "Jenkinsfile", ".github/workflows/automerge.yml",
                ".gitignore", ".copier-answers.yml", ".release-exempt"]
        self.commit(dict.fromkeys(only, "x"))
        r = self.run_release("raised", "main")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("nothing to release", r.stdout)

    def test_raised_needs_the_raise_for_any_other_path_beside_exempt_ones(self):
        for path in ("p/cli.py", "uv.lock", "scripts/package", "packaging/README.md",
                     "assets/logo.svg"):
            with self.subTest(path):
                self.commit({"docs/notes.md": path, path: path})
                r = self.run_release("raised", "main")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("version is 0.9.0, not greater than main's 0.9.0", r.stderr)

    def test_raised_takes_release_exempt_from_the_target_not_the_change(self):
        self.commit({".release-exempt": "# the logo\nassets\n", "assets/logo.svg": "x"})
        r = self.run_release("raised", "main")
        self.assertEqual(r.returncode, 1, "the change's own .release-exempt must not count")
        self.on_main({".release-exempt": "# the logo\nassets\n"})
        self.commit({"assets/logo.svg": "y", "assets/deep/x.png": "y"})
        r = self.run_release("raised", "main")
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_raised_orders_pre_releases_below_their_final_release(self):
        # (main's version, the change's, whether the change's is greater)
        cases = [("1.0.0rc1", "1.0.0", True), ("1.0.0", "1.0.0rc1", False),
                 ("1.0.0rc1", "1.0.0rc2", True), ("1.0.0b2", "1.0.0rc1", True),
                 ("1.0.0a1", "1.0.0b1", True), ("1.0.0.dev1", "1.0.0a1", True),
                 ("1.0.0-rc.1", "1.0.0", True), ("1.0.0", "1.0.0.post1", True),
                 ("1.0.0.post1", "1.0.1rc1", True), ("1.0", "1.0.0", False),
                 ("1.9.0", "1.10.0", True), ("2.0.0", "1.99.99", False)]
        for old, new, greater in cases:
            with self.subTest(old=old, new=new):
                self.on_main({"pyproject.toml": pyproject(old)})
                self.commit({"pyproject.toml": pyproject(new), "p/cli.py": new})
                r = self.run_release("raised", "main")
                self.assertEqual(r.returncode, 0 if greater else 1, r.stderr)

    def test_raised_reads_the_version_however_toml_spells_it(self):
        for line in ('version="1.0.0"', "version = '1.0.0'", 'version = "1.0.0"  # bumped',
                     'version = "1.0.0"\r', '  version = "1.0.0"', '\tversion\t=\t"1.0.0"'):
            with self.subTest(line=line):
                text = f'[project]  # the package\nname = "p"\n{line}\n[tool.x]\nversion = "0"\n'
                self.commit({"pyproject.toml": text, "p/cli.py": line})
                r = self.run_release("raised", "main")
                self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_raised_reads_a_project_header_however_toml_spells_it(self):
        for header in ("[ project ]", "  [project]", "[project]\r", "[\tproject\t]  # p"):
            with self.subTest(header=header):
                text = f'{header}\nname = "p"\nversion = "1.0.0"\n  [ tool.x ]\nversion = "0"\n'
                self.commit({"pyproject.toml": text, "p/cli.py": header})
                r = self.run_release("raised", "main")
                self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_raised_fails_with_2_on_a_pyproject_without_a_project_version(self):
        self.commit({"pyproject.toml": '[project]\nname = "p"\n'})
        r = self.run_release("raised", "main")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no version in pyproject.toml's [project] table", r.stderr)

    def test_raised_fails_with_2_on_a_target_origin_lacks(self):
        self.commit({"p/cli.py": "2"})
        r = self.run_release("raised", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot fetch nope", r.stderr)

    # --- changed ------------------------------------------------------------

    def test_changed_is_0_for_a_released_path_and_1_for_exempt_ones_alone(self):
        self.commit({"README.md": "x", "tests/t.py": "x"})
        self.assertEqual(self.run_release("changed", "main").returncode, 1)
        self.commit({"p/cli.py": "2"})
        self.assertEqual(self.run_release("changed", "main").returncode, 0)

    def test_changed_takes_release_exempt_from_head(self):
        self.commit({".release-exempt": "assets\n\n  # comment\n", "assets/a/b.svg": "x"})
        self.assertEqual(self.run_release("changed", "main").returncode, 1)

    def test_changed_fails_otherwise_on_a_bad_base(self):
        r = self.run_release("changed", "no-such-rev")
        self.assertNotIn(r.returncode, (0, 1))

    # --- publish ------------------------------------------------------------

    def test_publish_does_nothing_when_the_version_is_released(self):
        r = self.run_release("publish", releases="v0.9.0\nv0.8.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("v0.9.0 is already released", r.stdout)
        self.assertEqual(self.created(), [])

    def test_publish_fails_below_the_latest_release(self):
        r = self.run_release("publish", releases="v0.10.0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("0.9.0 is below the latest release v0.10.0", r.stderr)
        self.assertEqual(self.created(), [])

    def test_publish_creates_the_first_release_and_one_above_the_latest(self):
        for releases in ("", "v0.8.10"):
            with self.subTest(releases=releases):
                self.gh_log.unlink(missing_ok=True)
                r = self.run_release("publish", releases=releases)
                self.assertEqual(r.returncode, 0, r.stderr)
                head = subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], text=True,
                                      capture_output=True, check=True).stdout.strip()
                self.assertEqual(self.created(),
                                 [f"v0.9.0 --target {head} --title v0.9.0 --generate-notes"])

    def test_publish_attaches_every_file_in_dist_release_and_never_runs_scripts_package(self):
        self.package("touch packaged\n")
        self.write("dist/release/p-linux-x86_64", "b")
        self.write("dist/release/licenses.txt", "l")
        self.write("dist/release/.sig", "s")
        r = self.run_release("publish")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root / "packaged").exists())
        [call] = self.created()
        self.assertTrue(call.startswith("v0.9.0 dist/release/licenses.txt dist/release/p-linux-x86_64 "
                                        "dist/release/.sig --target "), call)

    def test_publish_with_scripts_package_creates_nothing_unless_dist_release_holds_only_files(self):
        trees = {(): "dist/release/ holds no file",
                 ("dist/release/a/b", "dist/release/z"): "dist/release/a is not a file",
                 ("dist/release/a#b",): "has a # in its name"}
        self.package("true\n")
        for files, message in trees.items():
            with self.subTest(files=files):
                subprocess.run(["rm", "-rf", self.root / "dist"], check=True)
                (self.root / "dist/release").mkdir(parents=True)
                for rel in files:
                    self.write(rel, "x")
                r = self.run_release("publish")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(message, r.stderr)
                self.assertEqual(self.created(), [])

    def test_publish_fails_on_any_other_gh_error_without_creating(self):
        r = self.run_release("publish", gh_fail="HTTP 401: Bad credentials")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Bad credentials", r.stderr)
        self.assertEqual(self.created(), [])

    # --- due ----------------------------------------------------------------

    def test_due_is_0_for_an_unreleased_version_and_1_for_a_released_one(self):
        for releases, status, said in (("", 0, "v0.9.0 is due"), ("v0.8.10", 0, "v0.9.0 is due"),
                                       ("v0.9.0\nv0.8.0", 1, "v0.9.0 is already released")):
            with self.subTest(releases=releases):
                r = self.run_release("due", releases=releases)
                self.assertEqual((r.returncode, r.stderr), (status, ""))
                self.assertIn(said, r.stdout)
        self.assertEqual(self.created(), [])

    def test_due_fails_with_2_below_the_latest_release_or_on_a_gh_error(self):
        for releases, gh_fail, message in (("v0.10.0", "", "below the latest release v0.10.0"),
                                           ("", "HTTP 401: Bad credentials", "Bad credentials")):
            with self.subTest(message=message):
                r = self.run_release("due", releases=releases, gh_fail=gh_fail)
                self.assertEqual(r.returncode, 2)
                self.assertIn(message, r.stderr)

    # --- usage --------------------------------------------------------------

    def test_an_unknown_or_missing_subcommand_fails_with_usage(self):
        for args in ((), ("bump",), ("changed",), ("raised",), ("due", "x"), ("publish", "x")):
            with self.subTest(args=args):
                r = self.run_release(*args)
                self.assertEqual(r.returncode, 2)
                self.assertIn("usage", r.stderr)


if __name__ == "__main__":
    unittest.main()
