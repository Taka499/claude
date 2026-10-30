"""Tests for board.py. Run: python3 -m unittest discover -s skills/task-board

The fixtures marked "captured" are trimmed from real gh output against the tia-tools board on 2026-10-29 (plan 0031).
The GraphQL shapes follow GitHub's public schema, checked the same day. The last class runs the real gh binary on
every command the other tests produced, offline, so an argument gh refuses fails here and not on a real board."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
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


def item(number: int, status: str | None, repo: str = REPO, kind: str = "Issue") -> dict:
    """A board item as parse_board_page returns it."""
    return {"id": f"PVTI_{number}", "status": status or "",
            "content": {"type": kind, "number": number, "title": f"issue {number}",
                        "url": f"https://github.com/{repo}/issues/{number}", "repository": repo}}


def issue(number: int, created: str = "2026-10-01T00:00:00Z", blocked_by=None) -> dict:
    return {"number": number, "title": f"issue {number}", "createdAt": created, "blockedBy": blocked_by or []}


def comment(body: str, at: str, login: str = "me") -> dict:
    return {"body": body, "createdAt": f"2026-10-29T{at}:00Z", "author": {"login": login}}


def claimed(branch: str = "feature/x", at: str = "10:00") -> dict:
    return comment(f"task-board claim: {branch}", at)


def board_page(items: list, cursor: str | None, field=STATUS_FIELD) -> str:
    """A page of BOARD_QUERY's answer, shaped as GitHub's schema and the captured empty page give it."""
    nodes = [{"id": entry["id"],
              "status": {"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": entry["status"]}
              if entry["status"] else None,
              "content": {"__typename": entry["content"]["type"], "number": entry["content"]["number"],
                          "title": entry["content"]["title"], "url": entry["content"]["url"],
                          "repository": {"nameWithOwner": entry["content"]["repository"]}}}
             for entry in items]
    return json.dumps({"data": {"organization": {"projectV2": {"id": PROJECT_ID, "field": field, "items": {
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
    back through GraphQL in pages of `page_size`; Priorities live per issue, as the organization's field does."""

    def __init__(self, items=(), issues=(), comments=None, priorities=None, fail_on=None, fail_once_on=None,
                 create_output=None, page_size=100, versions=("2022-11-28", "2026-03-10"), deprecated=False,
                 canonical=REPO, add_conflict=False):
        self.items, self.issues = list(items), list(issues)
        self.comments = {number: list(entries) for number, entries in (comments or {}).items()}
        self.priorities = dict(priorities or {})
        self.fail_on, self.fail_once_on, self.page_size, self.calls = fail_on, fail_once_on, page_size, []
        self.create_output = "https://github.com/o/r/issues/9\n" if create_output is None else create_output
        self.versions, self.deprecated = list(versions), deprecated
        # canonical: the repository's current name, as GitHub answers for the configured one (a rename changes it).
        # add_conflict: adding an issue fails with ALREADY_ON_BOARD, auto-add having placed it a moment before.
        self.canonical, self.add_conflict = canonical, add_conflict

    @staticmethod
    def kind(args: tuple) -> str:
        if args[:2] == ("api", "graphql"):
            query = variables(args)["query"]
            return {board.BOARD_QUERY: "board", board.SET_STATUS_MUTATION: "set-status",
                    board.ADD_ITEM_MUTATION: "add-item"}[query]
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
            return board_page(self.items[start:end], str(end) if end < len(self.items) else None)
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
            return self.create_output
        if kind == "issue-close":
            number = int(args[2])
            body = args[args.index("--comment") + 1]
            self.comments.setdefault(number, []).append({"body": body, "createdAt": "2026-10-29T13:00:00Z",
                                                          "author": {"login": "me"}})
            self.issues = [entry for entry in self.issues if entry["number"] != number]
            return ""
        raise AssertionError(f"unhandled gh call: {args}")

    def kinds(self) -> list:
        return [self.kind(args) for args, _ in self.calls]

    def edits(self) -> list:
        """The Status set by each set-status call, in order."""
        names = {option_id: name for name, option_id in STATUS_IDS.items()}
        return [names[variables(args)["option"]] for args, _ in self.calls if self.kind(args) == "set-status"]

    def priority_writes(self) -> list:
        return [(int(args[-1].split("/")[-2]), json.loads(given)["issue_field_values"][0]["value"])
                for args, given in self.calls if self.kind(args) == "priority-write"]

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
        node = page["data"]["organization"]["projectV2"]["items"]["nodes"][0]
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
            breakage(page["data"]["organization"]["projectV2"])
            with self.assertRaises(board.GhError):
                board.parse_board_page(json.dumps(page), 1)

    def test_graphql_errors_and_a_missing_board_are_reported(self):
        with self.assertRaises(board.GhError):
            board.parse_board_page('{"errors": [{"message": "bad"}], "data": null}', 1)
        with self.assertRaises(board.BoardError):
            board.parse_board_page('{"data": {"organization": {"projectV2": null}}}', 7)

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
