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
    """Answers the gh calls Board makes, and records them. Like the real gh, item-list gives a field's values
    only when asked for that field with --field. fail_on fails every call with that (verb, subverb);
    fail_once_on fails only the first such call, to test a rerun."""

    def __init__(self, items=(), issues=(), comments=None, fail_on=None, fail_once_on=None, create_output=None):
        self.items, self.issues = list(items), list(issues)
        self.comments = {number: list(entries) for number, entries in (comments or {}).items()}
        self.fail_on, self.fail_once_on, self.calls = fail_on, fail_once_on, []
        self.create_output = "https://github.com/o/r/issues/9\n" if create_output is None else create_output

    def run(self, *args: str) -> str:
        self.calls.append(args)
        key = args[:2]
        if self.fail_on == key:
            raise board.GhError("gh failed")
        if self.fail_once_on == key:
            self.fail_once_on = None
            raise board.GhError("gh failed once")
        if key == ("project", "view"):
            return json.dumps(PROJECT)
        if key == ("project", "field-list"):
            return json.dumps(FIELDS)
        if key == ("project", "item-list"):
            asked = {args[i + 1].lower() for i, arg in enumerate(args) if arg == "--field"}
            shown = [{k: v for k, v in entry.items() if k not in ("status", "priority") or k in asked}
                     for entry in self.items]
            return json.dumps({"items": shown, "totalCount": len(shown)})
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
            # Reflect the change, so a rerun sees it.
            item_id, option = args[args.index("--id") + 1], args[args.index("--single-select-option-id") + 1]
            names = {"s_triage": ("status", "Triage"), "s_todo": ("status", "Todo"),
                     "s_progress": ("status", "In Progress"), "s_done": ("status", "Done"),
                     "p1": ("priority", "P1"), "p2": ("priority", "P2"), "p3": ("priority", "P3")}
            for entry in self.items:
                if entry["id"] == item_id:
                    entry[names[option][0]] = names[option][1]
            return ""
        if key == ("issue", "close"):
            number = int(args[2])
            body = args[args.index("--comment") + 1]
            self.comments.setdefault(number, []).append({"body": body, "createdAt": "2026-10-29T13:00:00Z",
                                                          "author": {"login": "me"}})
            self.issues = [entry for entry in self.issues if entry["number"] != number]
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


def comment(body: str, at: str, login: str = "me") -> dict:
    return {"body": body, "createdAt": f"2026-10-29T{at}:00Z", "author": {"login": login}}


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


def claimed(branch: str = "feature/x", at: str = "10:00") -> dict:
    return comment(f"task-board claim: {branch}", at)


class Steps(unittest.TestCase):
    def test_the_item_list_asks_gh_for_status_and_priority(self):
        gh = FakeGh(items=[item(1, "Todo", "P1")], issues=[issue(1)])
        self.assertEqual([entry["priority"] for entry in make_board(gh).ready()], ["P1"])
        listing = next(call for call in gh.calls if call[:2] == ("project", "item-list"))
        asked = [listing[i + 1] for i, arg in enumerate(listing) if arg == "--field"]
        self.assertEqual(sorted(asked), ["Priority", "Status"])

    def test_claim_comments_first_then_moves_to_in_progress(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        make_board(gh).claim(1, "feature/x", "../r-x")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_progress")])
        self.assertEqual(gh.comments[1][-1]["body"], "task-board claim: feature/x in ../r-x")
        first_comment = next(i for i, call in enumerate(gh.calls) if call[:2] == ("issue", "comment"))
        first_edit = next(i for i, call in enumerate(gh.calls) if call[:2] == ("project", "item-edit"))
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
        self.assertEqual(gh.edits(), [("F_STATUS", "s_progress")])

    def test_claim_refuses_work_that_is_not_ready_and_changes_nothing(self):
        for status in (None, "Triage", "In Progress"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            with self.assertRaises(board.Refused):
                make_board(gh).claim(1, "feature/x", None)
            self.assertEqual(gh.edits(), [])
            self.assertNotIn(1, gh.comments)

    def test_file_into_todo_sets_priority_then_status(self):
        gh = FakeGh()
        number = make_board(gh).file("New task", "", todo=True, priority=None, blocked_by="4")
        self.assertEqual(number, 9)
        create = next(call for call in gh.calls if call[:2] == ("issue", "create"))
        self.assertEqual(create[create.index("--blocked-by") + 1], "4")
        add = next(call for call in gh.calls if call[:2] == ("project", "item-add"))
        self.assertEqual(add[add.index("--url") + 1], "https://github.com/o/r/issues/9")
        self.assertEqual(gh.edits(), [("F_PRIORITY", "p2"), ("F_STATUS", "s_todo")])

    def test_file_into_triage_sets_no_priority(self):
        gh = FakeGh()
        make_board(gh).file("Follow-up", "found while fixing #3", todo=False, priority=None, blocked_by=None)
        self.assertEqual(gh.edits(), [("F_STATUS", "s_triage")])

    def test_file_checks_the_board_before_creating_the_issue(self):
        gh = FakeGh(fail_on=("project", "field-list"))
        with self.assertRaises(board.GhError):
            make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)
        self.assertFalse(any(call[:2] == ("issue", "create") for call in gh.calls))

    def test_file_names_the_created_issue_when_placing_it_fails(self):
        gh = FakeGh(fail_on=("project", "item-add"))
        with self.assertRaisesRegex(board.GhError, "#9 was created"):
            make_board(gh).file("x", "", todo=True, priority=None, blocked_by=None)

    def test_file_refuses_output_without_this_repositorys_issue_url(self):
        for output in ("", "Creating issue…\n", "https://github.com/o/other/issues/9\n"):
            gh = FakeGh(create_output=output)
            with self.assertRaises(board.GhError):
                make_board(gh).file("x", "", todo=False, priority=None, blocked_by=None)
            self.assertFalse(any(call[:2] == ("project", "item-add") for call in gh.calls))

    def test_queue_accepts_a_triage_item_with_a_priority(self):
        for status in (None, "Triage"):
            gh = FakeGh(items=[item(1, status)], issues=[issue(1)])
            make_board(gh).queue(1, "P1")
            self.assertEqual(gh.edits(), [("F_PRIORITY", "p1"), ("F_STATUS", "s_todo")])

    def test_queue_refuses_an_item_already_past_triage(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)])
        with self.assertRaises(board.Refused):
            make_board(gh).queue(1, None)
        self.assertEqual(gh.edits(), [])

    def test_queue_refuses_a_closed_or_claimed_issue_even_with_a_blank_status(self):
        for issues, comments in (([], {}), ([issue(1)], {1: [claimed()]})):
            gh = FakeGh(items=[item(1, None)], issues=issues, comments=comments)
            with self.assertRaises(board.Refused):
                make_board(gh).queue(1, None)
            self.assertEqual(gh.edits(), [])

    def test_done_closes_first_then_sets_done(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]})
        make_board(gh).done(1, "feature/x", "merged abc123 into develop; tests green")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_done")])
        close = next(i for i, call in enumerate(gh.calls) if call[:2] == ("issue", "close"))
        edit = next(i for i, call in enumerate(gh.calls) if call[:2] == ("project", "item-edit"))
        self.assertLess(close, edit)
        self.assertEqual(gh.calls[close][gh.calls[close].index("--comment") + 1],
                         "task-board done: feature/x: merged abc123 into develop; tests green")

    def test_a_done_whose_status_change_failed_finishes_on_a_rerun(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]},
                    fail_once_on=("project", "item-edit"))
        with self.assertRaises(board.GhError):
            make_board(gh).done(1, "feature/x", "merged abc123")
        make_board(gh).done(1, "feature/x", "merged abc123")
        self.assertEqual(board.status_of(gh.items[0]), "Done")
        self.assertEqual(sum(call[:2] == ("issue", "close") for call in gh.calls), 1)

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
            self.assertFalse(any(call[:2] == ("issue", "close") for call in gh.calls))

    def test_release_returns_to_todo_with_a_reason(self):
        gh = FakeGh(items=[item(1, "In Progress")], issues=[issue(1)], comments={1: [claimed()]})
        make_board(gh).release(1, "feature/x", "blocked on the card data file")
        self.assertEqual(gh.edits(), [("F_STATUS", "s_todo")])
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
        (self.folder / ".task-board.json").write_text('{"owner": "o", "project": 3, "repo": "o/r"}')

    def test_exit_status_per_outcome(self):
        gh = FakeGh(items=[item(1, "Todo")], issues=[issue(1)])
        self.assertEqual(board.main(["ready"], gh=gh, cwd=self.folder), 0)
        self.assertEqual(board.main(["done", "1", "--branch", "feature/x", "--evidence", "x"], gh=gh,
                                    cwd=self.folder), 3)
        self.assertEqual(board.main(["ready"], gh=FakeGh(fail_on=("project", "item-list")), cwd=self.folder), 2)
        empty = Path(tempfile.mkdtemp())
        (empty / ".git").mkdir()
        self.assertEqual(board.main(["ready"], gh=gh, cwd=empty), 1)

    def test_unexpected_gh_output_exits_2_not_with_a_traceback(self):
        class Garbled(FakeGh):
            def run(self, *args):
                return "not json" if args[:2] == ("project", "item-list") else super().run(*args)

        self.assertEqual(board.main(["ready"], gh=Garbled(), cwd=self.folder), 2)

    def test_a_missing_gh_is_gh_failing_not_a_traceback(self):
        with self.assertRaisesRegex(board.GhError, "could not run"):
            board.Gh("gh-that-does-not-exist-here").run("api", "user")

    def test_release_and_done_need_a_branch(self):
        for argv in (["release", "1", "--reason", "x"], ["done", "1", "--evidence", "x"]):
            with self.assertRaises(SystemExit):
                board.parse_args(argv)

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
