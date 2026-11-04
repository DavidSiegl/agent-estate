#!/usr/bin/env python3
"""Two-way sync between a repo's `.scratch/` tickets and its GitHub issues.

    ticket-sync.py hook          Claude Code hook; see "Hooks" below.
    ticket-sync.py [DIR]         Syncs every ticket of the repo containing DIR
                                 (default: the current directory), printing one
                                 line per ticket that changed. Exits 1 if any
                                 ticket conflicted or failed.
    ticket-sync.py push FILE     Resolves a conflict on ticket FILE: the file
                                 wins and overwrites the issue.
    ticket-sync.py pull FILE     Resolves a conflict on ticket FILE: the issue
                                 wins and overwrites the file.

A repo opts in with `git config agent.ticketSync <owner/name>`, naming the GitHub
repo its issues live in. Without it nothing is synced: syncing publishes
`.scratch/`, which is otherwise private. Every checkout that syncs a repo must
use the same gh user: the sync only ever works on that user's issues.

Tickets are `.scratch/<feature>/issues/<NN>-<slug>.md` (see the
scratch-issue-tracker skill); spec.md, map.md and reviews/ are never synced. A
ticket's ID is `<feature>/<NN>`.

What a ticket is on GitHub:
  title   "[<feature>/<NN>] " + the file's first `# ` line outside code fences
  body    the rest of the file, ending in a marker comment
          `<!-- scratch-ticket: <feature>/<NN>-<slug> base=<hash> comments-to=<time> -->`:
          which ticket file the issue is, a hash of the ticket as last synced
          by any checkout, and the creation time of the newest GitHub comment
          already pulled. A file whose slug differs from its issue's is an
          error, not a sync: the same number was taken on two machines, or the
          file was renamed.
  label   the `Status:` value when it is one of TRIAGE; other triage labels are
          removed, other labels are left alone. Missing labels are created.
  state   closed as completed for `resolved` and `done`, as not planned for
          `wontfix`, open for anything else. A ticket that is already closed
          when it would first be published gets no issue.

Read back, an issue gives the ticket: its title and body, with `Status:` taken
from the issue where the two disagree (see issue_status).

Each checkout also records, per ticket, the hash of the text it last synced and
the issue number, in `.scratch/.ticket-sync-state.json`. A sync compares the
file and the issue with that record: when only one side changed since, it
overwrites the other; when both did, the ticket is a conflict and nothing is
touched until `push` or `pull` says which side wins. With no record (a ticket
another checkout published, or lost state), the issue wins only if the file is
exactly the text last synced anywhere, the marker's hash; any other difference
is a conflict, so a stale copy on a second machine never overwrites newer work.
New comments on the issue are then appended to the file under `## Comments`, so
they also show up in the issue body after the push.

Agents act on tickets, so the sync works only on issues the gh user opened,
whose bodies only that user and the repo's collaborators can edit:
  - Issues opened by anyone else are ignored: not imported, not synced. Their
    authors could rewrite them at any time. (See TODO.md for a safe import.)
  - An open issue the gh user opened on GitHub without a marker becomes a
    ticket under `.scratch/github/issues/` numbered with its issue number, at
    the Status its labels or body give, `needs-triage` if neither does. An
    import never overwrites a file, and reports one in its way instead.
  - Only comments by the repo's owner, members and collaborators are pulled,
    since anyone may comment on a public repo's issue.
Only the last marker in a body counts, so a ticket may quote one.
An open issue with a marker whose ticket file is missing gets the file back;
a closed one does not, so a resolved ticket may be deleted locally.

Hooks (`hook` reads the event from stdin and always exits 0; a conflict, a
failure, or a file rewritten under Claude reaches Claude as additionalContext):
  SessionStart        syncs every ticket of the session's repo
  PreToolUse(Read)    syncs a ticket before Claude reads it, so it is current
  PostToolUse(Write|Edit)
                      syncs a ticket Claude just wrote
A single-ticket hook fetches only its own issue when the record names it, and
gives up after LOCK_WAIT seconds when another sync holds the repo.
"""
import difflib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TRIAGE = ("needs-triage", "needs-info", "ready-for-agent", "ready-for-human")
# Status -> the reason a ticket with that status is closed for; any other
# status keeps the issue open.
CLOSING = {"resolved": "completed", "done": "completed", "wontfix": "not planned"}
# stateReason values gh reports for each closing reason.
STATE_REASONS = {"completed": {"COMPLETED", ""}, "not planned": {"NOT_PLANNED", "DUPLICATE"}}
# Comment authors whose comments are pulled into tickets.
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
# The feature directory issues opened on GitHub are imported into.
IMPORT_FEATURE = "github"
# Seconds a single-ticket hook waits for another sync's lock on the repo.
LOCK_WAIT = 20
ISSUE_FIELDS = "number,title,body,state,stateReason,labels,author,comments"

MARKER = re.compile(r"<!-- scratch-ticket: ((?!\.)[A-Za-z0-9._-]+/[0-9]+)(?:-([A-Za-z0-9._-]+))?"
                    r"(?: base=(\S+))?(?: comments-to=(\S+))? -->")
TICKET_PATH = re.compile(r"\.scratch/((?!\.)[A-Za-z0-9._-]+)/issues/([0-9]+)-([^/]*)\.md")
SLUG = re.compile(r"[A-Za-z0-9._-]+")
STATUS_LINE = re.compile(r"^Status:[ \t]*(\S*).*$", re.M)

GH_ENV = {**os.environ, "GH_NO_UPDATE_NOTIFIER": "1", "GH_PROMPT_DISABLED": "1"}


class SyncError(Exception):
    """A sync step failed; the message says what was attempted and why."""


# --- Ticket text ---------------------------------------------------------------
#
# A ticket's text is its canonical form, "# <title>\n\n<rest>\n", with CRs and
# surrounding blank lines removed: the form both sides are compared and hashed
# in, so that formatting GitHub or an editor adds is not a change.

def last_marker(body: str | None) -> re.Match | None:
    """Returns the issue body's own marker: the last one, since a ticket may
    quote others and the sync always appends its own at the end."""
    found = list(MARKER.finditer(body or ""))
    return found[-1] if found else None


def without_marker(body: str | None) -> str:
    """Returns the issue body with its own marker cut out."""
    body = body or ""
    m = last_marker(body)
    return body[:m.start()] + body[m.end():] if m else body


def canonical(title: str, rest: str) -> str:
    rest = rest.replace("\r", "").strip("\n").rstrip()
    return f"# {title.strip()}\n\n{rest}\n" if rest else f"# {title.strip()}\n"


def split(text: str) -> tuple[str, str]:
    """Returns the title and the rest of canonical ticket text."""
    head, _, rest = text.partition("\n")
    return head[2:], rest.strip("\n")


def file_text(raw: str, fallback_title: str) -> str:
    """Returns the ticket text of a file: its first `# ` line outside a code
    fence is the title, fallback_title if it has none."""
    lines = raw.replace("\r", "").split("\n")
    fence = ""  # the open fence's run of ` or ~; "" outside a fence
    for i, line in enumerate(lines):
        # https://spec.commonmark.org/0.31.2/#fenced-code-blocks: at most 3
        # spaces of indent; only a bare run of the same kind, at least as
        # long, closes a fence.
        run = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if run and run[1][0] == "`" and "`" in run[2]:
            run = None  # a backtick in a backtick fence's info string: not a fence
        if run and not fence:
            fence = run[1]
        elif run and run[1][0] == fence[0] and len(run[1]) >= len(fence) and not run[2].strip():
            fence = ""
        elif not fence and line.startswith("# "):
            return canonical(line[2:], "\n".join(lines[:i] + lines[i + 1:]))
    return canonical(fallback_title, raw)


def status_of(text: str) -> str:
    """Returns the first `Status:` value in ticket text or its rest, "" when
    there is none."""
    m = STATUS_LINE.search(text)
    return m[1] if m else ""


def with_status(rest: str, status: str) -> str:
    """Returns rest with its first `Status:` value set to status, adding the
    line at the top when there is none. An empty status leaves rest as it is."""
    if not status or status_of(rest) == status:
        return rest
    if STATUS_LINE.search(rest):
        return STATUS_LINE.sub(f"Status: {status}", rest, count=1)
    return f"Status: {status}\n\n{rest}"


def restatus(text: str, status: str) -> str:
    """Returns ticket text with its Status set as with_status does."""
    title, rest = split(text)
    return canonical(title, with_status(rest, status))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def slugify(title: str) -> str:
    """Returns a file-name slug for a title: lowercase words joined by -."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50].strip("-") or "ticket"


def issue_status(issue: dict, said: str) -> str:
    """Returns the Status a ticket has on GitHub, given the Status its body
    says. The issue's closed state, then a triage label other than said, win
    over said. A closed issue keeps said when it is a closing word for the
    reason it was closed for. An open issue whose body says it is closed is
    `needs-triage`."""
    if issue["state"] == "CLOSED":
        reason = "not planned" if issue.get("stateReason") in STATE_REASONS["not planned"] else "completed"
        if CLOSING.get(said) == reason:
            return said
        return "wontfix" if reason == "not planned" else "resolved"
    labels = [t for t in TRIAGE if t in {l["name"] for l in issue["labels"]}]
    added = [t for t in labels if t != said]
    if added:
        return added[0]
    if said in CLOSING:
        return "needs-triage"
    return said


def issue_text(issue: dict, title: str) -> str:
    """Returns the ticket text an issue stands for, titled title: its body
    without the marker, with Status as issue_status gives it."""
    rest = without_marker(issue["body"]).replace("\r", "").strip()
    return canonical(title, with_status(rest, issue_status(issue, status_of(rest))))


def with_comments(text: str, comments: list[dict]) -> str:
    """Returns text with comments appended under its `## Comments` heading."""
    if not comments:
        return text
    title, rest = split(text)
    if not re.search(r"^## Comments\s*$", rest, re.M):
        rest += "\n\n## Comments"
    for c in comments:
        rest += (f"\n\n**@{c['author']['login']} on GitHub, {c['createdAt'][:10]}:**"
                 f"\n\n{c['body'].strip()}")
    return canonical(title, rest)


def import_id(n: int) -> str:
    """Returns the ID of the ticket imported from issue n."""
    return f"{IMPORT_FEATURE}/{n:02d}"


# --- GitHub --------------------------------------------------------------------

class GitHub:
    """The issues and labels of one GitHub repo, through the gh CLI."""

    def __init__(self, repo: str):
        self.repo = repo
        # Label names in the repo; None until first needed.
        self._labels: set[str] | None = None
        # The authenticated user's login; None until first needed.
        self._me: str | None = None

    def _gh(self, what: str, *args: str, stdin: str | None = None) -> str:
        try:
            repo_flag = [] if args[0] == "api" else ["-R", self.repo]
            p = subprocess.run(["gh", *args, *repo_flag], input=stdin, env=GH_ENV,
                               capture_output=True, text=True)
        except OSError as e:
            raise SyncError(f"{what}: {e}") from e
        if p.returncode:
            raise SyncError(f"{what}: {p.stderr.strip() or f'gh exited {p.returncode}'}")
        return p.stdout

    def _json(self, what: str, *args: str):
        out = self._gh(what, *args)
        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise SyncError(f"{what}: gh printed no JSON: {e}") from e

    def me(self) -> str:
        """Returns the login gh is authenticated as."""
        if self._me is None:
            self._me = self._gh("finding the gh user", "api", "user", "--jq", ".login").strip()
        return self._me

    def mine(self, issue: dict) -> bool:
        """Says whether the gh user opened issue."""
        return (issue.get("author") or {}).get("login") == self.me()

    def issues(self) -> list[dict]:
        """Returns every issue, open and closed, with its comments."""
        return self._json(f"listing the issues of {self.repo}", "issue", "list", "--state", "all",
                          "--limit", "100000", "--json", ISSUE_FIELDS)

    def issue(self, n: int) -> dict:
        """Returns issue n with its comments."""
        return self._json(f"reading issue #{n}", "issue", "view", str(n), "--json", ISSUE_FIELDS)

    def _ensure_label(self, name: str) -> None:
        if self._labels is None:
            out = self._gh(f"listing the labels of {self.repo}", "label", "list",
                           "--limit", "1000", "--json", "name", "--jq", ".[].name")
            self._labels = set(out.split("\n"))
        if name not in self._labels:
            self._gh(f"creating label {name}", "label", "create", name,
                     "--description", f"scratch-issue-tracker Status: {name}")
            self._labels.add(name)

    def create(self, title: str, body: str, label: str | None) -> int:
        """Opens an issue and returns its number."""
        args = ["--label", label] if label else []
        if label:
            self._ensure_label(label)
        url = self._gh(f"creating issue {title!r}", "issue", "create", "--title", title,
                       "--body-file", "-", *args, stdin=body)
        try:
            return int(url.strip().rsplit("/", 1)[1])
        except (IndexError, ValueError) as e:
            raise SyncError(f"creating issue {title!r}: gh printed {url!r}, not an issue URL") from e

    def edit(self, n: int, *, title: str | None, body: str | None, add: str | None,
             remove: list[str]) -> None:
        """Changes what is not None or empty; does nothing when all are."""
        args = []
        if title is not None:
            args += ["--title", title]
        if body is not None:
            args += ["--body-file", "-"]
        if add:
            self._ensure_label(add)
            args += ["--add-label", add]
        if remove:
            args += ["--remove-label", ",".join(remove)]
        if args:
            self._gh(f"updating issue #{n}", "issue", "edit", str(n), *args, stdin=body)

    def close(self, n: int, reason: str) -> None:
        self._gh(f"closing issue #{n}", "issue", "close", str(n), "--reason", reason)

    def reopen(self, n: int) -> None:
        self._gh(f"reopening issue #{n}", "issue", "reopen", str(n))


# --- Sync ----------------------------------------------------------------------

class Repo:
    """An opted-in repo's tickets and the GitHub issues they sync with. Holds a
    lock on the repo's tickets from construction to close(), so that two syncs
    never run on one checkout at once. sync_one() syncs a single ticket;
    load_all() then sync_all() syncs them all."""

    def __init__(self, root: Path, repo: str, wait: float | None = None):
        """Locks the repo, waiting at most wait seconds (None: as long as it
        takes). Raises SyncError when the lock is not had in time, or when
        `.scratch` is a symlink: writing through it would land in another
        checkout's tickets."""
        self.root = root
        self.scratch = root / ".scratch"
        self.gh = GitHub(repo)
        if self.scratch.is_symlink():
            raise SyncError(f"{self.scratch} is a symlink; ticket-sync syncs only a real directory")
        try:
            self.scratch.mkdir(exist_ok=True)
            self._lock = open(self.scratch / ".ticket-sync.lock", "w")
            deadline = None if wait is None else time.monotonic() + wait
            while True:
                try:
                    fcntl.flock(self._lock, fcntl.LOCK_EX | (0 if deadline is None else fcntl.LOCK_NB))
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        self._lock.close()
                        raise SyncError("another sync of this repo is running; not synced now")
                    time.sleep(0.2)
        except OSError as e:
            raise SyncError(f"locking {self.scratch}: {e}") from e
        # Ticket ID -> {"hash": hash of the text this checkout last synced it
        # at, "issue": its issue number}. A missing ID means this checkout has
        # never synced that ticket; a missing "issue", a record from before it
        # was kept. Saved after every ticket.
        self._state_path = self.scratch / ".ticket-sync-state.json"
        try:
            raw = json.loads(self._state_path.read_text())
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError) as e:
            self._lock.close()
            raise SyncError(f"reading {self._state_path}: {e}") from e
        # Records written before the issue number was kept are bare hashes.
        self.synced: dict[str, dict] = {
            tid: v if isinstance(v, dict) else {"hash": v} for tid, v in raw.items()}
        # Ticket ID -> the lowest-numbered of the gh user's issues whose marker
        # names it.
        self.issues: dict[str, dict] = {}
        # Open issues of the gh user's with no marker, to be imported.
        self.unmarked: list[dict] = []

    def close(self) -> None:
        self._lock.close()

    def _ticket_of(self, issue: dict) -> str | None:
        """Returns the ID of the ticket issue syncs with, None if it is none:
        an issue of someone else's, or one without a marker."""
        m = last_marker(issue["body"]) if self.gh.mine(issue) else None
        return m[1] if m else None

    def _import_file(self, tid: str) -> Path | None:
        """Returns the file of imported ticket tid, None if there is none."""
        return next((self.scratch / IMPORT_FEATURE / "issues").glob(f"{tid.split('/')[1]}-*.md"),
                    None)

    def _add(self, issue: dict) -> None:
        tid = self._ticket_of(issue)
        if tid is not None:
            if tid not in self.issues or issue["number"] < self.issues[tid]["number"]:
                self.issues[tid] = issue
        elif (issue["state"] == "OPEN" and self.gh.mine(issue)
              and "<!-- scratch-ticket:" not in (issue["body"] or "")):
            self.unmarked.append(issue)

    def load_all(self) -> None:
        """Reads every issue of the repo."""
        for issue in self.gh.issues():
            self._add(issue)

    def sync_one(self, tid: str, path: Path, winner: str | None = None) -> str:
        """Syncs ticket tid, whose file is path, as sync does, reading only
        its own issue when this checkout's record names it and that issue
        still is tid's, else every issue. A closed ticket this checkout never
        synced costs no gh call: at most it is published from elsewhere, and
        a full sync picks that up."""
        record = self.synced.get(tid, {})
        if not record and winner is None and status_of(read_or_none(path) or "") in CLOSING:
            return ""
        if (n := record.get("issue")) is not None:
            try:
                issue = self.gh.issue(n)
            except SyncError:
                issue = None  # deleted or moved: look for it among all issues
            if issue is not None and self._ticket_of(issue) == tid:
                self.issues[tid] = issue
                return self.sync(tid, path, winner)
        self.load_all()
        return self.sync(tid, path, winner)

    def ticket_id(self, path: Path) -> str | None:
        """Returns the ID of the ticket at path, or None if it is not one."""
        try:
            rel = path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return None
        m = TICKET_PATH.fullmatch(rel)
        return f"{m[1]}/{m[2]}" if m else None

    def files(self) -> dict[str, list[Path]]:
        """Returns every ticket file, by ID; more than one file is an error."""
        found: dict[str, list[Path]] = {}
        for path in sorted(self.root.glob(".scratch/*/issues/*.md")):
            if (tid := self.ticket_id(path)) is not None:
                found.setdefault(tid, []).append(path)
        return found

    def sync_all(self) -> tuple[list[str], list[str]]:
        """Syncs every ticket and imports unmarked open issues; load_all()
        first. Returns the report lines of tickets that changed, and the
        problems: conflicts and failures, one message each."""
        changed, problems = [], []
        files = self.files()
        for tid in sorted(files.keys() | self.issues.keys()):
            paths = files.get(tid, [])
            try:
                if len(paths) > 1:
                    raise SyncError(f"{tid}: several files: {', '.join(map(str, paths))}")
                if not paths and self.issues[tid]["state"] == "CLOSED":
                    continue
                line = self.sync(tid, paths[0] if paths else None)
            except SyncError as e:
                problems.append(str(e))
                continue
            if line:
                changed.append(line)
        for issue in self.unmarked:
            try:
                changed.append(self.import_issue(issue))
            except SyncError as e:
                problems.append(str(e))
        return changed, problems

    def sync(self, tid: str, path: Path | None, winner: str | None = None) -> str:
        """Syncs ticket tid, whose file is path (None: no file yet). winner is
        None to sync both ways, "file" or "issue" to resolve a conflict that
        way. Returns a report line, empty when nothing changed. Raises SyncError
        on a conflict (both sides changed and no winner given), touching
        neither, and when a step fails, leaving the rest for the next sync."""
        issue = self.issues.get(tid)
        ftext = None
        if path is not None:
            try:
                ftext = file_text(path.read_text(), path.stem)
            except (OSError, UnicodeDecodeError) as e:
                raise SyncError(f"{tid}: reading {path}: {e}") from e
        itext, slug, base, comments_to = None, None, None, None
        if issue is not None:
            itext = issue_text(issue, issue["title"].removeprefix(f"[{tid}] "))
            m = last_marker(issue["body"])
            slug, base, comments_to = m[2], m[3], m[4]
            if path is not None and slug and winner != "file" and slug != path.stem.split("-", 1)[1]:
                raise SyncError(
                    f"{tid}: issue #{issue['number']} is ticket {tid}-{slug}, not {path.name}: the "
                    f"number was taken twice, or the file was renamed. Renumber one ticket, or make "
                    f"this file the ticket with `ticket-sync.py push {path}`.")

        # A closed ticket is not published after the fact.
        if issue is None and status_of(ftext) in CLOSING:
            return ""

        # Pick the text both sides end with. A side is unchanged when it still
        # has the text this checkout last synced; without that record, only
        # the file can be unchanged, by matching the marker's hash.
        last = self.synced.get(tid, {}).get("hash")
        done = []
        if ftext is None:
            text, done = itext, ["pulled"]
        elif itext is None or ftext == itext:
            text = ftext
        elif winner == "file" or (winner is None and last is not None and digest(itext) == last):
            text, done = ftext, ["pushed"]
        elif winner == "issue" or (winner is None and digest(ftext) == (last or base)):
            text, done = itext, ["pulled"]
        else:
            diff = "".join(difflib.unified_diff(
                itext.splitlines(True), ftext.splitlines(True), "GitHub", str(path)))
            raise SyncError(
                f"{tid} (#{issue['number']}): conflict, the file and the issue both changed since "
                f"the last sync. Merge them into the file, then run `ticket-sync.py push {path}`; "
                f"or take GitHub's with `ticket-sync.py pull {path}`.\n{diff}")

        new = [c for c in (issue or {}).get("comments", []) if c["createdAt"] > (comments_to or "")]
        if new:
            comments_to = max(c["createdAt"] for c in new)
            trusted = [c for c in new if c.get("authorAssociation") in TRUSTED]
            text = with_comments(text, trusted)
            if trusted:
                done.append(f"{len(trusted)} comment(s) pulled")

        if path is None:
            path = self._path(tid, slug or slugify(split(text)[0]))
        n, pushed = self._push(tid, path, issue, text, comments_to)
        if text != ftext:
            self._write(path, text)
        self._record(tid, n, text)
        done += [d for d in pushed if d not in done]
        return f"#{n} {tid}: {', '.join(done)}" if done else ""

    def import_issue(self, issue: dict) -> str:
        """Makes a ticket of an unmarked issue of the gh user's and marks the
        issue. Raises SyncError, touching nothing, when a file is in the new
        ticket's place."""
        tid = import_id(issue["number"])
        if (clash := self._import_file(tid)) is not None:
            raise SyncError(f"{tid}: {clash} is in the way of importing issue #{issue['number']}, "
                            f"and no issue's marker names it. Move it out of "
                            f"{self.scratch / IMPORT_FEATURE} and sync again.")
        comments = issue.get("comments") or []
        text = issue_text(issue, issue["title"])
        if not status_of(text):
            text = restatus(text, "needs-triage")
        text = with_comments(text, [c for c in comments if c.get("authorAssociation") in TRUSTED])
        path = self._path(tid, slugify(issue["title"]))
        self._push(tid, path, issue, text, max((c["createdAt"] for c in comments), default=None))
        self._write(path, text)
        self._record(tid, issue["number"], text)
        return f"#{issue['number']} {tid}: imported"

    def _path(self, tid: str, slug: str) -> Path:
        feature, nn = tid.split("/")
        return self.scratch / feature / "issues" / f"{nn}-{slug}.md"

    def _record(self, tid: str, n: int, text: str) -> None:
        self.synced[tid] = {"hash": digest(text), "issue": n}
        self._write(self._state_path, json.dumps(self.synced, indent=1, sort_keys=True) + "\n")

    def _write(self, path: Path, text: str) -> None:
        """Replaces path with text atomically, keeping its mode. Refuses a path
        that resolves outside .scratch/, as through a symlinked directory."""
        if not path.parent.resolve().is_relative_to(self.scratch.resolve()):
            raise SyncError(f"writing {path}: it lies outside {self.scratch}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                mode = path.stat().st_mode & 0o777
            except FileNotFoundError:
                umask = os.umask(0)
                os.umask(umask)
                mode = 0o666 & ~umask
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            with os.fdopen(fd, "w") as f:
                f.write(text)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        except OSError as e:
            raise SyncError(f"writing {path}: {e}") from e

    def _push(self, tid: str, path: Path, issue: dict | None, text: str,
              comments_to: str | None) -> tuple[int, list[str]]:
        """Makes issue (None: none yet) match text, marking it as ticket file
        path synced at text. Returns the issue number and what changed beyond
        title and body."""
        title, rest = split(text)
        status = status_of(rest)
        label = status if status in TRIAGE else None
        reason = CLOSING.get(status)
        gh_title = f"[{tid}] {title}"
        slug = path.stem.split("-", 1)[1]
        key = f"{tid}-{slug}" if SLUG.fullmatch(slug) else tid
        marker = f"<!-- scratch-ticket: {key} base={digest(text)} comments-to={comments_to or '-'} -->"
        body = f"{rest}\n\n{marker}" if rest else marker
        done = []
        if issue is None:
            n, state, state_reason = self.gh.create(gh_title, body, label), "OPEN", ""
            done.append("created")
        else:
            n, state, state_reason = issue["number"], issue["state"], issue.get("stateReason") or ""
            names = {l["name"] for l in issue["labels"]}
            remove = [t for t in TRIAGE if t in names and t != label]
            add = label if label and label not in names else None
            same_body = (issue["body"] or "").replace("\r", "").strip() == body
            self.gh.edit(n, title=None if issue["title"] == gh_title else gh_title,
                         body=None if same_body else body, add=add, remove=remove)
        if state == "CLOSED" and (not reason or state_reason not in STATE_REASONS[reason]):
            self.gh.reopen(n)
            state = "OPEN"
            if not reason:
                done.append("reopened")
        if reason and state == "OPEN":
            self.gh.close(n, reason)
            done.append(f"closed ({reason})")
        return n, done


# --- Entry points --------------------------------------------------------------

def opted_in(where: Path) -> tuple[Path, str] | None:
    """Returns the toplevel of the git repo containing directory where and the
    GitHub repo it syncs with, or None when it is not a repo that opted in."""
    def git(*args):
        p = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    root = git("rev-parse", "--show-toplevel")
    repo = root and git("config", "--get", "agent.ticketSync")
    return (Path(root), repo) if repo else None


def read_or_none(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def hook() -> None:
    """Runs as the Claude Code hook for the event on stdin; see the module doc."""
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return
    name = event.get("hook_event_name", "")
    if name == "SessionStart":
        target = Path(event.get("cwd") or ".")
    else:
        file = (event.get("tool_input") or {}).get("file_path") or ""
        if "/.scratch/" not in file or "/issues/" not in file or not os.path.isfile(file):
            return
        target = Path(file)
    found = opted_in(target if target.is_dir() else target.parent)
    if not found:
        return

    notes = []
    try:
        repo = Repo(*found, wait=None if name == "SessionStart" else LOCK_WAIT)
        try:
            if name == "SessionStart":
                repo.load_all()
                changed, problems = repo.sync_all()
                if changed:
                    notes.append(f"ticket-sync synced .scratch/ tickets with GitHub {found[1]}:\n"
                                 + "\n".join(changed))
                notes += problems
            elif (tid := repo.ticket_id(target)) is not None:
                before = read_or_none(target)
                line = repo.sync_one(tid, target)
                if read_or_none(target) != before:
                    notes.append(
                        f"ticket-sync updated {target} from GitHub before this read ({line})."
                        if name == "PreToolUse" else
                        f"ticket-sync rewrote {target} from GitHub after this edit ({line}); "
                        "read it again before editing it.")
        finally:
            repo.close()
    except SyncError as e:
        notes.append(f"ticket-sync (GitHub {found[1]}): {e}")
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": name,
                                                 "additionalContext": "\n\n".join(notes)}}))


def main(argv: list[str]) -> int:
    if argv[:1] == ["hook"]:
        hook()
        return 0
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if argv[:1] in (["push"], ["pull"]) and len(argv) == 2:
        target, winner = Path(argv[1]), {"push": "file", "pull": "issue"}[argv[0]]
        where = target.parent
    elif len(argv) <= 1:
        target, winner = None, None
        where = Path(argv[0] if argv else ".")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    found = opted_in(where)
    if not found:
        print(f"ticket-sync: {where} is not in a git repo that set agent.ticketSync; "
              "opt in with: git config agent.ticketSync <owner/name>", file=sys.stderr)
        return 1
    try:
        repo = Repo(*found)
        try:
            if target is None:
                repo.load_all()
                changed, problems = repo.sync_all()
            else:
                if (tid := repo.ticket_id(target)) is None or not target.is_file():
                    raise SyncError(f"{target} is not a ticket file under .scratch/<feature>/issues/")
                changed, problems = [repo.sync_one(tid, target, winner)], []
        finally:
            repo.close()
    except SyncError as e:
        changed, problems = [], [str(e)]
    for line in filter(None, changed):
        print(line)
    for p in problems:
        print(f"ticket-sync: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
