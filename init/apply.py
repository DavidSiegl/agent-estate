#!/usr/bin/env python3
"""Apply the parts of the agent setup that are not template files, to the repo in the cwd.

    apply.py --repo OWNER/NAME --tracker scratch|github --ticket-sync true|false
             --review-gate true|false --gate python|own|none --python-package NAME|''
             --automerge true|false

copier.yml runs this after `copier copy` and `copier update`, with the answers, in the
destination repo. Outside a git work tree it does nothing and exits 0: `copier update`
also runs it in the scratch renders of the old and new template versions it diffs, which
are not repos. So run copier in a repo that already exists. It is idempotent: each step
brings one thing to the state the answers ask for and leaves it alone when it is already
there. The steps:

- .gitignore gets `CLAUDE.local.md` (Claude Code's personal, uncommitted instructions),
  `.scratch/` (scratch tracker or review gate) and what scripts/gate writes: quality.md
  with any gate, and octoflow-ai's test and coverage files with the python one. Lines are
  only ever added.
- CLAUDE.md gets an `@docs/agents/README.md` import line, so its own text stays the
  repo's; a missing CLAUDE.md is created holding only that line.
- `git config agent.ticketSync` is set to OWNER/NAME when ticket sync is on, unset when
  off. Setting it publishes every open .scratch/ ticket on the next sync (ticket-sync).
- `.scratch/reviews/` at the repo root is created when the review gate is on. It is
  never removed: it holds review records; turning the gate off is reported instead.
- With a Python package: pyproject.toml gets the gate's rules (init/pyproject-tools.toml,
  aimed at the package's directory, NAME/ or src/NAME/, which must exist) unless it
  already has a [tool.ruff.lint] table, which is reported and left alone, and `uv add
  --dev` adds the tools the gate runs.
- With the GitHub tracker: the five triage labels are created on OWNER/NAME if missing.
  (With ticket sync, ticket-sync creates them itself.) With auto-merge, so is the
  no-automerge label that holds a pull request.

The main branch's ruleset is not set here: it needs admin rights, and must wait until CI
reports, or nothing can merge. init/github-rules.py does it.

Prints one line per change. Exits 1, naming the step, when a command or file operation
fails; steps after it do not run, and rerunning finishes them.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

GATE_DEV_TOOLS = ["mutmut", "mypy", "pymarkdownlnt", "pytest", "pytest-cov", "pytest-randomly", "ruff"]
# What each kind of scripts/gate writes at the repo root (the --gate answer); `own` is the
# report the starter gate's header invites.
GATE_OUTPUTS = {
    "python": [".coverage", "coverage.xml", "test-results.xml", "quality.md"],
    "own": ["quality.md"],
    "none": [],
}
CLAUDE_IMPORT = "@docs/agents/README.md"

# Label, colour and description of the label that keeps auto-merge off a pull request.
HOLD_LABEL = ("no-automerge", "b60205", "Auto-merge leaves this pull request for a human")

# Label, colour and description of each triage role (scratch-issue-tracker's vocabulary).
TRIAGE_LABELS = [
    ("needs-triage", "fbca04", "Maintainer needs to evaluate this issue"),
    ("needs-info", "d876e3", "Waiting on reporter for more information"),
    ("ready-for-agent", "0e8a16", "Fully specified, ready for an AFK agent"),
    ("ready-for-human", "1d76db", "Requires human implementation"),
    ("wontfix", "ffffff", "Will not be actioned"),
]


class StepFailed(Exception):
    """A step could not complete; the message says which and why."""


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run cmd in the cwd, capturing output; raise StepFailed on a non-zero exit when check."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise StepFailed(f"{cmd[0]}: {e}") from e
    if check and done.returncode != 0:
        raise StepFailed(f"{' '.join(cmd)}: {done.stderr.strip() or done.stdout.strip()}")
    return done


def ensure_lines(path: Path, comment: str, lines: list[str]) -> None:
    """Append the lines of `lines` that path lacks, under `# comment`; create path if missing."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if line not in present]
    if not missing:
        return
    sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    path.write_text(text + sep + f"# {comment}\n" + "".join(f"{line}\n" for line in missing), encoding="utf-8")
    print(f"{path.name}: added {', '.join(missing)}")


def ensure_claude_import(root: Path) -> None:
    """Make CLAUDE.md import docs/agents/README.md."""
    path = root / "CLAUDE.md"
    if not path.exists():
        path.write_text(f"# {root.name}\n\n{CLAUDE_IMPORT}\n", encoding="utf-8")
        print("CLAUDE.md: created, importing docs/agents/README.md")
        return
    text = path.read_text(encoding="utf-8")
    if CLAUDE_IMPORT in (line.strip() for line in text.splitlines()):
        return
    path.write_text(text.rstrip("\n") + f"\n\n{CLAUDE_IMPORT}\n", encoding="utf-8")
    print("CLAUDE.md: added the import of docs/agents/README.md")


def ensure_ticket_sync(repo: str | None) -> None:
    """Set agent.ticketSync to repo, or unset it when repo is None."""
    current = run("git", "config", "--get", "agent.ticketSync", check=False).stdout.strip() or None
    if current == repo:
        return
    if repo is None:
        run("git", "config", "--unset", "agent.ticketSync")
        print(f"git config agent.ticketSync: unset (was {current})")
    else:
        run("git", "config", "agent.ticketSync", repo)
        print(f"git config agent.ticketSync: {repo}; the next sync publishes every open ticket there")


def ensure_review_gate(root: Path, on: bool) -> None:
    """Create .scratch/reviews/ when on; when off, only report one that exists."""
    reviews = root / ".scratch" / "reviews"
    if on and not reviews.is_dir():
        reviews.mkdir(parents=True)
        print(".scratch/reviews/: created; Claude's pushes now need a passing cross-review")
    elif not on and reviews.is_dir():
        print(".scratch/reviews/ exists, so the review gate stays on; remove it by hand to turn it off")


def ensure_python_gate(root: Path, package: str) -> None:
    """Give pyproject.toml the gate's rules, unless it has ruff rules of its own, and add the gate's tools."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise StepFailed("python gate: no pyproject.toml at the repo root")
    text = pyproject.read_text(encoding="utf-8")
    if "[tool.ruff.lint]" in text:
        if "# The rules scripts/gate judges a change by." not in text:
            print("pyproject.toml: has its own [tool.ruff.lint]; the gate's rules were not added")
    else:
        dirs = [d for d in (Path(package), Path("src") / package) if (root / d).is_dir()]
        if not dirs:
            raise StepFailed(f"python gate: neither {package}/ nor src/{package}/ exists")
        rules = (HERE / "pyproject-tools.toml").read_text(encoding="utf-8")
        rules = rules.replace("{package_dir}", dirs[0].as_posix())
        pyproject.write_text(text.rstrip("\n") + "\n\n" + rules, encoding="utf-8")
        print("pyproject.toml: added the gate's rules")
    run("uv", "add", "--dev", "--quiet", *GATE_DEV_TOOLS)


def ensure_labels(repo: str, labels: list[tuple[str, str, str]]) -> None:
    """Create on repo each (name, colour, description) in labels that it lacks."""
    names = set(run("gh", "label", "list", "--repo", repo, "--limit", "500", "--json", "name",
                    "--jq", ".[].name").stdout.split("\n"))
    for name, colour, description in labels:
        if name not in names:
            run("gh", "label", "create", name, "--repo", repo, "--color", colour, "--description", description)
            print(f"{repo}: created label {name}")


def main() -> int:
    """Parse the answers and run each step; return the exit status."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", required=True)
    p.add_argument("--tracker", choices=["scratch", "github"], required=True)
    p.add_argument("--ticket-sync", choices=["true", "false", "True", "False"], required=True)
    p.add_argument("--review-gate", choices=["true", "false", "True", "False"], required=True)
    p.add_argument("--gate", choices=list(GATE_OUTPUTS), default="none")
    p.add_argument("--python-package", default="")
    p.add_argument("--automerge", choices=["true", "false", "True", "False"], default="false")
    a = p.parse_args()
    ticket_sync = a.tracker == "scratch" and a.ticket_sync.lower() == "true"
    review_gate = a.review_gate.lower() == "true"

    top = run("git", "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        return 0  # one of copier update's scratch renders; see the module docstring
    root = Path(top.stdout.strip())
    try:
        ensure_lines(root / ".gitignore", "Claude Code's personal instructions for this repo", ["CLAUDE.local.md"])
        ignores = [".scratch/"] if a.tracker == "scratch" or review_gate else []
        if ignores:
            ensure_lines(root / ".gitignore", "The tracker's specs, tickets and review records", ignores)
        if GATE_OUTPUTS[a.gate]:
            ensure_lines(root / ".gitignore", "What scripts/gate writes", GATE_OUTPUTS[a.gate])
        ensure_claude_import(root)
        ensure_ticket_sync(a.repo if ticket_sync else None)
        ensure_review_gate(root, review_gate)
        if a.python_package:
            ensure_python_gate(root, a.python_package)
        labels = TRIAGE_LABELS if a.tracker == "github" else []
        if a.automerge.lower() == "true":
            labels = [*labels, HOLD_LABEL]
        if labels:
            ensure_labels(a.repo, labels)
    except (StepFailed, OSError) as e:
        print(f"apply.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
