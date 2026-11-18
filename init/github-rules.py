#!/usr/bin/env python3
"""Protect a repo's default branch with the ruleset `ci-cd`: changes arrive only through pull requests, and only
once CI's check passed.

    github-rules.py OWNER/NAME --check CONTEXT [--app-id ID]

CONTEXT is the status or check CI reports on a pull request: `continuous-integration/jenkins/pr-head` for the
template's Jenkins job, `gate` for its GitHub Actions workflow. ID is the GitHub App the check must come from, so
that a status posted with anyone else's token does not count: Jenkins's own App (davidsiegl-jenkins is 5456635),
or GitHub Actions, 15368. Without it, any source satisfies the check.

The ruleset, as octoflow-ai's: no deleting or force-pushing the default branch, a pull request for every change
(no approvals required), and CONTEXT passing on its head, which must be up to date with the default branch
(strict), so that two pull requests that passed at the same moment cannot both merge unchecked against each other;
nobody may bypass, so neither may an agent with your token.
Run it once CI reports CONTEXT on pull requests. Before then nothing can merge. Rerunning replaces the rules of
an existing `ci-cd` ruleset with these.

Needs a gh token with Administration: write on the repo. Exit status 1 with gh's error when a call fails.
"""

import argparse
import json
import subprocess
import sys

NAME = "ci-cd"


def gh_api(*args: str, body: dict | None = None) -> str:
    """gh api's stdout for args, sending body as JSON; raises RuntimeError with gh's error when it fails."""
    cmd = ["gh", "api", *args]
    if body is not None:
        cmd += ["--input", "-"]
    try:
        done = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                              capture_output=True, text=True, check=False)
    except OSError as e:
        raise RuntimeError(f"gh: {e}") from e
    if done.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args)}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout


def ruleset(check: str, app_id: int | None) -> dict:
    """The ci-cd ruleset requiring check, from app_id when it is given."""
    required = {"context": check} | ({"integration_id": app_id} if app_id is not None else {})
    return {
        "name": NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "allowed_merge_methods": ["merge", "squash", "rebase"],
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_approving_review_count": 0,
                "required_review_thread_resolution": False,
            }},
            {"type": "required_status_checks", "parameters": {
                "do_not_enforce_on_create": False,
                "required_status_checks": [required],
                "strict_required_status_checks_policy": True,
            }},
        ],
    }


def main() -> int:
    """Create or update the ruleset; return the exit status."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("repo", metavar="OWNER/NAME")
    p.add_argument("--check", required=True, metavar="CONTEXT")
    p.add_argument("--app-id", type=int, metavar="ID")
    a = p.parse_args()
    body = ruleset(a.check, a.app_id)
    try:
        existing = json.loads(gh_api(f"repos/{a.repo}/rulesets"))
        ids = [r["id"] for r in existing if r["name"] == NAME]
        if ids:
            gh_api("--method", "PUT", f"repos/{a.repo}/rulesets/{ids[0]}", body=body)
            print(f"{a.repo}: ruleset {NAME} updated")
        else:
            gh_api("--method", "POST", f"repos/{a.repo}/rulesets", body=body)
            print(f"{a.repo}: ruleset {NAME} created")
    except RuntimeError as e:
        print(f"github-rules.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
