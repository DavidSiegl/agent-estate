# TODO

## Open issues

- **Copier runs `init/apply.py` three times per update.** It also runs it in the scratch renders of the old and new
  template versions. `apply.py` returns early outside a git work tree, which is also why `copier copy` into a
  directory that isn't a git repo silently skips every step.
- **The judged code can still tamper with the judge.** `scripts/gate` runs the pull request's tests (conftest, test
  code, the dependencies in its `uv.lock`) and then gate.py, as the same user, in the same `.venv`. Since 2026-11-04
  it checks gate.py's hash on a fresh copy after the tests, in a directory created after them, and runs it with
  `python -I`; that stops a pull request from replacing the cached gate.py. Everything else that user can write is
  still open, within the run and beyond it: the `.venv`'s ruff, mypy, coverage, interpreter and `.pth` files (which
  `-I` does not stop), `uv`, `~/.gitconfig` (gate.py runs git), `~/.config/uv/uv.toml` and `~/.cache/uv`, none of
  which `cleanWs()` reaches; the checkout's `.git/config` and `.git/info/attributes` (an attribute like `*.py -diff`
  hides every changed line from gate.py); `scripts/gate` itself, which bash reads while it runs; a process the tests leave running,
  which can swap the copy of gate.py after its check; and a `conftest.py`, which auto-merge holds but whose hooks run
  in any build. A test can so change the verdict
  on its own pull request, which auto-merge then merges, or on later builds on that agent. Review 02 on hyprmuse,
  F3: "the same-process part needs the judge kept out of the judged code's reach, or a recorded decision that it is
  accepted." Closed by running the tests where they cannot write what gate.py and its tools use (a container, or a
  different user on the Jenkins agent), or by the user deciding agents' pull requests are trusted that far.
