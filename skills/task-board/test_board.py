"""Tests for board.py. Run: python3 -m unittest discover -s skills/task-board

The fixtures marked "captured" are trimmed from real gh output against the tia-tools board on 2026-10-29 (plan 0031):
the organization's issue fields and the board's field list. The rest follow the shapes those captures and GitHub's
REST reference show."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import board  # beside this file: discover -s and direct runs both put this folder on the import path

REPO = "o/r"
PROJECT = {"id": "PVT_kwDOEfCcUc4BpKm6", "number": 1, "title": "tasks"}
# captured: `gh project field-list 1 --owner tia-tools --format json`, three of its fourteen fields. The board shows the
# organization's Priority issue field as a single-select field with no options of its own.
FIELDS = {"fields": [
    {"id": "PVTF_lADOEfCcUc4BpKm6zhnnb4Q", "name": "Title", "type": "ProjectV2Field"},
    {"id": "PVTSSF_lADOEfCcUc4BpKm6zhnnb4c", "name": "Status", "type": "ProjectV2SingleSelectField",
     "options": [{"id": "782d1866", "name": "Triage"}, {"id": "f75ad846", "name": "Todo"},
                 {"id": "47fc9ee4", "name": "In Progress"}, {"id": "98236657", "name": "Done"}]},
    {"id": "PVTSSF_lADOEfCcUc4BpKm6zhnnk50", "name": "Priority", "type": "ProjectV2SingleSelectField"}]}
STATUS_IDS = {"Triage": "782d1866", "Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}
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


def item(number: int, status: str | None, repo: str = REPO, kind: str = "Issue") -> dict:
    """A board item as parse_item_page returns it."""
    return {"id": f"PVTI_{number}", "status": status or "",
            "content": {"type": kind, "number": number, "title": f"issue {number}",
                        "url": f"https://github.com/{repo}/issues/{number}", "repository": repo}}


def issue(number: int, created: str = "2026-10-01T00:00:00Z", blocked_by=None) -> dict:
    return {"number": number, "title": f"issue {number}", "createdAt": created, "blockedBy": blocked_by or []}


def comment(body: str, at: str, login: str = "me") -> dict:
    return {"body": body, "createdAt": f"2026-10-29T{at}:00Z", "author": {"login": login}}


def claimed(branch: str = "feature/x", at: str = "10:00") -> dict:
    return comment(f"task-board claim: {branch}", at)


def graphql_page(items: list, cursor: str | None) -> str:
    """The board's items as the GraphQL ITEMS_QUERY answers: status and content shaped like the captured page."""
    nodes = [{"id": entry["id"], "status": {"name": entry["status"]} if entry["status"] else None,
              "content": {"__typename": entry["content"]["type"], "number": entry["content"]["number"],
                          "title": entry["content"]["title"], "url": entry["content"]["url"],
                          "repository": {"nameWithOwner": entry["content"]["repository"]}}}
             for entry in items]
    return json.dumps({"data": {"organization": {"projectV2": {"items": {
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}}}}})


class FakeGh:
    """Answers the gh calls Board makes, and records them. The board's items come back through GraphQL in pages of
    `page_size`; Priorities live per issue, as the organization's issue field does. fail_on fails every call whose
    first two or three arguments match; fail_once_on fails only the first such call, to test a rerun."""

    def __init__(self, items=(), issues=(), comments=None, priorities=None, fail_on=None, fail_once_on=None,
                 create_output=None, page_size=100):
        self.items, self.issues = list(items), list(issues)
        self.comments = {number: list(entries) for number, entries in (comments or {}).items()}
        self.priorities = dict(priorities or {})
        self.fail_on, self.fail_once_on, self.page_size, self.calls = fail_on, fail_once_on, page_size, []
        self.create_output = "https://github.com/o/r/issues/9\n" if create_output is None else create_output

    def run(self, *args: str, input: str | None = None) -> str:
        self.calls.append((args, input))
        key = args[:2]
        if self.fail_on in (key, args[:3]):
            raise board.GhError("gh failed")
        if self.fail_once_on in (key, args[:3]):
            self.fail_once_on = None
            raise board.GhError("gh failed once")
        if key == ("project", "view"):
            return json.dumps(PROJECT)
        if key == ("project", "field-list"):
            return json.dumps(FIELDS)
        if key == ("api", "graphql"):
            start = int(next((arg.split("=", 1)[1] for arg in args if arg.startswith("after=")), "0"))
            end = start + self.page_size
            return graphql_page(self.items[start:end], str(end) if end < len(self.items) else None)
        if key == ("api", "orgs/o/issue-fields"):
            return json.dumps(ISSUE_FIELDS)
        if args[:3] == ("api", "--method", "POST"):
            number = int(args[3].split("/")[-2])
            for value in json.loads(input)["issue_field_values"]:
                assert value["field_id"] == PRIORITY_FIELD_ID, value
                self.priorities[number] = value["value"]
            return "[]"
        if key[0] == "api" and key[1].endswith("/issue-field-values"):
            number = int(key[1].split("/")[-2])
            name = self.priorities.get(number)
            return json.dumps([] if not name else [
                {"issue_field_id": PRIORITY_FIELD_ID, "issue_field_name": "Priority", "data_type": "single_select",
                 "value": name, "single_select_option": {"id": 1, "name": name, "color": "red"}}])
        if key == ("issue", "list"):
            return json.dumps(self.issues)
        if key == ("issue", "comment"):
            body = args[args.index("--body") + 1]
            self.comments.setdefault(int(args[2]), []).append({"body": body, "createdAt": "2026-10-29T12:00:00Z",
                                                               "author": {"login": "me"}})
            return ""
        if key == ("issue", "view"):
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        if key == ("api", "user"):
            return "me\n"
        if key == ("issue", "create"):
            return self.create_output
        if key == ("project", "item-add"):
            return json.dumps({"id": "PVTI_9"})
        if key == ("project", "item-edit"):
            item_id, option = args[args.index("--id") + 1], args[args.index("--single-select-option-id") + 1]
            names = {option_id: name for name, option_id in STATUS_IDS.items()}
            for entry in self.items:
                if entry["id"] == item_id:
                    entry["status"] = names[option]
            return ""
        if key == ("issue", "close"):
            number = int(args[2])
            body = args[args.index("--comment") + 1]
            self.comments.setdefault(number, []).append({"body": body, "createdAt": "2026-10-29T13:00:00Z",
                                                          "author": {"login": "me"}})
            self.issues = [entry for entry in self.issues if entry["number"] != number]
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    def commands(self) -> list:
        return [args for args, _ in self.calls]

    def edits(self) -> list:
        """The Status set by each item-edit call, in order."""
        names = {option_id: name for name, option_id in STATUS_IDS.items()}
        return [names[args[args.index("--single-select-option-id") + 1]] for args in self.commands()
                if args[:2] == ("project", "item-edit")]

    def priority_writes(self) -> list:
        return [(int(args[3].split("/")[-2]), json.loads(given)["issue_field_values"][0]["value"])
                for args, given in self.calls if args[:3] == ("api", "--method", "POST")]


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

    def test_status_field_from_the_captured_field_list(self):
        field = board.parse_status_field(json.dumps(PROJECT), json.dumps(FIELDS))
        self.assertEqual((field.project_id, field.status_id), ("PVT_kwDOEfCcUc4BpKm6", "PVTSSF_lADOEfCcUc4BpKm6zhnnb4c"))
        self.assertEqual(field.status_options["In Progress"], "47fc9ee4")

    def test_a_missing_status_option_is_named(self):
        broken = json.loads(json.dumps(FIELDS))
        broken["fields"][1]["options"] = [option for option in broken["fields"][1]["options"]
                                          if option["name"] != "Triage"]
        with self.assertRaisesRegex(board.BoardError, "Triage"):
            board.parse_status_field(json.dumps(PROJECT), json.dumps(broken))

    def test_priority_ranks_options_by_their_priority_number_not_their_order(self):
        field = board.parse_priority_field(json.dumps(ISSUE_FIELDS))
        self.assertEqual(field.field_id, PRIORITY_FIELD_ID)
        self.assertEqual(field.priorities, PRIORITIES)
        self.assertEqual(field.default_priority(), "Medium")
        self.assertEqual(field.priority("Low"), "Low")
        with self.assertRaisesRegex(board.BoardError, "Urgent, High, Medium, Low"):
            field.priority("P1")

    def test_priority_is_the_field_named_priority_not_another_with_the_same_options(self):
        only_effort = [field for field in ISSUE_FIELDS if field["name"] != "Priority"]
        with self.assertRaisesRegex(board.BoardError, "Issue Fields"):
            board.parse_priority_field(json.dumps(only_effort))

    def test_an_issues_priority_is_read_from_its_field_values(self):
        values = [{"issue_field_id": 43924881, "single_select_option": {"name": "High"}},
                  {"issue_field_id": PRIORITY_FIELD_ID, "single_select_option": {"name": "Urgent"}}]
        self.assertEqual(board.priority_value(json.dumps(values), PRIORITY_FIELD_ID), "Urgent")
        self.assertEqual(board.priority_value("[]", PRIORITY_FIELD_ID), "")


class ItemPages(unittest.TestCase):
    def test_a_node_without_status_reads_as_triage_and_with_one_as_that_status(self):
        items, cursor = board.parse_item_page(graphql_page([item(1, None), item(2, "Todo")], None), 1)
        self.assertIsNone(cursor)
        self.assertEqual([board.status_of(entry) for entry in items], ["Triage", "Todo"])
        self.assertEqual(items[1]["content"]["repository"], REPO)

    def test_the_captured_empty_board(self):
        captured = '{"data":{"organization":{"projectV2":{"items":{"pageInfo":{"hasNextPage":false,' \
                   '"endCursor":null},"nodes":[]}}}}}'
        self.assertEqual(board.parse_item_page(captured, 1), ([], None))

    def test_graphql_errors_and_a_missing_board_are_reported(self):
        with self.assertRaises(board.GhError):
            board.parse_item_page('{"errors": [{"message": "bad"}], "data": null}', 1)
        with self.assertRaises(board.BoardError):
            board.parse_item_page('{"data": {"organization": {"projectV2": null}}}', 7)

    def test_every_page_is_read(self):
        gh = FakeGh(items=[item(number, "Todo") for number in range(1, 6)], page_size=2)
        self.assertEqual([entry["content"]["number"] for entry in make_board(gh).items()], [1, 2, 3, 4, 5])
        self.assertEqual(sum(args[:2] == ("api", "graphql") for args in gh.commands()), 3)


    def test_a_page_cursor_that_does_not_advance_is_an_error_not_a_loop(self):
        class Stuck(FakeGh):
            def run(self, *args, input=None):
                if args[:2] == ("api", "graphql"):
                    self.calls.append((args, input))
                    return graphql_page([item(1, "Todo")], "same")
                return super().run(*args, input=input)

        with self.assertRaisesRegex(board.GhError, "did not advance"):
            make_board(Stuck()).items()


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

    def test_blockers_given_as_graphql_nodes(self):
        nodes = [issue(1, blocked_by={"nodes": [{"number": 2, "state": "OPEN"}]})]
        self.assertEqual(self.ready_numbers([item(1, "Todo")], nodes), [])

    def test_the_board_reads_priorities_only_for_ready_candidates(self):
        gh = FakeGh(items=[item(1, "Todo"), item(2, None), item(3, "Todo")], issues=[issue(1), issue(2), issue(3)],
                    priorities={1: "Low", 3: "Urgent"})
        self.assertEqual([(entry["number"], entry["priority"]) for entry in make_board(gh).ready()],
                         [(3, "Urgent"), (1, "Low")])
        reads = [args[1] for args in gh.commands() if args[0] == "api" and args[1].endswith("/issue-field-values")]
        self.assertEqual(sorted(reads), ["repos/o/r/issues/1/issue-field-values",
                                         "repos/o/r/issues/3/issue-field-values"])


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
    def test_no_step_uses_project_item_list(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).ready()
        self.assertFalse(any(args[:2] == ("project", "item-list") for args in gh.commands()))

    def test_claim_comments_first_then_moves_to_in_progress(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).claim(1, "feature/x", "../r-x")
        self.assertEqual(gh.edits(), ["In Progress"])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board claim: feature/x in ../r-x")
        commands = gh.commands()
        first_comment = next(i for i, args in enumerate(commands) if args[:2] == ("issue", "comment"))
        first_edit = next(i for i, args in enumerate(commands) if args[:2] == ("project", "item-edit"))
        self.assertLess(first_comment, first_edit)

    def test_a_claim_whose_status_change_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], fail_once_on=("project", "item-edit"))
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

    def test_file_into_todo_sets_the_issue_priority_then_status(self):
        gh = FakeGh()
        number = make_board(gh).file("New task", "", todo=True, priority=None, blocked_by="4")
        self.assertEqual(number, 9)
        commands = gh.commands()
        create = next(args for args in commands if args[:2] == ("issue", "create"))
        self.assertEqual(create[create.index("--blocked-by") + 1], "4")
        add = next(args for args in commands if args[:2] == ("project", "item-add"))
        self.assertEqual(add[add.index("--url") + 1], "https://github.com/o/r/issues/9")
        self.assertEqual(gh.priority_writes(), [(9, "Medium")])
        write = next(i for i, args in enumerate(commands) if args[:3] == ("api", "--method", "POST"))
        edit = next(i for i, args in enumerate(commands) if args[:2] == ("project", "item-edit"))
        self.assertLess(write, edit)
        self.assertEqual(gh.edits(), ["Todo"])

    def test_file_into_triage_sets_no_priority(self):
        gh = FakeGh()
        make_board(gh).file("Follow-up", "found while fixing #3", todo=False, priority=None, blocked_by=None)
        self.assertEqual(gh.edits(), ["Triage"])
        self.assertEqual(gh.priority_writes(), [])

    def test_file_checks_the_board_before_creating_the_issue(self):
        for broken in (("project", "field-list"), ("api", "orgs/o/issue-fields")):
            gh = FakeGh(fail_on=broken)
            with self.assertRaises(board.GhError):
                make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)
            self.assertFalse(any(args[:2] == ("issue", "create") for args in gh.commands()))

    def test_file_names_the_created_issue_when_placing_it_fails(self):
        for broken in (("project", "item-add"), ("api", "--method", "POST")):
            gh = FakeGh(fail_on=broken)
            with self.assertRaisesRegex(board.GhError, "#9 was created"):
                make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)

    def test_file_refuses_output_without_this_repositorys_issue_url(self):
        for output in ("", "Creating issue…\n", "https://github.com/o/other/issues/9\n"):
            gh = FakeGh(create_output=output)
            with self.assertRaises(board.GhError):
                make_board(gh).file("x", "", todo=False, priority=None, blocked_by=None)
            self.assertFalse(any(args[:2] == ("project", "item-add") for args in gh.commands()))

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
        self.assertFalse(any(args[:2] == ("issue", "create") for args in gh.commands()))

    def test_done_closes_first_then_sets_done(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]})
        make_board(gh).done(1, "feature/x", "merged abc123 into develop; tests green")
        self.assertEqual(gh.edits(), ["Done"])
        commands = gh.commands()
        close = next(i for i, args in enumerate(commands) if args[:2] == ("issue", "close"))
        edit = next(i for i, args in enumerate(commands) if args[:2] == ("project", "item-edit"))
        self.assertLess(close, edit)
        self.assertEqual(commands[close][commands[close].index("--comment") + 1],
                         "task-board done: feature/x: merged abc123 into develop; tests green")

    def test_a_done_whose_status_change_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on=("project", "item-edit"))
        with self.assertRaises(board.GhError):
            make_board(gh).done(1, "feature/x", "merged abc123")
        make_board(gh).done(1, "feature/x", "merged abc123")
        self.assertEqual(board.status_of(gh.items[0]), "Done")
        self.assertEqual(sum(args[:2] == ("issue", "close") for args in gh.commands()), 1)

    def test_a_done_rerun_is_only_for_the_branch_that_closed_it(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on=("project", "item-edit"))
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
            self.assertFalse(any(args[:2] == ("issue", "close") for args in gh.commands()))

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
                    fail_once_on=("issue", "comment"))
        with self.assertRaises(board.GhError):
            make_board(gh).release(1, "feature/x", "stopping")
        make_board(gh).release(1, "feature/x", "stopping")
        self.assertIsNone(board.claim_holder(gh.comments[1], "me"))
        self.assertEqual(board.status_of(gh.items[0]), "Todo")


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / ".git").mkdir()
        (self.folder / ".task-board.json").write_text('{"owner": "o", "project": 1, "repo": "o/r"}')

    def test_exit_status_per_outcome(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        self.assertEqual(board.main(["ready"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["done", "1", "--branch", "feature/x", "--evidence", "x"], gh=gh,
                                    cwd=self.folder), 3)
        self.assertEqual(board.main(["ready"], gh=FakeGh(fail_on=("api", "graphql")), cwd=self.folder), 2)
        empty = Path(tempfile.mkdtemp())
        (empty / ".git").mkdir()
        self.assertEqual(board.main(["ready"], gh=gh, cwd=empty), 1)

    def test_unexpected_gh_output_exits_2_not_with_a_traceback(self):
        class Garbled(FakeGh):
            def run(self, *args, input=None):
                return "not json" if args[:2] == ("api", "graphql") else super().run(*args, input=input)

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


if __name__ == "__main__":
    unittest.main()
