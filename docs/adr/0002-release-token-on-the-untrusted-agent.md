# Jenkins releases from the agent that builds agents' pull requests

The Release stage binds `jenkins_release_credential` on the `untrusted` agent that builds agents' pull requests,
where a pull request's Jenkinsfile, a planted `gh`, or a process left by `scripts/package` can reach it (review 01,
F1, F16). Releasing from a job on a trusted agent that builds `main` only was rejected (2026-11-11): the README
requires the token to be one the agents already hold, so reaching it gains them nothing, and a second job would be
upkeep in every Jenkins repo. GitHub Actions' `release` job already runs on `main` only, on a fresh runner, with the
workflow's own token.
