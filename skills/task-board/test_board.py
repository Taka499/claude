"""Tests for board.py. Run: python3 -m unittest discover -s skills/task-board

The fixtures marked "captured" are trimmed from real gh output: against the tia-tools board on 2026-10-29 (plan 0031),
and against scratch boards of both owners on 2026-10-30 (plan 0033). The GraphQL shapes follow GitHub's public schema.
The last class runs the real gh binary on every command the other tests produced, offline, so an argument gh refuses
fails here and not on a real board."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import board  # beside this file: discover -s and direct runs both put this folder on the import path

REPO = "o/r"
PROJECT_ID = "PVT_kwDOEfCcUc4BpKm6"
STATUS_FIELD_ID = "PVTSSF_lADOEfCcUc4BpKm6zhnnb4c"
# captured: the board's Status options, from `gh project field-list 1 --owner tia-tools --format json`
STATUS_IDS = {"Triage": "782d1866", "Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}
STATUS_FIELD = {"__typename": "ProjectV2SingleSelectField", "id": STATUS_FIELD_ID,
                "options": [{"id": option_id, "name": name} for name, option_id in STATUS_IDS.items()]}
# captured: `gh api /orgs/tia-tools/issue-fields`, trimmed. The options come in no useful order; "priority" ranks them.
PRIORITY_FIELD_ID = 43924878
ISSUE_FIELDS = [
    {"id": PRIORITY_FIELD_ID, "name": "Priority", "data_type": "single_select",
     "options": [{"id": 76872379, "name": "High", "priority": 2}, {"id": 76872381, "name": "Low", "priority": 4},
                 {"id": 76872380, "name": "Medium", "priority": 3}, {"id": 76872378, "name": "Urgent", "priority": 1}]},
    {"id": 43924879, "name": "Start date", "data_type": "date"},
    {"id": 43924881, "name": "Effort", "data_type": "single_select",
     "options": [{"id": 76872382, "name": "High", "priority": 1}, {"id": 76872384, "name": "Low", "priority": 3},
                 {"id": 76872383, "name": "Medium", "priority": 2}]}]
PRIORITIES = ("Urgent", "High", "Medium", "Low")
OPTION_IDS = {"Urgent": 76872378, "High": 76872379, "Medium": 76872380, "Low": 76872381}
# captured: `gh api …/issues/1/issue-field-values` after the user set Priority High on the board. "value" is the
# option's numeric ID, not its name; the name is only in single_select_option.
FIELD_VALUES_CAPTURED = [{"issue_field_id": 43924878, "node_id": "IFSSV_kgDOAOdA_w", "data_type": "single_select",
                          "issue_field_name": "Priority", "value": 76872379,
                          "single_select_option": {"id": 76872379, "name": "High", "color": "red"}}]
# captured (2026-10-30): BOARD_QUERY's `priority` on tia-tools #1, where Priority is the organization's issue field.
# The board's field has no options, and an item's value names no option; both are ignored there.
ORG_PRIORITY_ON_BOARD = {"__typename": "ProjectV2SingleSelectField", "id": "PVTSSF_lADOEfCcUc4BpKm6zhnnk50",
                         "isIssueField": True, "options": []}
ORG_ITEM_PRIORITY = {"__typename": "ProjectV2ItemIssueFieldValue"}
# captured (2026-10-30): a user's scratch board with its own Priority field, made as setup_board.py makes it.
USER_PRIORITY_FIELD_ID = "PVTSSF_lAHOANfZRs4Bpb6Hzhn3kgg"
USER_PRIORITY_IDS = {"Urgent": "82c96254", "High": "4b573078", "Medium": "74cc6f2b", "Low": "0d90351d"}
USER_PRIORITY_FIELD = {"__typename": "ProjectV2SingleSelectField", "id": USER_PRIORITY_FIELD_ID, "isIssueField": False,
                       "options": [{"id": option_id, "name": name} for name, option_id in USER_PRIORITY_IDS.items()]}
# captured (2026-10-30): the workflows of a new board, all on. "Item added to project" sets Todo on every item added.
NEW_BOARD_WORKFLOWS = (("Auto-add sub-issues to project", True), ("Auto-close issue", True),
                       ("Item added to project", True), ("Item closed", True), ("Pull request linked to issue", True),
                       ("Pull request merged", True))
SET_UP_WORKFLOWS = tuple(entry for entry in NEW_BOARD_WORKFLOWS if entry[0] != "Item added to project")


def item(number: int, status: str | None, repo: str = REPO, kind: str = "Issue", archived: bool = False) -> dict:
    """A board item as parse_board_page returns it."""
    return {"id": f"PVTI_{number}", "archived": archived, "status": status or "",
            "content": {"type": kind, "number": number, "title": f"issue {number}",
                        "url": f"https://github.com/{repo}/issues/{number}", "repository": repo}}


def issue(number: int, created: str = "2026-10-01T00:00:00Z", blocked_by=None, author: str = "me") -> dict:
    return {"number": number, "title": f"issue {number}", "createdAt": created, "blockedBy": blocked_by or [],
            "author": {"login": author}}


def comment(body: str, at: str, login: str = "me") -> dict:
    return {"body": body, "createdAt": f"2026-10-29T{at}:00Z", "author": {"login": login}}


def claimed(branch: str = "feature/x", at: str = "10:00") -> dict:
    return comment(f"task-board claim: {branch}", at)


def board_page(items: list, cursor: str | None, field=STATUS_FIELD, owner_type: str = "Organization",
               priorities=None, priority_field="as captured") -> str:
    """A page of BOARD_QUERY's answer, shaped as GitHub's schema and the captured pages give it. On a user's board,
    `priorities` (issue number -> option name) fills each item's Priority; on an organization's, an item with a
    Priority carries the issue field's value, as captured."""
    priorities = priorities or {}

    def priority(entry):
        name = priorities.get(entry["content"]["number"])
        if not name:
            return None
        if owner_type == "User":
            return {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": name}
        return ORG_ITEM_PRIORITY

    nodes = [{"id": entry["id"], "isArchived": entry.get("archived", False),
              "status": {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": entry["status"]}
              if entry["status"] else None,
              "priority": priority(entry),
              "content": {"__typename": entry["content"]["type"], "number": entry["content"]["number"],
                          "title": entry["content"]["title"], "url": entry["content"]["url"],
                          "repository": {"nameWithOwner": entry["content"]["repository"]}}}
             for entry in items]
    if priority_field == "as captured":
        priority_field = USER_PRIORITY_FIELD if owner_type == "User" else ORG_PRIORITY_ON_BOARD
    fields = [{"__typename": "ProjectV2Field", "name": "Title"}]  # the board lists every field; None leaves one out
    fields += [dict(given, name=name) for name, given in (("Status", field), ("Priority", priority_field)) if given]
    return json.dumps({"data": {"repositoryOwner": {"__typename": owner_type, "projectV2": {
        "id": PROJECT_ID, "fields": {"nodes": fields}, "items": {
            "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}}}}})


def variables(args: tuple) -> dict:
    """The -f/-F name=value pairs of a gh api graphql call."""
    found = {}
    for flag, value in zip(args, args[1:]):
        if flag in ("-f", "-F"):
            name, _, rest = value.partition("=")
            found[name] = rest
    return found


class FakeGh:
    """Answers the gh calls Board makes, and records them. Each call is named by what it does (`kind`), and
    fail_on fails every call of that kind, fail_once_on only the first, to test a rerun. The board's items come
    back through GraphQL in pages of `page_size`. On an organization's board (the default) Priorities live per
    issue, as the organization's field does; with owner_type="User" they live on the board's items."""

    def __init__(self, items=(), issues=(), comments=None, priorities=None, fail_on=None, fail_once_on=None,
                 create_output=None, page_size=100, versions=("2022-11-28", "2026-03-10"), deprecated=False,
                 canonical=REPO, add_conflict=False, owner_type="Organization", workflows=SET_UP_WORKFLOWS):
        self.items, self.issues = list(items), list(issues)
        self.comments = {number: list(entries) for number, entries in (comments or {}).items()}
        self.priorities = dict(priorities or {})
        self.fail_on, self.fail_once_on, self.page_size, self.calls = fail_on, fail_once_on, page_size, []
        self.create_output = "https://github.com/o/r/issues/9\n" if create_output is None else create_output
        self.versions, self.deprecated = list(versions), deprecated
        # canonical: the repository's current name, as GitHub answers for the configured one (a rename changes it).
        # add_conflict: adding an issue fails with ALREADY_ON_BOARD, auto-add having placed it a moment before.
        self.canonical, self.add_conflict = canonical, add_conflict
        self.owner_type, self.workflows = owner_type, list(workflows)
        self.closed = []  # issues closed by a step, still readable by `gh issue view`
        self.editors = {}  # issue number -> who last edited its text (GraphQL Issue.editor)

    @staticmethod
    def kind(args: tuple) -> str:
        if args[:2] == ("api", "graphql"):
            given = variables(args)
            if given["query"] == board.SET_OPTION_MUTATION:
                return "set-status" if given["field"] == STATUS_FIELD_ID else "set-priority"
            return {board.BOARD_QUERY: "board", board.ADD_ITEM_MUTATION: "add-item",
                    board.WORKFLOWS_QUERY: "workflows", board.EDITOR_QUERY: "editor"}[given["query"]]
        if args[:3] == ("api", "-H", board.REST_HEADER):
            path = args[-1]
            if path.endswith("/issue-field-values"):
                return "priority-write" if "--method" in args else "priority-read"
            if path.endswith("/issue-fields"):
                return "issue-fields-headers" if "-i" in args else "issue-fields"
            if path == "versions":
                return "versions"
            if path == "user":
                return "user"
            if re.fullmatch(r"repos/[^/]+/[^/]+/issues/\d+", path):
                return "issue-node"
            if re.fullmatch(r"repos/[^/]+/[^/]+", path):
                return "repo-headers" if "-i" in args else "repo"
        if args[:2] == ("issue", "view"):
            return "comments" if args[args.index("--json") + 1] == "comments" else "issue-view"
        if args[:2] == ("issue", "list") and "--search" in args:
            return "issue-search"
        if args[:2] == ("issue", "edit"):
            return "issue-edit"
        return {("api", "user"): "user", ("issue", "list"): "issue-list", ("issue", "view"): "comments",
                ("issue", "comment"): "comment", ("issue", "create"): "issue-create",
                ("issue", "close"): "issue-close"}[args[:2]]

    def run(self, *args: str, input: str | None = None) -> str:
        self.calls.append((args, input))
        kind = self.kind(args)
        if self.fail_on == kind:
            raise board.GhError(f"gh failed ({kind})")
        if self.fail_once_on == kind:
            self.fail_once_on = None
            raise board.GhError(f"gh failed once ({kind})")
        given = variables(args)
        if kind == "board":
            start = int(given.get("after", "0"))
            end = start + self.page_size
            return board_page(self.items[start:end], str(end) if end < len(self.items) else None,
                              owner_type=self.owner_type, priorities=self.priorities)
        if kind == "editor":
            editor = self.editors.get(int(given["number"]))
            return json.dumps({"data": {"repository": {"issue": {"editor": {"login": editor} if editor else None}}}})
        if kind == "workflows":
            return json.dumps({"data": {"repositoryOwner": {"projectV2": {"workflows": {"nodes": [
                {"name": name, "enabled": enabled} for name, enabled in self.workflows]}}}}})
        if kind == "set-priority":
            assert self.owner_type == "User", "a board-field Priority is written only on a user's board"
            assert (given["project"], given["field"]) == (PROJECT_ID, USER_PRIORITY_FIELD_ID), given
            names = {option_id: name for name, option_id in USER_PRIORITY_IDS.items()}
            self.priorities[int(given["item"].split("_")[-1])] = names[given["option"]]
            return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": given["item"]}}}})
        if kind == "set-status":
            names = {option_id: name for name, option_id in STATUS_IDS.items()}
            assert (given["project"], given["field"]) == (PROJECT_ID, STATUS_FIELD_ID), given
            for entry in self.items:
                if entry["id"] == given["item"]:
                    entry["status"] = names[given["option"]]
            return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": given["item"]}}}})
        if kind == "add-item":
            assert given["project"] == PROJECT_ID, given
            number = int(given["content"][2:])
            repo = self.canonical
            if not any(entry["id"] == f"PVTI_{number}" for entry in self.items):
                self.items.append(item(number, None, repo=repo))  # added with no Status, as GitHub does
                if self.add_conflict:  # auto-add got there first: the item exists, and the mutation fails
                    raise board.GhError(f"gh api graphql -f … failed: gh: {board.ALREADY_ON_BOARD}")
            return json.dumps({"data": {"addProjectV2ItemById": {"item": {"id": f"PVTI_{number}"}}}})
        if kind == "issue-node":
            number = int(args[-1].split("/")[-1])
            return json.dumps({"number": number, "node_id": f"I_{number}"})
        if kind == "issue-fields":
            return json.dumps(ISSUE_FIELDS)
        if kind in ("repo", "repo-headers"):
            body = json.dumps({"full_name": self.canonical, "node_id": "R_1"})
            if kind == "repo":
                return body
            extra = "Deprecation: @1830297600\nSunset: Fri, 10 Mar 2028 00:00:00 GMT\n" if self.deprecated else ""
            return f"HTTP/2.0 200 OK\nContent-Type: application/json\n{extra}\n" + body
        if kind == "versions":
            return json.dumps(self.versions)
        if kind == "priority-write":
            assert self.owner_type == "Organization", "a user has no issue fields"
            number = int(args[-1].split("/")[-2])
            for value in json.loads(input)["issue_field_values"]:
                assert value["field_id"] == PRIORITY_FIELD_ID, value
                self.priorities[number] = value["value"]
            return "[]"
        if kind == "priority-read":
            number = int(args[-1].split("/")[-2])
            name = self.priorities.get(number)
            return json.dumps([] if not name else [  # shaped as FIELD_VALUES_CAPTURED
                {"issue_field_id": PRIORITY_FIELD_ID, "node_id": f"IFSSV_{number}", "data_type": "single_select",
                 "issue_field_name": "Priority", "value": OPTION_IDS.get(name, 0),
                 "single_select_option": {"id": OPTION_IDS.get(name, 0), "name": name, "color": "red"}}])
        if kind == "issue-list":
            return json.dumps(self.issues)
        if kind == "comment":
            body = args[args.index("--body") + 1]
            self.comments.setdefault(int(args[2]), []).append({"body": body, "createdAt": "2026-10-29T12:00:00Z",
                                                               "author": {"login": "me"}})
            return ""
        if kind == "comments":
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        if kind == "user":
            return "me\n"
        if kind == "issue-create":
            match = board.ISSUE_URL.search(self.create_output.strip())
            if match and not any(entry["number"] == int(match.group(2)) for entry in self.issues):
                self.issues.append({"number": int(match.group(2)), "title": args[args.index("--title") + 1],
                                    "createdAt": "2026-11-01T00:00:00Z", "blockedBy": [],
                                    "body": args[args.index("--body") + 1], "url": match.group(0).strip(),
                                    "author": {"login": "me"}})
            return self.create_output
        if kind == "issue-view":
            number = int(args[2])
            for state, pool in (("OPEN", self.issues), ("CLOSED", self.closed)):
                for entry in pool:
                    if entry["number"] == number:
                        return json.dumps({"number": number, "title": entry.get("title", ""),
                                           "body": entry.get("body", ""), "state": state,
                                           "createdAt": entry.get("createdAt", ""), "url": entry.get("url", ""),
                                           "author": entry.get("author", {"login": "me"})})
            raise board.GhError(f"no issue #{number}")
        if kind == "issue-edit":
            number = int(args[2])
            target = next(entry for entry in self.issues if entry["number"] == number)
            if "--add-blocked-by" in args:
                target.setdefault("blockedBy", []).append(
                    {"number": int(args[args.index("--add-blocked-by") + 1]), "state": "OPEN"})
            if "--body-file" in args:
                target["body"] = input
                self.editors[number] = "me"
            return ""
        if kind == "issue-search":
            return json.dumps([{"number": entry["number"], "url": entry.get("url", ""),
                                "comments": self.comments.get(entry["number"], [])}
                               for entry in self.issues + self.closed])
        if kind == "issue-close":
            number = int(args[2])
            body = args[args.index("--comment") + 1]
            self.comments.setdefault(number, []).append({"body": body, "createdAt": "2026-10-29T13:00:00Z",
                                                          "author": {"login": "me"}})
            self.closed += [entry for entry in self.issues if entry["number"] == number]
            self.issues = [entry for entry in self.issues if entry["number"] != number]
            for entry in self.issues:  # GitHub reports a closed blocker as CLOSED
                for blocker in entry.get("blockedBy") or []:
                    if blocker.get("number") == number:
                        blocker["state"] = "CLOSED"
            return ""
        raise AssertionError(f"unhandled gh call: {args}")

    def kinds(self) -> list:
        return [self.kind(args) for args, _ in self.calls]

    def edits(self) -> list:
        """The Status set by each set-status call, in order."""
        names = {option_id: name for name, option_id in STATUS_IDS.items()}
        return [names[variables(args)["option"]] for args, _ in self.calls if self.kind(args) == "set-status"]

    def priority_writes(self) -> list:
        """(issue number, Priority) of each Priority written, through REST or on a user's board."""
        names = {option_id: name for name, option_id in USER_PRIORITY_IDS.items()}
        writes = []
        for args, given in self.calls:
            if self.kind(args) == "priority-write":
                writes.append((int(args[-1].split("/")[-2]), json.loads(given)["issue_field_values"][0]["value"]))
            elif self.kind(args) == "set-priority":
                writes.append((int(variables(args)["item"].split("_")[-1]), names[variables(args)["option"]]))
        return writes

    def first(self, kind: str) -> int:
        return self.kinds().index(kind)


# Every FakeGh records here too, so the real-gh test can replay what the other tests produced.
RECORDED: list = []
_original_run = FakeGh.run


def _recording_run(self, *args, input=None):
    RECORDED.append((args, input))
    return _original_run(self, *args, input=input)


FakeGh.run = _recording_run


def make_board(gh: FakeGh) -> board.Board:
    return board.Board(board.Config(owner="o", project=1, repo=REPO), gh)


class ConfigAndFields(unittest.TestCase):
    def test_config_reads_owner_project_repo(self):
        config = board.parse_config('{"owner": "tia-tools", "project": "3", "repo": "tia-tools/x"}')
        self.assertEqual(config, board.Config("tia-tools", 3, "tia-tools/x"))

    def test_config_without_repo_is_refused(self):
        with self.assertRaises(board.BoardError):
            board.parse_config('{"owner": "o", "project": 3}')

    def test_config_repo_must_be_owner_slash_name(self):
        with self.assertRaises(board.BoardError):
            board.parse_config('{"owner": "o", "project": 3, "repo": "https://github.com/o/r"}')

    def test_priority_ranks_options_by_their_priority_number_not_their_order(self):
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        self.assertEqual(field.field_id, PRIORITY_FIELD_ID)
        self.assertEqual(field.priorities, PRIORITIES)
        self.assertEqual(field.default_priority(), "Medium")
        self.assertEqual(field.priority("Low"), "Low")
        with self.assertRaisesRegex(board.BoardError, "Urgent, High, Medium, Low"):
            field.priority("P1")

    def test_an_option_without_an_integer_priority_stops_rather_than_sorting_last(self):
        for bad in (None, "2", True, 2.0):
            fields = json.loads(json.dumps(ISSUE_FIELDS))
            fields[0]["options"][0]["priority"] = bad
            with self.assertRaisesRegex(board.GhError, "High"):
                board.parse_priority_field(json.dumps(fields))
        fields = json.loads(json.dumps(ISSUE_FIELDS))
        del fields[0]["options"][1]["priority"]
        with self.assertRaisesRegex(board.GhError, "Low"):
            board.parse_priority_field(json.dumps(fields))

    def test_two_priority_options_of_one_name_stop(self):
        fields = json.loads(json.dumps(ISSUE_FIELDS))
        fields[0]["options"].append({"id": 1, "name": "High", "priority": 5})
        with self.assertRaisesRegex(board.GhError, "two options"):
            board.parse_priority_field(json.dumps(fields))

    def test_priority_is_the_field_named_priority_not_another_with_the_same_options(self):
        only_effort = [field for field in ISSUE_FIELDS if field["name"] != "Priority"]
        with self.assertRaisesRegex(board.BoardError, "Issue Fields"):
            board.parse_priority_field(json.dumps(only_effort))

    def test_an_issues_priority_is_read_from_its_field_values(self):
        values = [{"issue_field_id": 43924881, "single_select_option": {"name": "High"}},
                  {"issue_field_id": PRIORITY_FIELD_ID, "single_select_option": {"name": "Urgent"}}]
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        self.assertEqual(board.priority_value(json.dumps(values), field), "Urgent")
        self.assertEqual(board.priority_value("[]", field), "")

    def test_the_captured_priority_value_reads_as_its_option_name_not_its_numeric_value(self):
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        self.assertEqual(board.priority_value(json.dumps(FIELD_VALUES_CAPTURED), field), "High")

    def test_a_priority_entry_without_an_option_name_stops_rather_than_counting_as_the_default(self):
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        for entry in ({"issue_field_id": PRIORITY_FIELD_ID, "single_select_option": None, "value": "High"},
                      {"issue_field_id": PRIORITY_FIELD_ID, "single_select_option": {"name": ""}}):
            with self.assertRaises(board.GhError):
                board.priority_value(json.dumps([entry]), field)

    def test_a_priority_that_is_not_one_of_the_options_stops_rather_than_sorting_last(self):
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        entry = {"issue_field_id": PRIORITY_FIELD_ID, "single_select_option": {"name": "Critical"}}
        with self.assertRaisesRegex(board.GhError, "Critical"):
            board.priority_value(json.dumps([entry]), field)


class BoardPages(unittest.TestCase):
    def test_a_node_without_status_reads_as_triage_and_with_one_as_that_status(self):
        field, items, cursor = board.parse_board_page(board_page([item(1, None), item(2, "Todo")], None), 1)
        self.assertIsNone(cursor)
        self.assertEqual((field.project_id, field.status_id), (PROJECT_ID, STATUS_FIELD_ID))
        self.assertEqual(field.status_options["In Progress"], "47fc9ee4")
        self.assertEqual([board.status_of(entry) for entry in items], ["Triage", "Todo"])
        self.assertEqual(items[1]["content"]["repository"], REPO)

    def test_a_status_value_of_another_shape_stops_rather_than_reading_as_triage(self):
        page = json.loads(board_page([item(1, "Todo")], None))
        node = page["data"]["repositoryOwner"]["projectV2"]["items"]["nodes"][0]
        for value in ({}, {"__typename": "ProjectV2ItemFieldTextValue", "text": "Todo"},
                      {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": None}):
            node["status"] = value
            with self.assertRaises(board.GhError):
                board.parse_board_page(json.dumps(page), 1)

    def test_a_renamed_missing_or_retyped_status_field_is_named(self):
        for field, pattern in ((None, "renamed"), ({"__typename": "ProjectV2Field", "id": "x"}, "single-select"),
                               (dict(STATUS_FIELD, options=STATUS_FIELD["options"][1:]), "Triage")):
            with self.assertRaisesRegex(board.BoardError, pattern):
                board.parse_board_page(board_page([], None, field=field), 1)

    def test_a_page_without_nodes_or_page_info_stops_rather_than_reading_as_empty(self):
        good = json.loads(board_page([item(1, "Todo")], None))
        breakages = [lambda page: page["items"].pop("nodes"), lambda page: page["items"].update(nodes=None),
                     lambda page: page["items"].pop("pageInfo"),
                     lambda page: page["items"]["pageInfo"].pop("hasNextPage"),
                     lambda page: page["items"]["pageInfo"].update(hasNextPage=True, endCursor=None),
                     lambda page: page.pop("items")]
        for breakage in breakages:
            page = json.loads(json.dumps(good))
            breakage(page["data"]["repositoryOwner"]["projectV2"])
            with self.assertRaises(board.GhError):
                board.parse_board_page(json.dumps(page), 1)

    def test_fields_that_are_not_a_list_stop_rather_than_reading_as_a_renamed_status(self):
        for fields in (None, {"nodes": None}, {"nodes": "Status"}):
            page = json.loads(board_page([item(1, "Todo")], None))
            page["data"]["repositoryOwner"]["projectV2"]["fields"] = fields
            with self.assertRaisesRegex(board.GhError, "fields came back"):
                board.parse_board_page(json.dumps(page), 1)

    def test_status_options_without_an_id_or_two_of_one_name_stop(self):
        for options in ([*STATUS_FIELD["options"], {"id": "x", "name": "Todo"}],
                        [*STATUS_FIELD["options"], {"name": "Blocked"}], [*STATUS_FIELD["options"], {"id": "y"}]):
            with self.assertRaises(board.GhError):
                board.parse_board_page(board_page([], None, field=dict(STATUS_FIELD, options=options)), 1)

    def test_a_field_without_a_name_or_two_of_one_name_stop(self):
        for extra in ({"__typename": "ProjectV2Field"}, {"__typename": "ProjectV2Field", "name": "Status"}, "Status"):
            page = json.loads(board_page([item(1, "Todo")], None))
            page["data"]["repositoryOwner"]["projectV2"]["fields"]["nodes"].append(extra)
            with self.assertRaises(board.GhError):
                board.parse_board_page(json.dumps(page), 1)

    def test_an_item_without_its_archived_state_stops(self):
        page = json.loads(board_page([item(1, "Todo")], None))
        del page["data"]["repositoryOwner"]["projectV2"]["items"]["nodes"][0]["isArchived"]
        with self.assertRaisesRegex(board.GhError, "isArchived"):
            board.parse_board_page(json.dumps(page), 1)

    def test_graphql_errors_and_a_missing_board_are_reported(self):
        with self.assertRaises(board.GhError):
            board.parse_board_page('{"errors": [{"message": "bad"}], "data": null}', 1)
        with self.assertRaises(board.BoardError):
            board.parse_board_page(json.dumps({"data": {"repositoryOwner": {"__typename": "Organization",
                                                                             "projectV2": None}}}), 7)

    def test_every_page_is_read(self):
        gh = FakeGh(items=[item(number, "Todo") for number in range(1, 6)], page_size=2)
        self.assertEqual([entry["content"]["number"] for entry in make_board(gh).items()], [1, 2, 3, 4, 5])
        self.assertEqual(gh.kinds().count("board"), 3)

    def test_a_page_cursor_that_does_not_advance_is_an_error_not_a_loop(self):
        class Stuck(FakeGh):
            def run(self, *args, input=None):
                if self.kind(args) == "board":
                    self.calls.append((args, input))
                    return board_page([item(1, "Todo")], "same")
                return super().run(*args, input=input)

        with self.assertRaisesRegex(board.GhError, "did not advance"):
            make_board(Stuck()).items()

    def test_a_mutation_must_answer_with_the_item_it_changed(self):
        self.assertEqual(board.mutation_id('{"data": {"a": {"b": {"id": "X"}}}}', "a", "b", "id"), "X")
        for answer in ('{"data": {"a": null}}', '{"data": {"a": {"b": {"id": ""}}}}',
                       '{"errors": [{"message": "no"}], "data": null}', '[]'):
            with self.assertRaises(board.GhError):
                board.mutation_id(answer, "a", "b", "id")

    def test_setting_status_refuses_an_answer_for_another_item(self):
        class Elsewhere(FakeGh):
            def run(self, *args, input=None):
                if self.kind(args) == "set-status":
                    return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_x"}}}})
                return super().run(*args, input=input)

        gh = Elsewhere(items=[item(1, "Todo")], issues=[issue(1)])
        with self.assertRaisesRegex(board.GhError, "not 'PVTI_1'"):
            make_board(gh).set_status("PVTI_1", "Done")


class Ready(unittest.TestCase):
    def ready_numbers(self, items, issues, priority_of=None) -> list:
        return [entry["number"] for entry in board.ready(items, issues, REPO, PRIORITIES, priority_of or {})]

    def test_only_open_todo_issues_of_this_repository(self):
        items = [item(1, "Todo"), item(2, None), item(3, "Triage"), item(4, "In Progress"), item(5, "Done"),
                 item(6, "Todo"), item(7, "Todo", repo="o/other"), item(8, "Todo", kind="DraftIssue")]
        issues = [issue(number) for number in (1, 2, 3, 4, 5, 7, 8)]  # 6 is closed
        self.assertEqual(self.ready_numbers(items, issues), [1])

    def test_an_item_without_status_counts_as_triage(self):
        self.assertEqual(board.status_of(item(2, None)), "Triage")
        self.assertEqual(board.status_of(item(2, "Todo")), "Todo")

    def test_priority_then_age_orders_the_list(self):
        items = [item(number, "Todo") for number in (1, 2, 3, 4, 5)]
        issues = [issue(1, "2026-01-01"), issue(2, "2026-03-01"), issue(3, "2026-05-01"), issue(4, "2026-02-01"),
                  issue(5, "2026-06-01")]
        priority_of = {1: "Low", 2: "", 3: "Urgent", 4: "Medium", 5: "High"}
        # 2 has no Priority, so it counts as Medium, the middle option; 4 is the older of the two Mediums.
        self.assertEqual(self.ready_numbers(items, issues, priority_of), [3, 5, 4, 2, 1])

    def test_the_order_comes_from_the_ranking_given_not_the_names(self):
        items, issues = [item(1, "Todo"), item(2, "Todo")], [issue(1), issue(2)]
        entries = board.ready(items, issues, REPO, ("B", "A"), {1: "A", 2: "B"})
        self.assertEqual([entry["number"] for entry in entries], [2, 1])

    def test_an_open_blocker_in_the_repository_holds_an_issue_back(self):
        items = [item(1, "Todo"), item(2, "Todo")]
        self.assertEqual(self.ready_numbers(items, [issue(1, blocked_by=[{"number": 2}]), issue(2)]), [2])

    def test_a_closed_blocker_does_not(self):
        self.assertEqual(self.ready_numbers([item(1, "Todo")], [issue(1, blocked_by=[{"number": 2}])]), [1])
        closed = [issue(1, blocked_by=[{"number": 2, "state": "CLOSED"}])]
        self.assertEqual(self.ready_numbers([item(1, "Todo")], closed), [1])

    def test_a_blocker_whose_state_says_open_holds_it_back(self):
        blocked = [issue(1, blocked_by=[{"number": 2, "state": "OPEN"}])]
        self.assertEqual(self.ready_numbers([item(1, "Todo")], blocked), [])

    def test_a_blocker_in_another_repository_without_state_counts_as_open(self):
        elsewhere = [issue(1, blocked_by=[{"number": 2, "url": "https://github.com/o/other/issues/2"}])]
        self.assertEqual(self.ready_numbers([item(1, "Todo")], elsewhere), [])

    def test_a_blocker_in_an_unknown_state_stops_rather_than_counting_as_closed(self):
        for state in ("MERGED", "open-ish", "DRAFT"):
            with self.assertRaisesRegex(board.GhError, "unknown state"):
                self.ready_numbers([item(1, "Todo")], [issue(1, blocked_by=[{"number": 2, "state": state}])])

    def test_blockers_missing_or_of_another_shape_stop_rather_than_reading_as_none(self):
        missing = {"number": 1, "title": "x", "createdAt": "2026-10-01T00:00:00Z"}
        for broken in (missing, issue(1, blocked_by="2"), dict(issue(1), blockedBy={"nodes": None}),
                       dict(issue(1), blockedBy=None)):
            with self.assertRaises(board.GhError):
                self.ready_numbers([item(1, "Todo")], [broken])

    def test_blockers_given_as_graphql_nodes(self):
        nodes = [issue(1, blocked_by={"nodes": [{"number": 2, "state": "OPEN"}]})]
        self.assertEqual(self.ready_numbers([item(1, "Todo")], nodes), [])

    def test_the_board_reads_priorities_only_for_ready_candidates(self):
        gh = FakeGh(items=[item(1, "Todo"), item(2, None), item(3, "Todo")], issues=[issue(1), issue(2), issue(3)],
                    priorities={1: "Low", 3: "Urgent"})
        self.assertEqual([(entry["number"], entry["priority"]) for entry in make_board(gh).ready()],
                         [(3, "Urgent"), (1, "Low")])
        reads = [args[-1] for args, _ in gh.calls if gh.kind(args) == "priority-read"]
        self.assertEqual(sorted(reads), ["repos/o/r/issues/1/issue-field-values",
                                         "repos/o/r/issues/3/issue-field-values"])

    def test_every_rest_call_names_the_pinned_version(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).ready()
        make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)
        make_board(gh).check()
        rest = [args for args, _ in gh.calls if args[0] == "api" and args[1] != "graphql"]
        self.assertIn("user", [args[-1] for args in rest])
        self.assertTrue(rest)
        self.assertTrue(all(args[1:3] == ("-H", "X-GitHub-Api-Version: 2022-11-28") for args in rest), rest)


class ClaimHolder(unittest.TestCase):
    def test_the_earliest_claim_holds(self):
        comments = [comment("task-board claim: feature/b", "10:05"),
                    comment("task-board claim: feature/a in ../r-a", "10:00")]
        self.assertEqual(board.claim_holder(comments, "me"), "feature/a")

    def test_a_release_or_done_ends_a_claim(self):
        claim = comment("task-board claim: feature/a", "10:00")
        for ending in ("task-board release: stopped", "task-board done: merged abc123"):
            comments = [claim, comment(ending, "11:00")]
            self.assertIsNone(board.claim_holder(comments, "me"))
        later = comments + [comment("task-board claim: feature/c", "12:00")]
        self.assertEqual(board.claim_holder(later, "me"), "feature/c")

    def test_an_own_comment_without_a_timestamp_stops_rather_than_sorting_first(self):
        undated = {"body": "task-board claim: feature/b", "author": {"login": "me"}}
        with self.assertRaises(board.GhError):
            board.claim_holder([comment("task-board claim: feature/a", "10:00"), undated], "me")
        stranger = {"body": "task-board claim: feature/b", "author": {"login": "stranger"}}
        self.assertEqual(board.claim_holder([comment("task-board claim: feature/a", "10:00"), stranger], "me"),
                         "feature/a")

    def test_ordinary_comments_are_ignored(self):
        self.assertIsNone(board.claim_holder([comment("looks good", "10:00")], "me"))

    def test_a_strangers_earlier_claim_does_not_count(self):
        comments = [comment("task-board claim: feature/spoof", "09:00", login="stranger"),
                    comment("task-board claim: feature/a", "10:00")]
        self.assertEqual(board.claim_holder(comments, "me"), "feature/a")

    def test_a_strangers_release_does_not_end_a_claim(self):
        comments = [comment("task-board claim: feature/a", "10:00"),
                    comment("task-board release: hijack", "11:00", login="stranger"),
                    comment("task-board claim: feature/b", "12:00")]
        self.assertEqual(board.claim_holder(comments, "me"), "feature/a")


class Steps(unittest.TestCase):
    def test_no_step_uses_a_gh_project_subcommand(self):
        gh = FakeGh(items=[item(1, "Todo"), item(2, None)], issues=[issue(1), issue(2)], comments={})
        work = make_board(gh)
        work.ready()
        work.claim(1, "feature/x", None)
        work.queue(2, None)
        work.file("x", "", todo=True, priority=None, blocked_by=None)
        self.assertFalse(any(args[0] == "project" for args, _ in gh.calls))

    def test_claim_comments_first_then_moves_to_in_progress(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).claim(1, "feature/x", "../r-x")
        self.assertEqual(gh.edits(), ["In Progress"])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board claim: feature/x in ../r-x")
        self.assertLess(gh.first("comment"), gh.first("set-status"))

    def test_a_claim_whose_status_change_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], fail_once_on="set-status")
        with self.assertRaises(board.GhError):
            make_board(gh).claim(1, "feature/x", None)
        make_board(gh).claim(1, "feature/x", None)
        self.assertEqual(board.status_of(gh.items[0]), "In Progress")

    def test_claim_backs_off_when_another_session_claimed_first(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], comments={1: [claimed("feature/other", "11:00")]})
        with self.assertRaisesRegex(board.Refused, "feature/other"):
            make_board(gh).claim(1, "feature/x", None)
        self.assertEqual(gh.edits(), [])

    def test_claim_is_not_blocked_by_a_strangers_claim_comment(self):
        spoof = comment("task-board claim: feature/spoof", "11:00", login="stranger")
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], comments={1: [spoof]})
        make_board(gh).claim(1, "feature/x", None)
        self.assertEqual(gh.edits(), ["In Progress"])

    def test_claim_refuses_work_that_is_not_ready_and_changes_nothing(self):
        for status in (None, "Triage", "In Progress"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            with self.assertRaises(board.Refused):
                make_board(gh).claim(1, "feature/x", None)
            self.assertEqual(gh.edits(), [])
            self.assertNotIn(1, gh.comments)

    def test_file_into_todo_adds_by_node_then_sets_priority_then_status(self):
        gh = FakeGh()
        number = make_board(gh).file("New task", "", todo=True, priority=None, blocked_by="4")
        self.assertEqual(number, 9)
        create = next(args for args, _ in gh.calls if gh.kind(args) == "issue-create")
        self.assertEqual(create[create.index("--blocked-by") + 1], "4")
        add = next(args for args, _ in gh.calls if gh.kind(args) == "add-item")
        self.assertEqual(variables(add)["content"], "I_9")
        self.assertEqual(gh.priority_writes(), [(9, "Medium")])
        self.assertLess(gh.first("add-item"), gh.first("priority-write"))
        self.assertLess(gh.first("priority-write"), gh.first("set-status"))
        self.assertEqual(gh.edits(), ["Todo"])

    def test_file_into_triage_sets_no_priority(self):
        gh = FakeGh()
        make_board(gh).file("Follow-up", "found while fixing #3", todo=False, priority=None, blocked_by=None)
        self.assertEqual(gh.edits(), ["Triage"])
        self.assertEqual(gh.priority_writes(), [])

    def test_file_checks_the_board_before_creating_the_issue(self):
        for broken in ("board", "issue-fields"):
            gh = FakeGh(fail_on=broken)
            with self.assertRaises(board.GhError):
                make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)
            self.assertNotIn("issue-create", gh.kinds())

    def test_file_names_the_created_issue_when_placing_it_fails(self):
        for broken in ("issue-node", "add-item", "priority-write", "set-status"):
            gh = FakeGh(fail_on=broken)
            with self.assertRaisesRegex(board.GhError, "#9 was created"):
                make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)

    def test_file_refuses_output_without_this_repositorys_issue_url(self):
        for output in ("", "Creating issue…\n", "https://github.com/o/other/issues/9\n"):
            gh = FakeGh(create_output=output)
            with self.assertRaises(board.GhError):
                make_board(gh).file("x", "", todo=False, priority=None, blocked_by=None)
            self.assertNotIn("add-item", gh.kinds())

    def test_file_takes_the_existing_item_when_auto_add_placed_the_issue_first(self):
        gh = FakeGh(add_conflict=True)
        self.assertEqual(make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None), 9)
        self.assertEqual(gh.priority_writes(), [(9, "Medium")])
        self.assertEqual(gh.edits(), ["Todo"])
        self.assertEqual(board.status_of(gh.items[-1]), "Todo")

    def test_already_on_the_board_with_no_item_there_is_still_an_error(self):
        class Phantom(FakeGh):
            def run(self, *args, input=None):
                if self.kind(args) == "add-item":
                    self.calls.append((args, input))
                    raise board.GhError(f"gh: {board.ALREADY_ON_BOARD}")
                return super().run(*args, input=input)

        with self.assertRaisesRegex(board.GhError, "#9 was created.*no item for it"):
            make_board(Phantom()).file("x", "", todo=False, priority=None, blocked_by=None)

    def test_file_after_a_rename_places_the_issue_and_says_to_update_the_config(self):
        gh = FakeGh(create_output="https://github.com/o/renamed/issues/9\n", canonical="o/renamed")
        work = make_board(gh)
        self.assertEqual(work.file("x", "", todo=False, priority=None, blocked_by=None), 9)
        self.assertEqual(gh.edits(), ["Triage"])
        self.assertEqual(work.config.repo, "o/renamed")
        self.assertTrue(any("o/renamed" in warning for warning in work.warnings), work.warnings)

    def test_sync_puts_open_issues_missing_from_the_board_in_triage(self):
        gh = FakeGh(items=[item(1, "Todo"), item(2, None, repo="o/other")], issues=[issue(1), issue(2), issue(3)])
        self.assertEqual(make_board(gh).sync(), [2, 3])
        self.assertEqual(gh.edits(), [])
        added = [entry for entry in gh.items if entry["id"] in ("PVTI_2", "PVTI_3")]
        self.assertEqual([board.status_of(entry) for entry in added], ["Triage", "Triage"])

    def test_sync_on_a_complete_board_changes_nothing(self):
        gh = FakeGh(items=[item(1, "Todo"), item(2, "Done")], issues=[issue(1)])
        self.assertEqual(make_board(gh).sync(), [])
        self.assertNotIn("add-item", gh.kinds())

    def test_sync_leaves_an_issue_whose_item_was_archived_and_ready_skips_it(self):
        gh = FakeGh(items=[item(1, "Todo", archived=True)], issues=[issue(1)])
        self.assertEqual(make_board(gh).sync(), [])
        self.assertEqual(make_board(gh).ready(), [])

    def test_steps_that_add_items_refuse_while_item_added_is_on_and_change_nothing(self):
        gh = FakeGh(items=[], issues=[issue(1)], workflows=NEW_BOARD_WORKFLOWS)
        with self.assertRaisesRegex(board.BoardError, "Item added to project"):
            make_board(gh).sync()
        with self.assertRaisesRegex(board.BoardError, "Item added to project"):
            make_board(gh).file("x", "", todo=False, priority=None, blocked_by=None)
        self.assertFalse({"add-item", "issue-create"} & set(gh.kinds()))

    def test_sync_survives_auto_add_placing_the_same_issue(self):
        gh = FakeGh(items=[], issues=[issue(4)], add_conflict=True)
        self.assertEqual(make_board(gh).sync(), [4])

    def test_queue_accepts_a_triage_item_with_a_priority(self):
        for status in (None, "Triage"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            make_board(gh).queue(1, "Urgent")
            self.assertEqual(gh.priority_writes(), [(1, "Urgent")])
            self.assertEqual(gh.edits(), ["Todo"])

    def test_queue_refuses_an_item_already_past_triage(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)])
        with self.assertRaises(board.Refused):
            make_board(gh).queue(1, None)
        self.assertEqual((gh.edits(), gh.priority_writes()), ([], []))

    def test_queue_refuses_a_closed_or_claimed_issue_even_with_a_blank_status(self):
        for issues, comments in (([], {}), ([issue(1)], {1: [claimed()]})):
            gh = FakeGh(items=[item(1, None)], issues=issues, comments=comments)
            with self.assertRaises(board.Refused):
                make_board(gh).queue(1, None)
            self.assertEqual((gh.edits(), gh.priority_writes()), ([], []))

    def test_a_priority_that_does_not_exist_is_refused_before_anything_changes(self):
        gh = FakeGh(items=[item(1, None)], issues=[issue(1)])
        with self.assertRaisesRegex(board.BoardError, "Urgent"):
            make_board(gh).queue(1, "P1")
        with self.assertRaises(board.BoardError):
            make_board(gh).file("x", "", todo=True, priority="P1", blocked_by=None)
        self.assertEqual((gh.edits(), gh.priority_writes()), ([], []))
        self.assertNotIn("issue-create", gh.kinds())

    def test_done_closes_first_then_sets_done(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]})
        make_board(gh).done(1, "feature/x", "merged abc123 into develop; tests green")
        self.assertEqual(gh.edits(), ["Done"])
        self.assertLess(gh.first("issue-close"), gh.first("set-status"))
        close = next(args for args, _ in gh.calls if gh.kind(args) == "issue-close")
        self.assertEqual(close[close.index("--comment") + 1],
                         "task-board done: feature/x: merged abc123 into develop; tests green")

    def test_a_done_whose_status_change_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on="set-status")
        with self.assertRaises(board.GhError):
            make_board(gh).done(1, "feature/x", "merged abc123")
        make_board(gh).done(1, "feature/x", "merged abc123")
        self.assertEqual(board.status_of(gh.items[0]), "Done")
        self.assertEqual(gh.kinds().count("issue-close"), 1)

    def test_a_done_rerun_is_only_for_the_branch_that_closed_it(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on="set-status")
        with self.assertRaises(board.GhError):
            make_board(gh).done(1, "feature/x", "merged abc123")
        with self.assertRaises(board.Refused):
            make_board(gh).done(1, "feature/other", "x")

    def test_done_refuses_outside_in_progress_or_for_another_branch(self):
        cases = [("Todo", [claimed()], "feature/x"), ("In Progress", [claimed("feature/other")], "feature/x"),
                 ("In Progress", [], "feature/x")]
        for status, comments, branch in cases:
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)], comments={1: comments})
            with self.assertRaises(board.Refused):
                make_board(gh).done(1, branch, "x")
            self.assertNotIn("issue-close", gh.kinds())

    def test_release_returns_to_todo_with_a_reason(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]})
        make_board(gh).release(1, "feature/x", "blocked on the card data file")
        self.assertEqual(gh.edits(), ["Todo"])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board release: feature/x: blocked on the card data file")
        self.assertIsNone(board.claim_holder(gh.comments[1], "me"))

    def test_release_refuses_another_branchs_claim(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed("feature/other")]})
        with self.assertRaises(board.Refused):
            make_board(gh).release(1, "feature/x", "x")
        self.assertEqual(gh.edits(), [])

    def test_a_release_whose_comment_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on="comment")
        with self.assertRaises(board.GhError):
            make_board(gh).release(1, "feature/x", "stopping")
        make_board(gh).release(1, "feature/x", "stopping")
        self.assertIsNone(board.claim_holder(gh.comments[1], "me"))
        self.assertEqual(board.status_of(gh.items[0]), "Todo")


def users_board(**kwargs) -> board.Board:
    return board.Board(board.Config(owner="me", project=1, repo=REPO), FakeGh(owner_type="User", **kwargs))


class UsersBoard(unittest.TestCase):
    """A user has no issue fields, so on a user's board Priority is the board's own field (plan 0033)."""

    def test_an_organizations_board_ignores_the_issue_fields_value_on_its_items(self):
        page = board_page([item(1, "Todo")], None, priorities={1: "High"})
        field, items, _ = board.parse_board_page(page, 1)
        self.assertEqual((field.owner_type, field.board_priority, items[0]["priority"]), ("Organization", None, ""))

    def test_an_organizations_board_needs_no_priority_field_of_its_own(self):
        field, _, _ = board.parse_board_page(board_page([item(1, "Todo")], None, priority_field=None), 1)
        self.assertEqual(field.owner_type, "Organization")

    def test_no_query_asks_for_a_field_by_name(self):
        # GitHub answers `field(name:)` for a field the board lacks with an error, not null (measured 2026-10-30)
        for query in (board.BOARD_QUERY, board.WORKFLOWS_QUERY):
            self.assertNotIn("field(name:", query.replace(" ", ""))

    def test_a_users_board_ranks_its_own_priority_options_in_board_order(self):
        field, items, _ = board.parse_board_page(board_page([item(1, "Todo")], None, owner_type="User",
                                                            priorities={1: "Low"}), 1)
        self.assertEqual(field.board_priority.priorities, ("Urgent", "High", "Medium", "Low"))
        self.assertEqual(field.board_priority.default_priority(), "Medium")
        self.assertEqual(items[0]["priority"], "Low")

    def test_a_users_board_without_its_own_priority_field_is_named(self):
        for priority_field in (None, ORG_PRIORITY_ON_BOARD, dict(USER_PRIORITY_FIELD, options=[]),
                               dict(USER_PRIORITY_FIELD, isIssueField=True),
                               {"__typename": "ProjectV2Field", "id": "x", "isIssueField": False}):
            with self.assertRaisesRegex(board.BoardError, "Priority"):
                board.parse_board_page(board_page([], None, owner_type="User", priority_field=priority_field), 1)

    def test_a_users_item_priority_of_another_shape_or_outside_the_options_stops(self):
        page = json.loads(board_page([item(1, "Todo")], None, owner_type="User"))
        node = page["data"]["repositoryOwner"]["projectV2"]["items"]["nodes"][0]
        for value in ({"__typename": "ProjectV2ItemFieldTextValue", "text": "High"}, ORG_ITEM_PRIORITY,
                      {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": "Critical"}):
            node["priority"] = value
            with self.assertRaises(board.GhError):
                board.parse_board_page(json.dumps(page), 1)

    def test_an_owner_that_is_neither_an_organization_nor_a_user_stops(self):
        page = json.loads(board_page([], None))
        page["data"]["repositoryOwner"]["__typename"] = "Enterprise"
        with self.assertRaises(board.GhError):
            board.parse_board_page(json.dumps(page), 1)

    def test_ready_orders_by_the_boards_priority_without_the_rest_issue_fields(self):
        work = users_board(items=[item(1, "Todo"), item(2, "Todo"), item(3, "Todo")],
                           issues=[issue(1), issue(2), issue(3)], priorities={2: "Urgent", 3: "Low"})
        self.assertEqual([entry["number"] for entry in work.ready()], [2, 1, 3])
        self.assertEqual([entry["priority"] for entry in work.ready()], ["Urgent", "Medium", "Low"])
        self.assertFalse({"issue-fields", "priority-read", "priority-write"} & set(work.gh.kinds()))

    def test_file_writes_priority_on_the_boards_item_after_adding_it_and_before_the_status(self):
        work = users_board()
        work.file("x", "", todo=True, priority="High", blocked_by=None)
        self.assertEqual(work.gh.priority_writes(), [(9, "High")])
        self.assertLess(work.gh.first("add-item"), work.gh.first("set-priority"))
        self.assertLess(work.gh.first("set-priority"), work.gh.first("set-status"))
        self.assertEqual(work.gh.edits(), ["Todo"])

    def test_queue_writes_priority_on_the_boards_item(self):
        work = users_board(items=[item(5, None)], issues=[issue(5)])
        work.queue(5, None)
        self.assertEqual(work.gh.priority_writes(), [(5, "Medium")])
        self.assertEqual(work.gh.edits(), ["Todo"])

    def test_check_on_a_users_board_names_the_boards_own_field(self):
        lines = users_board(items=[item(1, "Todo")], issues=[issue(1)]).check()
        self.assertTrue(all(line.startswith("ok:") for line in lines), lines)
        self.assertIn("the board's own field", "\n".join(lines))


class Check(unittest.TestCase):
    def test_check_reads_everything_and_reports_ok(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], priorities={1: "High"})
        lines = make_board(gh).check()
        self.assertTrue(all(line.startswith("ok:") for line in lines), lines)
        self.assertIn("Urgent > High > Medium > Low", "\n".join(lines))
        self.assertEqual([], [args for args, _ in gh.calls if gh.kind(args) in ("set-status", "add-item",
                                                                                   "priority-write", "comment",
                                                                                   "issue-create", "issue-close")])

    def test_check_warns_when_the_pinned_version_is_marked_deprecated(self):
        lines = make_board(FakeGh(deprecated=True)).check()
        self.assertTrue(any(line.startswith("warn:") and "Sunset" in line for line in lines), lines)

    def test_check_fails_when_the_pinned_version_is_no_longer_listed(self):
        with self.assertRaisesRegex(board.GhError, "no longer lists"):
            make_board(FakeGh(versions=("2026-03-10",))).check()

    def test_check_fails_while_a_workflow_sets_a_status_on_every_item_added(self):
        with self.assertRaisesRegex(board.BoardError, "Item added to project"):
            make_board(FakeGh(workflows=NEW_BOARD_WORKFLOWS)).check()
        lines = make_board(FakeGh(workflows=[("Item added to project", False), ("Item closed", True)])).check()
        self.assertTrue(all(line.startswith("ok:") for line in lines), lines)

    def test_workflows_of_another_shape_stop_rather_than_reading_as_none(self):
        for answer in ({"data": {"repositoryOwner": {"projectV2": None}}},
                       {"data": {"repositoryOwner": {"projectV2": {"workflows": {"nodes": [{"name": "x"}]}}}}}):
            with self.assertRaises(board.GhError):
                board.enabled_workflows(json.dumps(answer))

    def test_check_fails_while_the_config_names_a_renamed_repository(self):
        with self.assertRaisesRegex(board.BoardError, "now calls o/renamed"):
            make_board(FakeGh(canonical="o/renamed")).check()

    def test_check_fails_on_a_shape_the_steps_could_not_use(self):
        class Garbled(FakeGh):
            def run(self, *args, input=None):
                if self.kind(args) == "priority-read":
                    return json.dumps([{"issue_field_id": PRIORITY_FIELD_ID, "value": "High"}])
                return super().run(*args, input=input)

        with self.assertRaises(board.GhError):
            make_board(Garbled(items=[item(1, "Todo")], issues=[issue(1)])).check()

    def test_headers_of_gh_api_i(self):
        headers = board.parse_headers("HTTP/2.0 200 OK\r\nDeprecation: @1\r\nSunset: then\r\n\r\n{\"a\": 1}")
        self.assertEqual(headers, {"deprecation": "@1", "sunset": "then"})


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / ".git").mkdir()
        (self.folder / ".task-board.json").write_text('{"owner": "o", "project": 1, "repo": "o/r"}')

    def test_exit_status_per_outcome(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        self.assertEqual(board.main(["ready"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["check"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["sync"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["done", "1", "--branch", "feature/x", "--evidence", "x"], gh=gh,
                                    cwd=self.folder), 3)
        self.assertEqual(board.main(["ready"], gh=FakeGh(fail_on="board"), cwd=self.folder), 2)
        empty = Path(tempfile.mkdtemp())
        (empty / ".git").mkdir()
        self.assertEqual(board.main(["ready"], gh=gh, cwd=empty), 1)

    def test_unexpected_gh_output_exits_2_not_with_a_traceback(self):
        class Garbled(FakeGh):
            def run(self, *args, input=None):
                return "not json" if self.kind(args) == "board" else super().run(*args, input=input)

        self.assertEqual(board.main(["ready"], gh=Garbled(), cwd=self.folder), 2)

    def test_a_missing_gh_is_gh_failing_not_a_traceback(self):
        with self.assertRaisesRegex(board.GhError, "could not run"):
            board.Gh("gh-that-does-not-exist-here").run("api", "user")

    def test_a_request_body_reaches_gh_on_stdin(self):
        echoed = board.Gh("cat").run(input='{"issue_field_values": []}')
        self.assertEqual(json.loads(echoed), {"issue_field_values": []})

    def test_release_and_done_need_a_branch(self):
        for argv in (["release", "1", "--reason", "x"], ["done", "1", "--evidence", "x"]):
            with self.assertRaises(SystemExit):
                board.parse_args(argv)

    def test_priority_is_refused_with_triage(self):
        with self.assertRaises(SystemExit):
            board.parse_args(["file", "--triage", "--priority", "High", "--title", "x"])

    def test_the_config_is_found_from_a_subfolder_but_not_above_the_repository(self):
        sub = self.folder / "src" / "deep"
        sub.mkdir(parents=True)
        self.assertEqual(board.find_config(sub), self.folder / ".task-board.json")
        nested = self.folder / "vendor"
        (nested / ".git").mkdir(parents=True)
        with self.assertRaises(board.BoardError):
            board.find_config(nested)


DECIDE_ARGS = (["A|fix the two rules first|about half a day", "B|predict now|140 of 900 moves left out"],
               "A|the full logs exist to find such gaps")
JOB_URL = "https://github.com/o/r/issues/9\n"


def typed(text: str, at: str = "2026-11-01T01:00:00Z", kind: str = "human") -> dict:
    """A transcript record of a message, as Claude Code writes it."""
    return {"type": "user", "timestamp": at, "origin": {"kind": kind}, "message": {"content": text}}


def job_body(data: dict) -> str:
    import jobs
    return jobs.render_body(data)


class JobsAndPage(unittest.TestCase):
    """The steps of plan 0036: ask, answer, job-state, progress, note, and the page they redraw."""

    def asked(self, **given):
        """A board with work #3 in Todo, and the decision job #9 filed holding it up."""
        gh = FakeGh(items=[item(3, "Todo")], issues=[dict(issue(3), body="", url="https://github.com/o/r/issues/3")],
                    create_output=JOB_URL, **given)
        made = make_board(gh)
        options, recommend = DECIDE_ARGS
        self.assertEqual(made.ask("decide", "fix two engine rules first?", options, recommend, None, [3], ""), 9)
        return gh, made

    def test_ask_files_the_job_in_todo_and_holds_its_work_up(self):
        gh, made = self.asked()
        self.assertEqual(gh.edits(), ["Todo"])
        self.assertEqual(gh.kinds().count("issue-edit"), 1)
        job = next(entry for entry in gh.issues if entry["number"] == 9)
        data, error = board.block_of(job)
        self.assertEqual((data["kind"], error), ("decide", None))
        self.assertEqual(made.ready(), [], "neither the job nor the work it holds up is ready work")

    def test_ask_refuses_bad_lines_and_closed_holds_before_creating_anything(self):
        options, recommend = DECIDE_ARGS
        cases = ((("decide", "fix E193 first?", options, recommend, None, [3]), board.BoardError, "plain explanation"),
                 (("decide", "t", options[:1], recommend, None, [3]), board.BoardError, "2 to 3 options"),
                 (("decide", "t", options, recommend, "a summary", [3]), board.BoardError, "not --summary"),
                 (("approve", "t", options, None, "s", [3]), board.BoardError, "not --option"),
                 (("approve", "merge it", [], None, "checks green", [77]), board.Refused, "#77"))
        for args, error, why in cases:
            gh = FakeGh(items=[item(3, "Todo")], issues=[issue(3)], create_output=JOB_URL)
            with self.subTest(why=why), self.assertRaisesRegex(error, why):
                make_board(gh).ask(*args, "")
            self.assertNotIn("issue-create", gh.kinds())

    def test_answer_closes_the_job_on_the_users_typed_words_and_frees_the_work(self):
        gh, made = self.asked()
        self.assertEqual(made.answer(9, "#9 a", [typed("ok, #9 a")]), "A")
        self.assertIn("issue-close", gh.kinds())
        closing = [a for a, _ in gh.calls if gh.kind(a) == "issue-close"][0]
        self.assertTrue(closing[closing.index("--comment") + 1].startswith(f"{board.ANSWER_MARK} A — the user's"))
        self.assertEqual(gh.edits()[-1], "Done")
        self.assertEqual([entry["number"] for entry in made.ready()], [3])
        self.assertEqual(made.job_state(9), {"number": 9, "kind": "decide", "state": "closed", "answer": "A"})

    def test_answer_refuses_words_that_are_not_the_users_and_changes_nothing(self):
        for records, quote, why in (([typed("#9 A", kind="peer")], "#9 A", "not in any message"),
                                    ([typed("#9 C")], "#9 C", "not an answer #9 declares"),
                                    ([typed("#9 A", at="2026-10-31T23:00:00Z")], "#9 A", "not in any message")):
            gh, made = self.asked()
            with self.subTest(why=why), self.assertRaisesRegex(board.Refused, why):
                made.answer(9, quote, records)
            self.assertNotIn("issue-close", gh.kinds())

    def test_answer_refuses_an_issue_that_is_not_a_job(self):
        gh = FakeGh(items=[item(3, "Todo")], issues=[dict(issue(3), body="just work")])
        with self.assertRaisesRegex(board.Refused, "not a job"):
            make_board(gh).answer(3, "#3 A", [typed("#3 A")])
        broken = FakeGh(items=[item(4, "Todo")], issues=[dict(issue(4), body=board.jobs.BLOCK_START + "\n{")])
        with self.assertRaisesRegex(board.Refused, "not closed"):
            make_board(broken).answer(4, "#4 A", [typed("#4 A")])

    def test_answer_rerun_after_closing_finishes_and_a_job_closed_without_answer_is_refused(self):
        gh, made = self.asked()
        gh.fail_once_on = None
        made.answer(9, "#9 A", [typed("#9 A")])
        self.assertEqual(made.answer(9, "#9 A", []), "A")
        gh2, made2 = self.asked()
        gh2.closed += [entry for entry in gh2.issues if entry["number"] == 9]
        gh2.issues = [entry for entry in gh2.issues if entry["number"] != 9]
        with self.assertRaisesRegex(board.Refused, "no answer recorded"):
            made2.answer(9, "#9 A", [typed("#9 A")])

    def test_progress_is_the_claim_holders_and_checks_its_lines(self):
        gh = FakeGh(items=[item(3, "In Progress")], issues=[dict(issue(3), body="The plan: x.md")],
                    comments={3: [claimed("feature/x")]})
        made = make_board(gh)
        values = {"goal": "the simulator matches", "step": 2, "of": 4, "now": "fixing", "next": "predicting"}
        made.progress(3, "feature/x", values)
        body = next(entry for entry in gh.issues if entry["number"] == 3)["body"]
        self.assertTrue(body.startswith("The plan: x.md"))
        self.assertEqual(board.block_of({"body": body})[0]["step"], 2)
        with self.assertRaisesRegex(board.Refused, "claimed by 'feature/x'"):
            made.progress(3, "feature/y", values)
        with self.assertRaisesRegex(board.BoardError, "whole numbers"):
            made.progress(3, "feature/x", dict(values, step=5))

    def test_every_new_step_runs_from_the_command_line(self):
        gh = FakeGh(items=[item(3, "In Progress")], issues=[dict(issue(3), body="")],
                    comments={3: [claimed("feature/x")]}, create_output=JOB_URL)
        folder = Path(tempfile.mkdtemp())
        (folder / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": REPO,
                                                             "page": "coord/board.md"}))
        config = folder / "claude-config"  # the transcript `answer` reads, found through CLAUDE_CONFIG_DIR
        (config / "projects" / "-x").mkdir(parents=True)
        (config / "projects" / "-x" / "s1.jsonl").write_text(json.dumps(typed("#9 approve")) + "\n")
        environ = {"CLAUDE_CODE_SESSION_ID": "s1", "CLAUDE_CONFIG_DIR": str(config)}
        paths, now = (folder, folder / ".git" / "task-board"), board.jobs.utc("2026-11-01T03:00:00Z")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codes = [board.main(argv, gh=gh, cwd=folder, environ=environ, now=now, paths=paths) for argv in (
                ["progress", "3", "--branch", "feature/x", "--goal", "g", "--step", "2", "--of", "4", "--now", "n",
                 "--next", "x"],
                ["ask", "--kind", "approve", "--title", "merge it", "--summary", "checks green"],
                ["job-state", "9", "--json"],
                ["note", "3", "--decided", "--text", "a call"],
                ["answer", "9", "--quote", "#9 approve"],
                ["page"])]
        self.assertEqual(codes, [0, 0, 0, 0, 0, 0], out.getvalue())
        self.assertIn("#3: step 2 of 4", out.getvalue())
        self.assertIn("answered #9: approve", out.getvalue())
        self.assertEqual(board.block_of(next(e for e in gh.issues if e["number"] == 3))[0]["step"], 2)
        self.assertIn("## In progress (1)", (folder / "coord" / "board.md").read_text())

    def test_note_marks_a_comment_on_an_open_issue_only(self):
        gh = FakeGh(items=[item(3, "Todo")], issues=[issue(3)])
        made = make_board(gh)
        made.note(3, "decided", "left 10 one-move decisions out: they cannot tell models apart")
        self.assertTrue(gh.comments[3][-1]["body"].startswith(board.NOTE_MARKS["decided"]))
        for number, text, error in ((4, "x", board.Refused), (3, "see C290", board.BoardError)):
            with self.subTest(text=text), self.assertRaises(error):
                made.note(number, "finding", text)

    def test_the_page_shows_jobs_work_and_what_happened_since(self):
        gh, made = self.asked()
        gh.items.append(item(5, "In Progress"))
        work = {"kind": "work", "goal": "the simulator matches", "step": 2, "of": 4, "now": "fixing", "next": "x"}
        gh.issues.append(dict(issue(5, blocked_by=[{"number": 9, "state": "OPEN"}]), body=job_body(work),
                              url="https://github.com/o/r/issues/5"))
        gh.comments[5] = [comment(f"{board.NOTE_MARKS['finding']} a rounding difference", "02:00"),
                          comment(f"{board.NOTE_MARKS['finding']} old news", "00:30"),
                          comment(f"{board.NOTE_MARKS['decided']} a stranger's", "02:00", login="stranger")]
        since = board.jobs.utc("2026-10-29T01:00:00Z")
        page = made.page_text(board.jobs.utc("2026-11-01T03:00:00Z"), since, ["## Goals", "- one goal"])
        self.assertIn("## Needs you (1)", page)
        self.assertIn("| [#9](https://github.com/o/r/issues/9) | decide | fix two engine rules first? |", page)
        self.assertIn("| [#3](https://github.com/o/r/issues/3), [#5](https://github.com/o/r/issues/5) |", page)
        self.assertIn("step 2 of 4: fixing. Next: x. Turn: yours.", page)
        self.assertIn("found: a rounding difference", page)
        self.assertNotIn("old news", page)
        self.assertNotIn("a stranger's", page)
        self.assertIn("## Goals", page)

    def test_a_step_redraws_the_page_and_a_failed_redraw_only_warns(self):
        folder = Path(tempfile.mkdtemp())
        root, state = folder / "repo", folder / "repo" / ".git" / "task-board"
        root.mkdir()
        (root / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": REPO,
                                                           "page": "coord/board.md"}))
        gh = FakeGh(items=[item(3, "Todo")], issues=[issue(3)])
        now = board.jobs.utc("2026-11-01T03:00:00Z")
        code = board.main(["note", "3", "--finding", "--text", "a finding"], gh=gh, cwd=root, now=now,
                          paths=(root, state))
        self.assertEqual(code, 0)
        drawn = (root / "coord" / "board.md").read_text()
        self.assertEqual(drawn, (state / "page.md").read_text())
        self.assertTrue(drawn.startswith("Updated "))
        gh.fail_on = "issue-search"
        code = board.main(["note", "3", "--finding", "--text", "another"], gh=gh, cwd=root, now=now,
                          paths=(root, state))
        self.assertEqual(code, 0)
        self.assertTrue((root / "coord" / "board.md").read_text().startswith("Out of date since "))
        self.assertEqual(board.main(["page"], gh=gh, cwd=root, now=now, paths=(root, state)), 2)

    def test_check_warns_about_malformed_blocks_and_restored_pages(self):
        gh = FakeGh(items=[item(3, "Todo")], issues=[dict(issue(3), body=board.jobs.BLOCK_START + "\n{")])
        lines = make_board(gh).check()
        self.assertTrue(any(line.startswith("warn: #3:") for line in lines), lines)
        state = Path(tempfile.mkdtemp())
        now = board.jobs.utc("2026-11-01T03:00:00Z")
        (state / "restores.log").write_text(f"{(now - timedelta(days=9)).isoformat()}\tFileChanged\tx\n"
                                            f"{(now - timedelta(hours=1)).isoformat()}\tPostToolUse\tx\n")
        self.assertIn("restored 1 time(s)", board.restore_warnings(state, now)[0])
        self.assertEqual(board.restore_warnings(Path(tempfile.mkdtemp()), now), [])

    def test_ready_warns_about_an_issue_left_out_for_a_malformed_block(self):
        gh = FakeGh(items=[item(3, "Todo"), item(4, "Todo")],
                    issues=[issue(3), dict(issue(4), body=board.jobs.BLOCK_START + "\n{")])
        made = make_board(gh)
        self.assertEqual([entry["number"] for entry in made.ready()], [3])
        self.assertTrue(any("#4 is left out" in warning for warning in made.warnings))

    def test_config_takes_a_page_its_blocks_and_an_id_pattern(self):
        config = board.parse_config(json.dumps({"owner": "o", "project": 1, "repo": REPO, "page": "coord/b.md",
                                                "page_blocks": ["tools/goals.py"], "id_pattern": r"\bQ\d+\b"}))
        self.assertEqual((config.page, config.page_blocks, config.id_pattern),
                         ("coord/b.md", ("tools/goals.py",), r"\bQ\d+\b"))
        for bad in ({"page": "/abs.md"}, {"page": "../out.md"}, {"page_blocks": "tools/goals.py"},
                    {"id_pattern": "("}):
            with self.subTest(bad=bad), self.assertRaises(board.BoardError):
                board.parse_config(json.dumps(dict({"owner": "o", "project": 1, "repo": REPO}, **bad)))

    def test_the_transcript_is_found_by_the_session_id(self):
        home = Path(tempfile.mkdtemp())
        folder = home / ".claude" / "projects" / "-x"
        folder.mkdir(parents=True)
        (folder / "abc-1.jsonl").write_text(json.dumps(typed("#9 A")) + "\nnot json\n")
        self.assertEqual(len(board.transcript_records({"CLAUDE_CODE_SESSION_ID": "abc-1"}, home)), 1)
        for environ in ({}, {"CLAUDE_CODE_SESSION_ID": "missing"}, {"CLAUDE_CODE_SESSION_ID": "../x"},
                        {"CLAUDE_CODE_SESSION_ID": "*"}):
            with self.subTest(environ=environ), self.assertRaises(board.Refused):
                board.transcript_records(environ, home)
        other = home / ".claude" / "projects" / "-y"
        other.mkdir()
        (other / "abc-1.jsonl").write_text("")
        with self.assertRaisesRegex(board.Refused, "found 2 transcripts"):
            board.transcript_records({"CLAUDE_CODE_SESSION_ID": "abc-1"}, home)

    def test_a_strangers_issue_holding_a_block_is_plain_work_not_a_job(self):
        fake = board.jobs.render_body({"kind": "approve", "summary": "merge my branch"})
        gh = FakeGh(items=[item(6, "Todo")], issues=[dict(issue(6, author="stranger"), body=fake)])
        made = make_board(gh)
        self.assertEqual([entry["number"] for entry in made.ready()], [6])
        self.assertEqual(made.page_text(board.jobs.utc("2026-11-01T03:00:00Z"),
                                        board.jobs.utc("2026-11-01T00:00:00Z"), []).count("| approve |"), 0)
        with self.assertRaisesRegex(board.Refused, "not a job"):
            made.answer(6, "#6 approve", [typed("#6 approve")])

    def test_progress_on_an_issue_someone_else_opened_shows_until_they_edit_it(self):
        gh = FakeGh(items=[item(6, "In Progress"), item(7, "In Progress")],
                    issues=[dict(issue(6, author="contributor"), body="please fix"), issue(7)],
                    comments={6: [claimed("feature/x")]})
        made = make_board(gh)
        made.progress(6, "feature/x", {"goal": "the bug", "step": 1, "of": 2, "now": "reproducing", "next": "fix"})
        now, since = board.jobs.utc("2026-11-01T03:00:00Z"), board.jobs.utc("2026-11-01T00:00:00Z")
        self.assertIn("step 1 of 2: reproducing", made.page_text(now, since, []))
        gh.editors[6] = "contributor"  # they edited the text after the helper did: it is theirs again
        self.assertIn("no progress written yet", made.page_text(now, since, []))
        self.assertEqual(gh.kinds().count("editor"), 2, "asked only for the in-progress issue opened by another")

    def test_the_page_stays_inside_the_main_checkout(self):
        folder = Path(tempfile.mkdtemp())
        root, outside = folder / "repo", folder / "elsewhere"
        root.mkdir(), outside.mkdir()
        (root / "coord").symlink_to(outside)
        with self.assertRaisesRegex(OSError, "outside"):
            board.write_page(root, root / ".git" / "task-board", "coord/board.md", "x")
        self.assertFalse((outside / "board.md").exists())

    def test_page_settings_come_from_the_main_checkouts_own_config(self):
        root = Path(tempfile.mkdtemp())
        (root / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": REPO,
                                                           "page": "coord/board.md"}))
        branch = board.Config("o", 1, REPO, page="coord/board.md", page_blocks=("sh", "-c", "anything"))
        mine = board.main_checkout_config(branch, root)
        self.assertEqual((mine.page, mine.page_blocks), ("coord/board.md", ()))
        self.assertIsNone(board.main_checkout_config(branch, None).page)

    def test_a_worktrees_own_page_settings_are_not_used(self):
        folder = Path(tempfile.mkdtemp())
        root, worktree = folder / "main", folder / "wt"
        for place, page in ((root, "coord/main.md"), (worktree, "coord/branch.md")):
            place.mkdir()
            (place / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": REPO,
                                                                "page": page}))
        gh = FakeGh(items=[item(3, "Todo")], issues=[issue(3)])
        board.main(["note", "3", "--finding", "--text", "a finding"], gh=gh, cwd=worktree,
                   now=board.jobs.utc("2026-11-01T03:00:00Z"), paths=(root, root / ".git" / "task-board"))
        self.assertTrue((root / "coord" / "main.md").exists())
        self.assertFalse((root / "coord" / "branch.md").exists())

    def test_page_blocks_print_lines_or_say_they_failed(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual(board.run_blocks(root, ("printf", "## Goals\\n- one\\n")), ["## Goals", "- one"])
        self.assertIn("failed (exit 1)", board.run_blocks(root, ("false",))[0])
        self.assertIn("could not run", board.run_blocks(root, ("/no/such/command",))[0])
        many = board.run_blocks(root, ("seq", "40"))
        self.assertEqual(len(many), board.BLOCKS_MAX_LINES + 1)


def closed_local_port() -> int:
    """A local port with nothing listening: one the system just handed out and took back, then confirmed refused,
    so the replay's requests, dummy token included, reach no one."""
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    except PermissionError:  # a sandbox that forbids local binding; the connect check below still decides
        port = 9
    with socket.socket() as check:
        check.settimeout(2)
        try:
            check.connect(("127.0.0.1", port))
        except OSError:  # refused, or not permitted inside a sandbox: either way, nothing will receive the requests
            return port
    raise unittest.SkipTest(f"something is listening on 127.0.0.1:{port}; not replaying commands into it")


@unittest.skipUnless(shutil.which("gh"), "gh is not installed")
class ZzRealGhAcceptsEveryCommand(unittest.TestCase):
    """Runs the real gh on every distinct command the tests above produced, with its host pointed at a local port
    confirmed closed and a dummy token. gh checks flags, argument combinations and --json field names before it opens a
    connection, so each command must get as far as dialling the port; a refusal before that fails here. Named Zz… to run
    last (unittest runs classes alphabetically), after the other tests have recorded their calls."""

    def test_zz_gh_parses_every_command_the_helper_issues(self):
        if not RECORDED:
            self.skipTest("no commands recorded")
        folder = tempfile.mkdtemp()
        port = closed_local_port()
        env = dict(os.environ, GH_HOST=f"127.0.0.1:{port}", GH_ENTERPRISE_TOKEN="dummy", GH_TOKEN="dummy",
                   GH_CONFIG_DIR=folder, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
        seen, failures = set(), []
        for args, given in RECORDED:
            shape = tuple(re.sub(r"\d+", "N", arg) for arg in args)
            if shape in seen:
                continue
            seen.add(shape)
            result = subprocess.run(["gh", *args], input=given or "", capture_output=True, text=True, env=env,
                                    timeout=30)
            if "dial tcp" not in result.stderr:
                failures.append(f"gh {' '.join(args)[:120]}\n    -> {result.stderr.strip()[:200]}")
        self.assertGreater(len(seen), 10)
        self.assertEqual(failures, [], "\n".join(failures))
