"""Tests for board.py. Run: python3 -m unittest discover -s skills/task-board"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import board  # beside this file: discover -s and direct runs both put this folder on the import path

REPO = "o/r"
PROJECT = {"id": "PVT_1", "number": 3, "title": "tasks"}
FIELDS = {"fields": [
    {"id": "F_STATUS", "name": "Status", "type": "ProjectV2SingleSelectField",
     "options": [{"id": "s_triage", "name": "Triage"}, {"id": "s_todo", "name": "Todo"},
                 {"id": "s_progress", "name": "In Progress"}, {"id": "s_done", "name": "Done"}]},
    {"id": "F_PRIORITY", "name": "Priority", "type": "ProjectV2SingleSelectField",
     "options": [{"id": "p1", "name": "P1"}, {"id": "p2", "name": "P2"}, {"id": "p3", "name": "P3"}]},
    {"id": "F_TITLE", "name": "Title", "type": "ProjectV2Field"}]}


def item(number: int, status: str | None, priority: str | None = None, repo: str = REPO,
         kind: str = "Issue") -> dict:
    entry = {"id": f"PVTI_{number}", "content": {"type": kind, "number": number, "title": f"issue {number}",
                                                 "repository": repo,
                                                 "url": f"https://github.com/{repo}/issues/{number}"}}
    if status is not None:
        entry["status"] = status
    if priority is not None:
        entry["priority"] = priority
    return entry


def issue(number: int, created: str = "2026-10-01T00:00:00Z", blocked_by=None) -> dict:
    return {"number": number, "title": f"issue {number}", "createdAt": created, "blockedBy": blocked_by or []}


class FakeGh:
    """Answers the gh calls Board makes, and records them."""

    def __init__(self, items=(), issues=(), comments=None, fail_on=None):
        self.items, self.issues = list(items), list(issues)
        self.comments = {number: list(entries) for number, entries in (comments or {}).items()}
        self.fail_on, self.calls = fail_on, []

    def run(self, *args: str) -> str:
        self.calls.append(args)
        key = args[:2]
        if self.fail_on == key:
            raise board.GhError("gh failed")
        if key == ("project", "view"):
            return json.dumps(PROJECT)
        if key == ("project", "field-list"):
            return json.dumps(FIELDS)
        if key == ("project", "item-list"):
            return json.dumps({"items": self.items, "totalCount": len(self.items)})
        if key == ("issue", "list"):
            return json.dumps(self.issues)
        if key == ("issue", "comment"):
            body = args[args.index("--body") + 1]
            self.comments.setdefault(int(args[2]), []).append({"body": body, "createdAt": "2026-10-29T12:00:00Z"})
            return ""
        if key == ("issue", "view"):
            return json.dumps({"comments": self.comments.get(int(args[2]), [])})
        if key == ("issue", "create"):
            return "https://github.com/o/r/issues/9\n"
        if key == ("project", "item-add"):
            return json.dumps({"id": "PVTI_9"})
        if key in (("project", "item-edit"), ("issue", "close")):
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    def edits(self) -> list:
        """(field id, option id) of each item-edit call, in order."""
        return [(call[call.index("--field-id") + 1], call[call.index("--single-select-option-id") + 1])
                for call in self.calls if call[:2] == ("project", "item-edit")]


def make_board(gh: FakeGh) -> board.Board:
    return board.Board(board.Config(owner="o", project=3, repo=REPO), gh)


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

    def test_fields_resolve_names_to_ids(self):
        fields = board.parse_fields(json.dumps(PROJECT), json.dumps(FIELDS))
        self.assertEqual((fields.project_id, fields.status_id, fields.priority_id), ("PVT_1", "F_STATUS", "F_PRIORITY"))
        self.assertEqual(fields.status_options["In Progress"], "s_progress")
        self.assertEqual(fields.priority_options["P3"], "p3")

    def test_a_missing_status_option_is_named(self):
        broken = json.loads(json.dumps(FIELDS))
        broken["fields"][0]["options"] = [option for option in broken["fields"][0]["options"]
                                          if option["name"] != "Triage"]
        with self.assertRaisesRegex(board.BoardError, "Triage"):
            board.parse_fields(json.dumps(PROJECT), json.dumps(broken))

    def test_a_missing_priority_field_is_named(self):
        broken = {"fields": [FIELDS["fields"][0]]}
        with self.assertRaisesRegex(board.BoardError, "Priority"):
            board.parse_fields(json.dumps(PROJECT), json.dumps(broken))


class Ready(unittest.TestCase):
    def ready_numbers(self, items, issues) -> list:
        return [entry["number"] for entry in board.ready(items, issues, REPO)]

    def test_only_open_todo_issues_of_this_repository(self):
        items = [item(1, "Todo"), item(2, None), item(3, "Triage"), item(4, "In Progress"), item(5, "Done"),
                 item(6, "Todo"), item(7, "Todo", repo="o/other"), item(8, "Todo", kind="DraftIssue")]
        issues = [issue(number) for number in (1, 2, 3, 4, 5, 7, 8)]  # 6 is closed
        self.assertEqual(self.ready_numbers(items, issues), [1])

    def test_an_item_without_status_counts_as_triage(self):
        self.assertEqual(board.status_of(item(2, None)), "Triage")
        self.assertEqual(board.status_of(item(2, "Todo")), "Todo")

    def test_priority_then_age_orders_the_list(self):
        items = [item(1, "Todo", "P3"), item(2, "Todo"), item(3, "Todo", "P1"), item(4, "Todo", "P2")]
        issues = [issue(1, "2026-01-01"), issue(2, "2026-03-01"), issue(3, "2026-05-01"), issue(4, "2026-02-01")]
        # 2 has no Priority, so it counts as P2, and 4 is the older of the two P2s.
        self.assertEqual(self.ready_numbers(items, issues), [3, 4, 2, 1])

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


class ClaimHolder(unittest.TestCase):
    def test_the_earliest_claim_holds(self):
        comments = [{"body": "task-board claim: feature/b", "createdAt": "2026-10-29T10:05:00Z"},
                    {"body": "task-board claim: feature/a in ../r-a", "createdAt": "2026-10-29T10:00:00Z"}]
        self.assertEqual(board.claim_holder(comments), "feature/a")

    def test_a_release_or_done_ends_a_claim(self):
        claim = {"body": "task-board claim: feature/a", "createdAt": "2026-10-29T10:00:00Z"}
        for ending in ("task-board release: stopped", "task-board done: merged abc123"):
            comments = [claim, {"body": ending, "createdAt": "2026-10-29T11:00:00Z"}]
            self.assertIsNone(board.claim_holder(comments))
        later = comments + [{"body": "task-board claim: feature/c", "createdAt": "2026-10-29T12:00:00Z"}]
        self.assertEqual(board.claim_holder(later), "feature/c")

    def test_ordinary_comments_are_ignored(self):
        self.assertIsNone(board.claim_holder([{"body": "looks good", "createdAt": "2026-10-29T10:00:00Z"}]))


class Steps(unittest.TestCase):
    def test_claim_moves_to_in_progress_and_comments(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).claim(1, "feature/x", "../r-x")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_progress")])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board claim: feature/x in ../r-x")

    def test_claim_backs_off_when_another_session_claimed_first(self):
        earlier = {"body": "task-board claim: feature/other", "createdAt": "2026-10-29T11:00:00Z"}
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)], comments={1: [earlier]})
        with self.assertRaisesRegex(board.Refused, "feature/other"):
            make_board(gh).claim(1, "feature/x", None)

    def test_claim_refuses_work_that_is_not_ready_and_changes_nothing(self):
        for status in (None, "Triage", "In Progress"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            with self.assertRaises(board.Refused):
                make_board(gh).claim(1, "feature/x", None)
            self.assertEqual(gh.edits(), [])
            self.assertNotIn(1, gh.comments)

    def test_file_into_todo_sets_status_and_default_priority(self):
        gh = FakeGh()
        number = make_board(gh).file("New task", "", todo=True, priority=None, blocked_by="4")
        self.assertEqual(number, 9)
        create = next(call for call in gh.calls if call[:2] == ("issue", "create"))
        self.assertEqual(create[create.index("--blocked-by") + 1], "4")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_todo"), ("F_PRIORITY", "p2")])

    def test_file_into_triage_sets_no_priority(self):
        gh = FakeGh()
        make_board(gh).file("Follow-up", "found while fixing #3", todo=False, priority=None, blocked_by=None)
        self.assertEqual(gh.edits(), [("F_STATUS", "s_triage")])

    def test_file_checks_the_board_before_creating_the_issue(self):
        gh = FakeGh(fail_on=("project", "field-list"))
        with self.assertRaises(board.GhError):
            make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)
        self.assertFalse(any(call[:2] == ("issue", "create") for call in gh.calls))

    def test_queue_accepts_a_triage_item_with_a_priority(self):
        for status in (None, "Triage"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            make_board(gh).queue(1, "P1")
            self.assertEqual(gh.edits(), [("F_STATUS", "s_todo"), ("F_PRIORITY", "p1")])

    def test_queue_refuses_an_item_already_past_triage(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)])
        with self.assertRaises(board.Refused):
            make_board(gh).queue(1, None)
        self.assertEqual(gh.edits(), [])

    def test_done_closes_with_evidence_only_from_in_progress(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)])
        make_board(gh).done(1, "merged abc123 into develop; tests green")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_done")])
        close = next(call for call in gh.calls if call[:2] == ("issue", "close"))
        self.assertEqual(close[close.index("--comment") + 1], "task-board done: merged abc123 into develop; tests green")
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        with self.assertRaises(board.Refused):
            make_board(gh).done(1, "x")
        self.assertFalse(any(call[:2] == ("issue", "close") for call in gh.calls))

    def test_release_returns_to_todo_with_a_reason(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)])
        make_board(gh).release(1, "blocked on the card data file")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_todo")])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board release: blocked on the card data file")


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / ".git").mkdir()
        (self.folder / ".task-board.json").write_text('{"owner": "o", "project": 3, "repo": "o/r"}')

    def test_exit_status_per_outcome(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        self.assertEqual(board.main(["ready"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["done", "1", "--evidence", "x"], gh=gh, cwd=self.folder), 3)
        self.assertEqual(board.main(["ready"], gh=FakeGh(fail_on=("project", "item-list")), cwd=self.folder), 2)
        empty = Path(tempfile.mkdtemp())
        (empty / ".git").mkdir()
        self.assertEqual(board.main(["ready"], gh=gh, cwd=empty), 1)

    def test_priority_is_refused_with_triage(self):
        with self.assertRaises(SystemExit):
            board.parse_args(["file", "--triage", "--priority", "P1", "--title", "x"])

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
