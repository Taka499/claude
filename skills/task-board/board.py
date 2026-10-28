#!/usr/bin/env python3
"""Run a project's GitHub board by name: ready, file, queue, claim, release, done.

The task-board skill (SKILL.md beside this file) describes the workflow; this script is its only way to change the
board, so no session has to look up the board's internal IDs, and a wrong ID cannot set the wrong field. It reads
`.task-board.json` at the repository root, for example
    {"owner": "tia-tools", "project": 3, "repo": "tia-tools/gmks-hif-final-stats"}
and calls `gh`, which takes its token from the project's GH_CONFIG_DIR (global CLAUDE.md § Git Operations).
Standard library only; Python 3.9 or later.

Usage:
    python3 -I board.py ready [--json]
    python3 -I board.py file (--triage | --todo [--priority P1|P2|P3]) --title TITLE [--body BODY] [--blocked-by 3,7]
    python3 -I board.py queue N [--priority P1|P2|P3]          (only when the user asks: Triage is their gate)
    python3 -I board.py claim N --branch BRANCH [--worktree PATH]
    python3 -I board.py release N --branch BRANCH --reason TEXT
    python3 -I board.py done N --branch BRANCH --evidence TEXT
Exit status: 0 done, 1 bad usage or configuration, 2 gh failed or answered in an unexpected shape, 3 refused (wrong
state, or another session's claim).
Tests: python3 -m unittest discover -s skills/task-board
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = ".task-board.json"
STATUS_FIELD, PRIORITY_FIELD = "Status", "Priority"
TRIAGE, TODO, IN_PROGRESS, DONE = "Triage", "Todo", "In Progress", "Done"
STATUSES = (TRIAGE, TODO, IN_PROGRESS, DONE)
PRIORITIES = ("P1", "P2", "P3")
DEFAULT_PRIORITY = "P2"
# Markers at the start of the comments this script writes, so a later run can read the claim history back.
CLAIM, RELEASE, DONE_MARK = "task-board claim:", "task-board release:", "task-board done:"
LIMIT = "1000"  # gh's list commands default to 30 items


class BoardError(Exception):
    """Bad usage or configuration (exit 1)."""


class GhError(Exception):
    """gh exited non-zero (exit 2)."""


class Refused(Exception):
    """The issue is not in a state that allows the step, or another session holds it (exit 3)."""


@dataclass(frozen=True)
class Config:
    owner: str
    project: int
    repo: str


@dataclass(frozen=True)
class Fields:
    project_id: str
    status_id: str
    status_options: dict  # option name -> option id
    priority_id: str
    priority_options: dict


# ---- pure functions -------------------------------------------------------------------------------------------------

def parse_config(text: str) -> Config:
    try:
        data = json.loads(text)
        config = Config(owner=str(data["owner"]), project=int(data["project"]), repo=str(data["repo"]))
    except (ValueError, KeyError, TypeError) as error:
        raise BoardError(f"{CONFIG_FILE} must hold owner, project (a number) and repo: {error}") from None
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", config.repo):
        raise BoardError(f"{CONFIG_FILE}: repo must be owner/name, not {config.repo!r}")
    return config


def parse_fields(project_json: str, fields_json: str) -> Fields:
    """The board's ID and the IDs of its Status and Priority fields and their options, from `gh project view` and
    `gh project field-list`. Names a missing field or option rather than guessing one."""
    project_id = json.loads(project_json)["id"]
    fields = {field["name"]: field for field in json.loads(fields_json)["fields"]}
    found = {}
    for name, wanted in ((STATUS_FIELD, STATUSES), (PRIORITY_FIELD, PRIORITIES)):
        field = fields.get(name)
        if field is None or "options" not in field:
            raise BoardError(f"the board has no single-select field {name!r} (wanted options: {', '.join(wanted)})")
        options = {option["name"]: option["id"] for option in field["options"]}
        missing = [option for option in wanted if option not in options]
        if missing:
            raise BoardError(f"the board's {name} field lacks the option(s) {', '.join(missing)}")
        found[name] = (field["id"], options)
    return Fields(project_id, found[STATUS_FIELD][0], found[STATUS_FIELD][1],
                  found[PRIORITY_FIELD][0], found[PRIORITY_FIELD][1])


def field_value(item: dict, name: str) -> str:
    """gh's item-list JSON gives each field's value under the field's name in lower case."""
    value = item.get(name.lower(), item.get(name))
    return value if isinstance(value, str) else ""


def status_of(item: dict) -> str:
    """An item with no Status yet counts as Triage: the board's auto-add puts new issues there without one."""
    return field_value(item, STATUS_FIELD) or TRIAGE


def repo_of(content: dict) -> str:
    repository = content.get("repository") or ""
    if isinstance(repository, dict):
        repository = repository.get("nameWithOwner", "")
    match = re.search(r"github\.com/([^/]+/[^/]+)", repository or content.get("url", ""))
    return match.group(1) if match else repository


def item_for(items: list, number: int, repo: str):
    for item in items:
        content = item.get("content") or {}
        if content.get("type") == "Issue" and content.get("number") == number and repo_of(content) == repo:
            return item
    return None


def open_blockers(issue: dict, open_numbers: set, repo: str) -> list:
    """Numbers of the blockers still open. gh's `blockedBy` may come as a list or as {"nodes": [...]}. A blocker
    with a state is open if that state is OPEN. One without a state is open if it is among this repository's open
    issues, and also when it cannot be placed (no number, or another repository): in doubt, nothing starts early."""
    value = issue.get("blockedBy") or []
    if isinstance(value, dict):
        value = value.get("nodes") or []
    blockers = []
    for blocker in value:
        number = blocker.get("number")
        state = str(blocker.get("state", "")).upper()
        if state:
            if state == "OPEN":
                blockers.append(number)
            continue
        elsewhere = repo_of(blocker) not in ("", repo)
        if number is None or elsewhere or number in open_numbers:
            blockers.append(number)
    return blockers


def ready(items: list, issues: list, repo: str) -> list:
    """Ready work: board items for open issues of this repository with Status Todo and no open blocker, ordered by
    Priority (none counts as P2), then oldest first. Each entry: number, title, priority, created."""
    open_issues = {issue["number"]: issue for issue in issues}
    rank = {priority: index for index, priority in enumerate(PRIORITIES)}
    result = []
    for item in items:
        content = item.get("content") or {}
        number = content.get("number")
        if content.get("type") != "Issue" or repo_of(content) != repo or number not in open_issues:
            continue
        if status_of(item) != TODO or open_blockers(open_issues[number], set(open_issues), repo):
            continue
        priority = field_value(item, PRIORITY_FIELD) or DEFAULT_PRIORITY
        result.append({"number": number, "title": open_issues[number].get("title", content.get("title", "")),
                       "priority": priority, "created": open_issues[number].get("createdAt", "")})
    return sorted(result, key=lambda entry: (rank.get(entry["priority"], len(PRIORITIES)), entry["created"],
                                             entry["number"]))


def claim_holder(comments: list, login: str):
    """The branch holding the claim: the earliest claim comment since the last release or done comment, or None.
    Only comments written by `login`, the account every session acts as, count. On a public repository anyone can
    comment, and a stranger's marker comment must not take, block or end a claim."""
    holder = None
    for comment in sorted(comments, key=lambda comment: comment.get("createdAt", "")):
        if ((comment.get("author") or {}).get("login") or "") != login:
            continue
        body = (comment.get("body") or "").strip()
        if body.startswith(RELEASE) or body.startswith(DONE_MARK):
            holder = None
        elif body.startswith(CLAIM) and holder is None:
            holder = body[len(CLAIM):].split()[0] if body[len(CLAIM):].split() else ""
    return holder


# ---- gh at the edge ---------------------------------------------------------------------------------------------

class Gh:
    def run(self, *args: str) -> str:
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise GhError(f"gh {' '.join(args[:3])} … failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout


class Board:
    def __init__(self, config: Config, gh: Gh):
        self.config, self.gh = config, gh
        self._fields = None
        self._login = None

    def fields(self) -> Fields:
        if self._fields is None:
            number, owner = str(self.config.project), self.config.owner
            self._fields = parse_fields(self.gh.run("project", "view", number, "--owner", owner, "--format", "json"),
                                        self.gh.run("project", "field-list", number, "--owner", owner, "--format",
                                                    "json", "--limit", LIMIT))
        return self._fields

    def items(self) -> list:
        # gh adds a field's values to the item list only when asked with --field. Without them every item would
        # read as blank, which status_of() counts as Triage.
        data = json.loads(self.gh.run("project", "item-list", str(self.config.project), "--owner", self.config.owner,
                                      "--field", STATUS_FIELD, "--field", PRIORITY_FIELD, "--format", "json",
                                      "--limit", LIMIT))
        return data.get("items") or []

    def open_issues(self) -> list:
        return json.loads(self.gh.run("issue", "list", "--repo", self.config.repo, "--state", "open", "--limit",
                                      LIMIT, "--json", "number,title,createdAt,blockedBy"))

    def set_field(self, item_id: str, field_id: str, option_id: str) -> None:
        self.gh.run("project", "item-edit", "--id", item_id, "--project-id", self.fields().project_id,
                    "--field-id", field_id, "--single-select-option-id", option_id)

    def set_status(self, item_id: str, status: str) -> None:
        fields = self.fields()
        self.set_field(item_id, fields.status_id, fields.status_options[status])

    def comment(self, number: int, body: str) -> None:
        self.gh.run("issue", "comment", str(number), "--repo", self.config.repo, "--body", body)

    def login(self) -> str:
        """The account the token belongs to: every session's comments are written as it."""
        if self._login is None:
            self._login = self.gh.run("api", "user", "--jq", ".login").strip()
            if not self._login:
                raise GhError("gh api user returned no login")
        return self._login

    def comments(self, number: int) -> list:
        return json.loads(self.gh.run("issue", "view", str(number), "--repo", self.config.repo, "--json",
                                      "comments"))["comments"]

    def item(self, number: int) -> dict:
        found = item_for(self.items(), number, self.config.repo)
        if found is None:
            raise Refused(f"issue #{number} is not on the board")
        return found

    def holder(self, number: int):
        return claim_holder(self.comments(number), self.login())

    def require_holder(self, number: int, branch: str) -> None:
        holder = self.holder(number)
        if holder != branch:
            who = "no one" if holder is None else repr(holder)
            raise Refused(f"issue #{number} is claimed by {who}, not {branch!r}; only the claiming branch may do this")

    # -- the steps --
    # Each step changes things in an order whose failure leaves the safer state, and a rerun of the same step
    # finishes it. A gh failure after the first change says what was already done.

    def ready(self) -> list:
        return ready(self.items(), self.open_issues(), self.config.repo)

    def file(self, title: str, body: str, todo: bool, priority: str | None, blocked_by: str | None) -> int:
        fields = self.fields()  # check the board before creating anything on it
        args = ["issue", "create", "--repo", self.config.repo, "--title", title, "--body", body]
        if blocked_by:
            args += ["--blocked-by", blocked_by]
        output = self.gh.run(*args).strip()
        match = re.search(rf"(https://github\.com/{re.escape(self.config.repo)}/issues/(\d+))\s*$", output)
        if not match:
            raise GhError(f"gh issue create gave no issue URL for {self.config.repo}; check the repository's issues"
                          f" for {title!r} before filing again. Output: {output[-200:]!r}")
        url, number = match.group(1), int(match.group(2))
        try:
            # Auto-add may have put it on the board already; item-add then returns the same item.
            item_id = json.loads(self.gh.run("project", "item-add", str(self.config.project), "--owner",
                                             self.config.owner, "--url", url, "--format", "json"))["id"]
            # Priority before Status: if setting Status fails, the item stays in Triage, the safe side.
            if todo:
                self.set_field(item_id, fields.priority_id, fields.priority_options[priority or DEFAULT_PRIORITY])
            self.set_status(item_id, TODO if todo else TRIAGE)
        except (GhError, KeyError, ValueError, TypeError) as error:
            raise GhError(f"issue #{number} was created, but placing it on the board failed ({error}); it counts as"
                          f" {TRIAGE}. Run `queue {number}` on the user's ask, or set it on the board.") from None
        return number

    def queue(self, number: int, priority: str | None) -> None:
        """Accept a Triage item into Todo. Triage is the user's gate, so a session runs this only when the user
        asks for that issue to be worked on or queued. Refuses a closed issue and one with a live claim, so a
        Status misread as blank cannot pull finished or claimed work back into the queue."""
        item = self.item(number)
        if status_of(item) != TRIAGE:
            raise Refused(f"issue #{number} is in {status_of(item)}, not {TRIAGE}")
        if number not in {issue["number"] for issue in self.open_issues()}:
            raise Refused(f"issue #{number} is closed")
        if self.holder(number) is not None:
            raise Refused(f"issue #{number} has a live claim by {self.holder(number)!r}")
        fields = self.fields()
        # Priority before Status: if setting Status fails, the item stays in Triage, and a rerun finishes it.
        self.set_field(item["id"], fields.priority_id, fields.priority_options[priority or DEFAULT_PRIORITY])
        self.set_status(item["id"], TODO)

    def claim(self, number: int, branch: str, worktree: str | None) -> None:
        if number not in [entry["number"] for entry in self.ready()]:
            item = item_for(self.items(), number, self.config.repo)
            state = "not on the board" if item is None else f"in {status_of(item)}, or blocked, or closed"
            raise Refused(f"issue #{number} is not ready work ({state}); only Todo with no open blocker can be claimed")
        # The comment first: it is what decides a race. If setting the Status then fails, the item stays in Todo
        # with this branch's claim, and a rerun of claim with the same branch finds the claim its own and finishes.
        self.comment(number, f"{CLAIM} {branch}" + (f" in {worktree}" if worktree else ""))
        holder = self.holder(number)
        if holder != branch:
            raise Refused(f"issue #{number} was claimed first by {holder!r}; this session backs off")
        self.set_status(self.item(number)["id"], IN_PROGRESS)

    def release(self, number: int, branch: str, reason: str) -> None:
        item = self.item(number)
        if status_of(item) not in (IN_PROGRESS, TODO):
            raise Refused(f"issue #{number} is in {status_of(item)}, not {IN_PROGRESS}")
        self.require_holder(number, branch)
        # The Status first, then the comment that ends the claim. A rerun after a failed comment finds the item in
        # Todo, still claimed by this branch, and posts the comment.
        if status_of(item) == IN_PROGRESS:
            self.set_status(item["id"], TODO)
        self.comment(number, f"{RELEASE} {branch}: {reason}")

    def done(self, number: int, branch: str, evidence: str) -> None:
        item = self.item(number)
        if status_of(item) != IN_PROGRESS:
            raise Refused(f"issue #{number} is in {status_of(item)}, not {IN_PROGRESS}; claim it before closing it")
        self.require_holder(number, branch)
        # Closing first: the board's "Item closed" workflow sets Done as well, so a failure setting Done leaves a
        # closed issue the workflow still files under Done.
        self.gh.run("issue", "close", str(number), "--repo", self.config.repo, "--comment",
                    f"{DONE_MARK} {branch}: {evidence}")
        self.set_status(item["id"], DONE)


# ---- command line -----------------------------------------------------------------------------------------------

def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="board.py", description="Run a project's GitHub board by name.")
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser("ready").add_argument("--json", action="store_true")
    file_ = steps.add_parser("file")
    where = file_.add_mutually_exclusive_group(required=True)
    where.add_argument("--triage", action="store_true")
    where.add_argument("--todo", action="store_true")
    file_.add_argument("--priority", choices=PRIORITIES)
    file_.add_argument("--title", required=True)
    file_.add_argument("--body", default="")
    file_.add_argument("--blocked-by")
    queue = steps.add_parser("queue")
    queue.add_argument("number", type=int)
    queue.add_argument("--priority", choices=PRIORITIES)
    claim = steps.add_parser("claim")
    claim.add_argument("number", type=int)
    claim.add_argument("--branch", required=True)
    claim.add_argument("--worktree")
    release = steps.add_parser("release")
    release.add_argument("number", type=int)
    release.add_argument("--branch", required=True)
    release.add_argument("--reason", required=True)
    done = steps.add_parser("done")
    done.add_argument("number", type=int)
    done.add_argument("--branch", required=True)
    done.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    if args.step == "file" and args.triage and args.priority:
        parser.error("--priority goes with --todo: the user sets Priority when accepting a Triage item")
    return args


def find_config(start: Path) -> Path:
    for folder in (start, *start.parents):
        if (folder / CONFIG_FILE).is_file():
            return folder / CONFIG_FILE
        if (folder / ".git").exists():
            break
    raise BoardError(f"no {CONFIG_FILE} at the repository root: this project does not keep its tasks on a board")


def main(argv: list, gh: Gh | None = None, cwd: Path | None = None) -> int:
    try:
        args = parse_args(argv)
        board = Board(parse_config(find_config(cwd or Path.cwd()).read_text()), gh or Gh())
        if args.step == "ready":
            entries = board.ready()
            if args.json:
                print(json.dumps(entries, ensure_ascii=False))
            else:
                for entry in entries:
                    print(f"#{entry['number']}  {entry['priority']}  {entry['title']}")
                print(f"{len(entries)} ready")
        elif args.step == "file":
            number = board.file(args.title, args.body, args.todo, args.priority, args.blocked_by)
            print(f"filed #{number} in {TODO if args.todo else TRIAGE}")
        elif args.step == "queue":
            board.queue(args.number, args.priority)
            print(f"queued #{args.number} in {TODO} as {args.priority or DEFAULT_PRIORITY}")
        elif args.step == "claim":
            board.claim(args.number, args.branch, args.worktree)
            print(f"claimed #{args.number} for {args.branch}")
        elif args.step == "release":
            board.release(args.number, args.branch, args.reason)
            print(f"released #{args.number} to {TODO}")
        else:
            board.done(args.number, args.branch, args.evidence)
            print(f"closed #{args.number} as {DONE}")
        return 0
    except BoardError as error:
        print(f"board.py: {error}", file=sys.stderr)
        return 1
    except GhError as error:
        print(f"board.py: {error}", file=sys.stderr)
        return 2
    except Refused as error:
        print(f"board.py: refused: {error}", file=sys.stderr)
        return 3
    except (KeyError, ValueError, TypeError, IndexError, AttributeError) as error:
        # gh answered in a shape this script does not expect: report it as gh's failure, not a traceback.
        print(f"board.py: unexpected output from gh ({type(error).__name__}: {error})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
