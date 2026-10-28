#!/usr/bin/env python3
"""Run a project's GitHub board by name: ready, file, queue, claim, release, done, and check.

The task-board skill (SKILL.md beside this file) describes the workflow; this script is its only way to change the
board, so no session has to look up the board's internal IDs, and a wrong ID cannot set the wrong field. It reads
`.task-board.json` at the repository root, for example
    {"owner": "tia-tools", "project": 3, "repo": "tia-tools/gmks-hif-final-stats"}
and calls `gh`, which takes its token from the project's GH_CONFIG_DIR (global CLAUDE.md § Git Operations).

What it relies on, and why (plan 0031 in the Taka499/claude repo):
- the board through GitHub's GraphQL API only, via `gh api graphql`: GA since 2022, breaking changes announced at
  least three months ahead. Not `gh project …`, whose commands and JSON are gh's own and have changed;
- the organization's issue field "Priority" through the REST API, with the version pinned (REST_VERSION), so a
  change of gh's default cannot move it;
- every shape it reads is checked, and anything unexpected stops with exit 2 instead of being read as a default.
Standard library only; Python 3.9 or later.

Usage:
    python3 -I board.py check                                   (read-only: is the board and the API as expected?)
    python3 -I board.py ready [--json]
    python3 -I board.py file (--triage | --todo [--priority NAME]) --title TITLE [--body BODY] [--blocked-by 3,7]
    python3 -I board.py queue N [--priority NAME]               (only when the user asks: Triage is their gate)
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
# Markers at the start of the comments this script writes, so a later run can read the claim history back.
CLAIM, RELEASE, DONE_MARK = "task-board claim:", "task-board release:", "task-board done:"
LIMIT = "1000"  # gh's list commands default to 30 items
# The REST version every REST call names. Supported until at least 2028-03-10; `check` warns when GitHub marks it
# deprecated or stops listing it.
REST_VERSION = "2022-11-28"
REST_HEADER = f"X-GitHub-Api-Version: {REST_VERSION}"

# The board's ID, its Status field and options, and its items with their Status, asked for by name.
BOARD_QUERY = """query($owner: String!, $number: Int!, $after: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      field(name: "Status") {
        __typename
        ... on ProjectV2SingleSelectField { id options { id name } }
      }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          status: fieldValueByName(name: "Status") {
            __typename
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content { __typename ... on Issue { number title url repository { nameWithOwner } } }
        }
      }
    }
  }
}"""
SET_STATUS_MUTATION = """mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
                                        value: {singleSelectOptionId: $option}}) {
    projectV2Item { id }
  }
}"""
ADD_ITEM_MUTATION = """mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } }
}"""


class BoardError(Exception):
    """Bad usage or configuration (exit 1)."""


class GhError(Exception):
    """gh exited non-zero, or answered in a shape this script does not expect (exit 2)."""


class Refused(Exception):
    """The issue is not in a state that allows the step, or another session holds it (exit 3)."""


@dataclass(frozen=True)
class Config:
    owner: str
    project: int
    repo: str


@dataclass(frozen=True)
class StatusField:
    project_id: str
    status_id: str
    status_options: dict  # option name -> option id


@dataclass(frozen=True)
class PriorityField:
    field_id: int
    priorities: tuple  # option names, most urgent first

    def default_priority(self) -> str:
        """The middle option (Medium of Urgent, High, Medium, Low): what an issue without a Priority counts as."""
        return self.priorities[len(self.priorities) // 2]

    def priority(self, name: str | None) -> str:
        if name is None:
            return self.default_priority()
        if name not in self.priorities:
            raise BoardError(f"there is no Priority {name!r}; the options are {', '.join(self.priorities)}")
        return name


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


def graphql_data(response_json: str) -> dict:
    """The `data` of a GraphQL response; its `errors` become a GhError."""
    response = json.loads(response_json)
    if not isinstance(response, dict):
        raise GhError(f"GraphQL answered with {type(response).__name__}, not an object")
    if response.get("errors"):
        raise GhError(f"GraphQL: {'; '.join(str(error.get('message', error)) for error in response['errors'])}")
    if not isinstance(response.get("data"), dict):
        raise GhError("GraphQL answered with no data")
    return response["data"]


def parse_board_page(page_json: str, project: int):
    """One page of BOARD_QUERY: (the Status field, the page's items, the cursor of the next page or None).

    Each item is {"id", "status", "content": {"type", "number", "title", "url", "repository"}}. "status" is the
    name of the item's Status option, or "" where the item has none. Fails closed: a missing or renamed Status
    field, a missing option, or a value that is not a named single-select option stops the run, so nothing is
    silently read as Triage."""
    board = (graphql_data(page_json).get("organization") or {}).get("projectV2")
    if board is None:
        raise BoardError(f"no board number {project} for this owner, or the token cannot read it")
    field = board.get("field")
    if not field:
        raise BoardError(f"the board has no field named {STATUS_FIELD!r}; was it renamed? (wanted options:"
                         f" {', '.join(STATUSES)})")
    if field.get("__typename") != "ProjectV2SingleSelectField" or not field.get("options"):
        raise BoardError(f"the board's {STATUS_FIELD!r} field is a {field.get('__typename')}, not a single-select"
                         f" field with options")
    options = {option["name"]: option["id"] for option in field["options"]}
    missing = [option for option in STATUSES if option not in options]
    if missing:
        raise BoardError(f"the board's {STATUS_FIELD} field lacks the option(s) {', '.join(missing)}")
    status_field = StatusField(board["id"], field["id"], options)
    page = board["items"]
    items = []
    for node in page.get("nodes") or []:
        value = node.get("status")
        if value is None:
            status = ""
        elif value.get("__typename") == "ProjectV2ItemFieldSingleSelectValue" and value.get("name"):
            status = value["name"]
        else:
            raise GhError(f"item {node.get('id')!r} has a Status of an unexpected shape: {value!r}")
        content = node.get("content") or {}
        items.append({"id": node["id"], "status": status,
                      "content": {"type": content.get("__typename", ""), "number": content.get("number"),
                                  "title": content.get("title", ""), "url": content.get("url", ""),
                                  "repository": (content.get("repository") or {}).get("nameWithOwner", "")}})
    info = page.get("pageInfo") or {}
    return status_field, items, (info.get("endCursor") if info.get("hasNextPage") else None)


def mutation_id(response_json: str, *path: str) -> str:
    """The ID a mutation answered with, at `path` inside its data; anything else is a GhError."""
    value = graphql_data(response_json)
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if not isinstance(value, str) or not value:
        raise GhError(f"GraphQL mutation answered without {'.'.join(path)}")
    return value


def parse_priority_field(issue_fields_json: str) -> PriorityField:
    """The organization's issue field "Priority", from `GET /orgs/{org}/issue-fields`. Its options are listed in no
    useful order (measured: High, Low, Medium, Urgent), so they are ranked by each option's own "priority" number,
    1 the most urgent; an option without one goes last, in listed order."""
    for field in json.loads(issue_fields_json):
        if field.get("name") == PRIORITY_FIELD and field.get("data_type") == "single_select" and field.get("options"):
            listed = list(enumerate(field["options"]))
            if not all(isinstance(option.get("name"), str) and option["name"] for _, option in listed):
                raise GhError(f"the organization's {PRIORITY_FIELD} field has an option without a name")
            ranked = sorted(listed, key=lambda pair: (pair[1].get("priority") is None,
                                                      pair[1].get("priority") or 0, pair[0]))
            return PriorityField(int(field["id"]), tuple(option["name"] for _, option in ranked))
    raise BoardError(f"the organization has no single-select issue field {PRIORITY_FIELD!r} with options (the"
                     f" token needs Organization permissions: Issue Fields, read)")


def priority_value(values_json: str, field_id: int) -> str:
    """An issue's Priority from `GET …/issues/{n}/issue-field-values`, or "" if it has none. An entry for the field
    without an option name stops the run rather than counting as the default."""
    for entry in json.loads(values_json):
        if entry.get("issue_field_id") == field_id:
            name = (entry.get("single_select_option") or {}).get("name")
            if not isinstance(name, str) or not name:
                raise GhError(f"the issue's {PRIORITY_FIELD} value has an unexpected shape: {entry!r}")
            return name
    return ""


def parse_headers(response: str) -> dict:
    """The headers of `gh api -i` output, lower-cased: the lines after the status line, up to the first blank."""
    headers = {}
    for line in response.replace("\r\n", "\n").split("\n\n", 1)[0].split("\n")[1:]:
        name, _, value = line.partition(":")
        if value:
            headers[name.strip().lower()] = value.strip()
    return headers


def status_of(item: dict) -> str:
    """An item with no Status yet counts as Triage: the board's auto-add puts new issues there without one."""
    status = item.get("status")
    return status if isinstance(status, str) and status else TRIAGE


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


def ready_candidates(items: list, issues: list, repo: str) -> list:
    """Numbers of the board's items for open issues of this repository with Status Todo and no open blocker."""
    open_issues = {issue["number"]: issue for issue in issues}
    numbers = []
    for item in items:
        content = item.get("content") or {}
        number = content.get("number")
        if content.get("type") != "Issue" or repo_of(content) != repo or number not in open_issues:
            continue
        if status_of(item) == TODO and not open_blockers(open_issues[number], set(open_issues), repo):
            numbers.append(number)
    return numbers


def ready(items: list, issues: list, repo: str, priorities, priority_of: dict) -> list:
    """Ready work, ordered by Priority (most urgent first; an issue without one counts as the middle option), then
    oldest first. `priority_of` maps an issue number to its Priority, or "" for none. Each entry: number, title,
    priority, created."""
    open_issues = {issue["number"]: issue for issue in issues}
    rank = {priority: index for index, priority in enumerate(priorities)}
    default = priorities[len(priorities) // 2]
    result = []
    for number in ready_candidates(items, issues, repo):
        priority = priority_of.get(number) or default
        result.append({"number": number, "title": open_issues[number].get("title", ""), "priority": priority,
                       "created": open_issues[number].get("createdAt", "")})
    return sorted(result, key=lambda entry: (rank.get(entry["priority"], len(priorities)), entry["created"],
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


def last_marker(comments: list, login: str):
    """The latest of this account's marker comments, as (kind, branch), kind being claim, release or done; or
    None. Lets `done` recognise its own earlier, half-finished run."""
    last = None
    for comment in sorted(comments, key=lambda comment: comment.get("createdAt", "")):
        if ((comment.get("author") or {}).get("login") or "") != login:
            continue
        body = (comment.get("body") or "").strip()
        for kind, marker in (("claim", CLAIM), ("release", RELEASE), ("done", DONE_MARK)):
            if body.startswith(marker):
                words = body[len(marker):].replace(":", " ").split()
                last = (kind, words[0] if words else "")
    return last


# ---- gh at the edge ---------------------------------------------------------------------------------------------

class Gh:
    def __init__(self, executable: str = "gh"):
        self.executable = executable

    def run(self, *args: str, input: str | None = None) -> str:
        try:
            result = subprocess.run([self.executable, *args], capture_output=True, text=True, input=input)
        except OSError as error:
            raise GhError(f"could not run {self.executable}: {error}") from None
        if result.returncode != 0:
            raise GhError(f"gh {' '.join(args[:3])} … failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout


class Board:
    def __init__(self, config: Config, gh: Gh):
        self.config, self.gh = config, gh
        self._status_field = None
        self._priority_field = None
        self._login = None

    # -- reading --

    def graphql(self, query: str, *variables: str) -> str:
        """`gh api graphql` with `query` and `variables` given as `-f name=value`, or `-F` for an integer."""
        args = ["api", "graphql", "-f", f"query={query}"]
        for variable in variables:
            flag = "-F" if variable.startswith("number=") else "-f"
            args += [flag, variable]
        return self.gh.run(*args)

    def rest(self, path: str, *extra: str, input: str | None = None) -> str:
        """`gh api` against REST, naming the pinned version."""
        return self.gh.run("api", "-H", REST_HEADER, *extra, path, input=input)

    def board(self):
        """(the Status field, every item), reading all pages of BOARD_QUERY."""
        items, cursor, seen = [], None, set()
        while True:
            variables = [f"owner={self.config.owner}", f"number={self.config.project}"]
            if cursor:
                variables.append(f"after={cursor}")
            field, page, cursor = parse_board_page(self.graphql(BOARD_QUERY, *variables), self.config.project)
            self._status_field = field
            items += page
            if cursor is None:
                return field, items
            if cursor in seen:  # a page that does not advance would otherwise loop forever
                raise GhError(f"the board's item pages did not advance: cursor {cursor!r} came back twice")
            seen.add(cursor)

    def status_field(self) -> StatusField:
        if self._status_field is None:
            self.board()
        return self._status_field

    def items(self) -> list:
        return self.board()[1]

    def priority_field(self) -> PriorityField:
        if self._priority_field is None:
            self._priority_field = parse_priority_field(self.rest(f"orgs/{self.config.owner}/issue-fields"))
        return self._priority_field

    def priority_of(self, number: int) -> str:
        return priority_value(self.rest(f"repos/{self.config.repo}/issues/{number}/issue-field-values"),
                              self.priority_field().field_id)

    def open_issues(self) -> list:
        return json.loads(self.gh.run("issue", "list", "--repo", self.config.repo, "--state", "open", "--limit",
                                      LIMIT, "--json", "number,title,createdAt,blockedBy"))

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

    # -- writing --

    def set_status(self, item_id: str, status: str) -> None:
        field = self.status_field()
        answered = mutation_id(self.graphql(SET_STATUS_MUTATION, f"project={field.project_id}", f"item={item_id}",
                                            f"field={field.status_id}", f"option={field.status_options[status]}"),
                               "updateProjectV2ItemFieldValue", "projectV2Item", "id")
        if answered != item_id:
            raise GhError(f"setting Status answered for item {answered!r}, not {item_id!r}")

    def set_priority(self, number: int, name: str) -> None:
        body = {"issue_field_values": [{"field_id": self.priority_field().field_id, "value": name}]}
        self.rest(f"repos/{self.config.repo}/issues/{number}/issue-field-values", "--method", "POST", "--input", "-",
                  input=json.dumps(body))

    def add_to_board(self, number: int) -> str:
        """Add issue `number` to the board, and return its item ID. Adding an issue already on the board (auto-add
        may have been first) returns the existing item."""
        node = json.loads(self.rest(f"repos/{self.config.repo}/issues/{number}")).get("node_id")
        if not isinstance(node, str) or not node:
            raise GhError(f"issue #{number} came back without a node_id")
        return mutation_id(self.graphql(ADD_ITEM_MUTATION, f"project={self.status_field().project_id}",
                                        f"content={node}"), "addProjectV2ItemById", "item", "id")

    def comment(self, number: int, body: str) -> None:
        self.gh.run("issue", "comment", str(number), "--repo", self.config.repo, "--body", body)

    # -- the steps --
    # Each step changes things in an order whose failure leaves the safer state, and a rerun of the same step
    # finishes it. A gh failure after the first change says what was already done.

    def check(self) -> list:
        """Read-only: everything the other steps rely on, read once from the live board and API. Returns report
        lines; a shape the steps could not use raises, as it would there. A deprecated REST version only warns."""
        lines = []
        field, items = self.board()
        lines.append(f"ok: board {self.config.owner} #{self.config.project}: {STATUS_FIELD} has"
                     f" {', '.join(field.status_options)}; {len(items)} item(s), every Status readable")
        priority = self.priority_field()
        lines.append(f"ok: {PRIORITY_FIELD} options, most urgent first: {' > '.join(priority.priorities)}"
                     f" (default {priority.default_priority()})")
        issues = self.open_issues()
        lines.append(f"ok: {len(issues)} open issue(s) in {self.config.repo}")
        on_board = [item["content"]["number"] for item in items
                    if item["content"]["type"] == "Issue" and repo_of(item["content"]) == self.config.repo]
        for number in on_board[:3]:
            self.priority_of(number)
        lines.append(f"ok: {PRIORITY_FIELD} read for {len(on_board[:3])} issue(s) on the board")
        lines.append(f"ok: acting as {self.login()}")
        versions = json.loads(self.rest("versions"))
        if REST_VERSION not in versions:
            raise GhError(f"GitHub no longer lists REST version {REST_VERSION} (it lists {', '.join(versions)})")
        headers = parse_headers(self.rest(f"orgs/{self.config.owner}/issue-fields", "-i"))
        if "deprecation" in headers or "sunset" in headers:
            lines.append(f"warn: GitHub marks REST version {REST_VERSION} deprecated (Deprecation:"
                         f" {headers.get('deprecation', '-')}; Sunset: {headers.get('sunset', '-')}); move REST_VERSION")
        else:
            lines.append(f"ok: REST version {REST_VERSION} supported, not marked deprecated")
        return lines

    def ready(self) -> list:
        items, issues = self.items(), self.open_issues()
        priorities = self.priority_field().priorities
        candidates = ready_candidates(items, issues, self.config.repo)
        return ready(items, issues, self.config.repo, priorities,
                     {number: self.priority_of(number) for number in candidates})

    def file(self, title: str, body: str, todo: bool, priority: str | None, blocked_by: str | None) -> int:
        self.status_field()  # check the board, and the priority, before creating anything on it
        chosen = self.priority_field().priority(priority) if todo else None
        args = ["issue", "create", "--repo", self.config.repo, "--title", title, "--body", body]
        if blocked_by:
            args += ["--blocked-by", blocked_by]
        output = self.gh.run(*args).strip()
        match = re.search(rf"(https://github\.com/{re.escape(self.config.repo)}/issues/(\d+))\s*$", output)
        if not match:
            raise GhError(f"gh issue create gave no issue URL for {self.config.repo}; check the repository's issues"
                          f" for {title!r} before filing again. Output: {output[-200:]!r}")
        number = int(match.group(2))
        try:
            item_id = self.add_to_board(number)
            # Priority before Status: if setting Status fails, the item stays in Triage, the safe side.
            if todo:
                self.set_priority(number, chosen)
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
        chosen = self.priority_field().priority(priority)
        # Priority before Status: if setting Status fails, the item stays in Triage, and a rerun finishes it.
        self.set_priority(number, chosen)
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
        closed = number not in {issue["number"] for issue in self.open_issues()}
        if closed and last_marker(self.comments(number), self.login()) == ("done", branch):
            # A rerun: this branch's earlier run closed the issue, and its done comment ended the claim, but
            # setting Done failed. Finish that.
            self.set_status(item["id"], DONE)
            return
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
    steps.add_parser("check")
    steps.add_parser("ready").add_argument("--json", action="store_true")
    file_ = steps.add_parser("file")
    where = file_.add_mutually_exclusive_group(required=True)
    where.add_argument("--triage", action="store_true")
    where.add_argument("--todo", action="store_true")
    file_.add_argument("--priority", help="one of the Priority options; default: the middle one")
    file_.add_argument("--title", required=True)
    file_.add_argument("--body", default="")
    file_.add_argument("--blocked-by")
    queue = steps.add_parser("queue")
    queue.add_argument("number", type=int)
    queue.add_argument("--priority", help="one of the Priority options; default: the middle one")
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
        if args.step == "check":
            for line in board.check():
                print(line)
        elif args.step == "ready":
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
            print(f"queued #{args.number} in {TODO} as {args.priority or board.priority_field().default_priority()}")
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
