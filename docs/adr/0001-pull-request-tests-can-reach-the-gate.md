# A pull request's tests can reach the gate that judges them

`scripts/gate` runs a pull request's tests and then gate.py as the same user in the same `.venv`. It checks gate.py's
hash on a fresh copy after the tests and runs it with `python -I` (since 2026-11-04), but the tests can still rewrite
the `.venv`'s tools and `.pth` files, `uv` and its config and cache, `~/.gitconfig`, the checkout's `.git/config` and
`.git/info/attributes`, `scripts/gate` itself, or leave a process running, and so change the verdict on their own pull
request (hyprmuse's review 02, F3). Running the tests in a container or as a different user was rejected (2026-11-11):
agents' pull requests are trusted that far, and the gate guards against mistakes, not against a hostile author.
