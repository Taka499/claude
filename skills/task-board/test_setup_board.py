"""Tests for setup_board.py. Run: python3 -m unittest discover -s skills/task-board

The fixtures marked "captured" are trimmed from real gh output against scratch boards on 2026-10-30 (plan 0033 § What
the scratch test measured). The last class runs the real gh binary on every command the other tests produced,
offline, as test_board.py does for board.py."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import board
import setup_board
from test_board import closed_local_port

# captured: a new board's Status field, its option IDs the same on every board measured
NEW_STATUS = {"__typename": "ProjectV2SingleSelectField", "id": "PVTSSF_lADOEfCcUc4Bpb5Uzhn3juA",
              "databaseId": 435654368,
              "options": [{"id": "f75ad846", "name": "Todo", "color": "GREEN",
                           "description": "This item hasn't been started"},
                          {"id": "47fc9ee4", "name": "In Progress", "color": "YELLOW",
                           "description": "This is actively being worked on"},
                          {"id": "98236657", "name": "Done", "color": "PURPLE",
                           "description": "This has been completed"}]}
# captured: a new board's workflows, all on
NEW_WORKFLOWS = [("PWF_4", "Auto-add sub-issues to project", True), ("PWF_3", "Auto-close issue", True),
                 ("PWF_6", "Item added to project", True), ("PWF_1", "Item closed", True),
                 ("PWF_5", "Pull request linked to issue", True), ("PWF_2", "Pull request merged", True)]
# captured: the organization's issue fields through GraphQL, trimmed
ISSUE_FIELDS = {"data": {"organization": {"issueFields": {"nodes": [
    {"__typename": "IssueFieldSingleSelect", "id": "IFSS_kgDOAp49jg", "name": "Priority"},
    {"__typename": "IssueFieldDate"},
    {"__typename": "IssueFieldSingleSelect", "id": "IFSS_kgDOAp49kQ", "name": "Effort"}]}}}}
ISSUE_FIELD_ON_BOARD = {"__typename": "ProjectV2SingleSelectField", "id": "PVTSSF_priority", "isIssueField": True,
                        "options": []}
MUTATIONS = {"create", "private", "status-options", "add-issue-field", "create-priority", "view", "delete-workflow",
             "default-branch"}
KINDS = {setup_board.REPO_QUERY: "repo", setup_board.CREATE_MUTATION: "create", setup_board.SETUP_QUERY: "state",
         setup_board.PRIVATE_MUTATION: "private", setup_board.STATUS_OPTIONS_MUTATION: "status-options",
         setup_board.ISSUE_FIELDS_QUERY: "issue-fields", setup_board.ADD_ISSUE_FIELD_MUTATION: "add-issue-field",
         setup_board.CREATE_PRIORITY_MUTATION: "create-priority",
         setup_board.DELETE_WORKFLOW_MUTATION: "delete-workflow"}


class FakeGh:
    """A repository `o/r` (owned by `owner_login`) and the boards linked to it, answering setup_board's calls as
    GitHub did on the scratch boards. fail_once_on fails the first call of one kind, to test a rerun."""

    def __init__(self, owner_type="Organization", owner_login="o", boards=(), branches=("main",),
                 default_branch="main", fail_once_on=None, ignore=()):
        self.owner_type, self.owner_login = owner_type, owner_login
        self.boards = {entry["id"]: entry for entry in boards}
        self.branches, self.default_branch = set(branches), default_branch
        self.fail_once_on, self.ignore, self.calls = fail_once_on, set(ignore), []

    @staticmethod
    def new_board(number: int, title: str, owner: str, **changes) -> dict:
        status = dict(json.loads(json.dumps(NEW_STATUS)), id=f"PVTSSF_{number}")  # each board's fields are its own
        entry = {"id": f"PVT_{number}", "number": number, "title": title, "closed": False, "owner": owner,
                 "public": False, "status": status, "priority": None, "views": [("TABLE_LAYOUT", ())],
                 "workflows": [(f"{flow_id}_{number}", name, enabled) for flow_id, name, enabled in NEW_WORKFLOWS]}
        entry.update(changes)
        return entry

    def kind(self, args: tuple, given) -> str:
        if args[:3] == ("api", "graphql", "--input"):
            return KINDS[json.loads(given)["query"]]
        path = rest_path(args)
        if "/branches/" in path:
            return "branch"
        if path.endswith("/views"):
            return "view"
        if "PATCH" in args:
            return "default-branch"
        raise AssertionError(f"unhandled gh call: {args}")

    def kinds(self) -> list:
        return [self.kind(args, given) for args, given in self.calls]

    def run(self, *args: str, input: str | None = None) -> str:
        self.calls.append((args, input))
        RECORDED.append((args, input))
        kind = self.kind(args, input)
        if self.fail_once_on == kind:
            self.fail_once_on = None
            raise board.GhError(f"gh failed once ({kind})")
        variables = json.loads(input)["variables"] if args[:2] == ("api", "graphql") else {}
        if kind == "repo":
            assert variables == {"owner": "o" if self.owner_type == "Organization" else "me", "name": "r"}, variables
            return json.dumps({"data": {"repository": {
                "id": "R_1", "nameWithOwner": f"{self.owner_login}/r",
                "defaultBranchRef": {"name": self.default_branch},
                "owner": {"__typename": self.owner_type, "id": "O_1", "login": self.owner_login},
                "projectsV2": {"nodes": [{"id": entry["id"], "number": entry["number"], "title": entry["title"],
                                          "closed": entry["closed"], "owner": {"login": entry["owner"]}}
                                         for entry in self.boards.values()]}}}})
        if kind == "create":
            assert (variables["owner"], variables["repository"]) == ("O_1", "R_1"), variables
            entry = self.new_board(len(self.boards) + 7, variables["title"], self.owner_login)
            self.boards[entry["id"]] = entry
            return json.dumps({"data": {"createProjectV2": {"projectV2": {"id": entry["id"],
                                                                          "number": entry["number"]}}}})
        if kind == "issue-fields":
            assert self.owner_type == "Organization", "a user has no issue fields"
            return json.dumps(ISSUE_FIELDS)
        if kind == "branch":
            if args[-1].rsplit("/", 1)[1] not in self.branches:
                raise board.GhError("gh api … failed: Not Found (HTTP 404)")
            return "{}"
        if kind == "default-branch":
            self.default_branch = args[args.index("-f") + 1].split("=", 1)[1]
            return "{}"
        if kind == "view":
            path = rest_path(args)
            entry = next(value for value in self.boards.values() if path.endswith(f"/{value['number']}/views"))
            owner_path = "orgs" if self.owner_type == "Organization" else "users"
            assert path.startswith(f"{owner_path}/{self.owner_login}/"), path  # the user path takes the login
            body = json.loads(input)
            if kind not in self.ignore and body["layout"] == "board" and \
                    body["vertical_group_by"] == [entry["status"]["databaseId"]]:
                entry["views"].append(("BOARD_LAYOUT", ("Status",)))
            return json.dumps({"id": 1, "layout": "board"})
        entry = self.boards[self.board_of(variables)]
        if kind == "state":
            fields = [{"__typename": "ProjectV2Field", "name": "Title"}, dict(entry["status"], name="Status")]
            fields += [dict(entry["priority"], name="Priority")] if entry["priority"] else []
            return json.dumps({"data": {"node": {
                "id": entry["id"], "number": entry["number"], "public": entry["public"], "fields": {"nodes": fields},
                "views": {"nodes": [{"layout": layout, "verticalGroupByFields": {"nodes": [{"name": name}
                                                                                          for name in columns]}}
                                    for layout, columns in entry["views"]]},
                "workflows": {"nodes": [{"id": flow_id, "name": name, "enabled": enabled}
                                        for flow_id, name, enabled in entry["workflows"]]}}}})
        if kind == "private":
            entry["public"] = False
            return json.dumps({"data": {"updateProjectV2": {"projectV2": {"id": entry["id"]}}}})
        if kind == "status-options":
            entry["status"]["options"] = [dict(option, id=option.get("id") or f"new_{option['name']}")
                                          for option in variables["options"]]
            return json.dumps({"data": {"updateProjectV2Field": {"projectV2Field": {"id": variables["field"]}}}})
        if kind == "add-issue-field":
            assert variables["field"] == "IFSS_kgDOAp49jg", variables
            entry["priority"] = dict(ISSUE_FIELD_ON_BOARD)
            return json.dumps({"data": {"createProjectV2IssueField": {"projectV2Field": {"id": "PVTSSF_priority"}}}})
        if kind == "create-priority":
            entry["priority"] = {"__typename": "ProjectV2SingleSelectField", "id": "PVTSSF_own", "isIssueField": False,
                                 "options": [{"id": f"o_{option['name']}", "name": option["name"]}
                                             for option in variables["options"]]}
            return json.dumps({"data": {"createProjectV2Field": {"projectV2Field": {"id": "PVTSSF_own"}}}})
        if kind == "delete-workflow":
            entry["workflows"] = [flow for flow in entry["workflows"] if flow[0] != variables["id"]]
            return json.dumps({"data": {"deleteProjectV2Workflow": {"deletedWorkflowId": variables["id"]}}})
        raise AssertionError(f"unhandled gh call: {args}")

    def board_of(self, variables: dict) -> str:
        """The board a call is about: named by its ID, or by the ID of its Status field or one of its workflows."""
        for key, entry in self.boards.items():
            if key in (variables.get("id"), variables.get("project")) or entry["status"]["id"] == variables.get(
                    "field") or variables.get("id") in [flow_id for flow_id, _, _ in entry["workflows"]]:
                return key
        raise AssertionError(f"no board for {variables}")

    def mutations(self) -> list:
        return [kind for kind in self.kinds() if kind in MUTATIONS]

    def body(self, kind: str) -> dict:
        args, given = next((args, given) for args, given in self.calls if self.kind(args, given) == kind)
        return json.loads(given)


RECORDED: list = []


def rest_path(args: tuple) -> str:
    """The REST path of a `gh api` call, wherever it stands among the flags."""
    return next(arg for arg in args if re.match(r"(repos|orgs|users)/", arg))


def run(gh: FakeGh, repo="o/r", checkout=None, default_branch=None) -> board.Config:
    return setup_board.Setup(gh, say=lambda line: None).run(repo, checkout, default_branch)


class Pure(unittest.TestCase):
    def test_status_options_put_the_four_first_keeping_ids_and_other_options(self):
        options = [{"id": "a", "name": "Todo", "color": "GREEN", "description": "x"},
                   {"id": "b", "name": "Blocked", "color": "RED", "description": ""},
                   {"id": "c", "name": "Done", "color": "PURPLE", "description": ""},
                   {"id": "d", "name": "In Progress", "color": "YELLOW", "description": ""}]
        wanted = setup_board.status_options(options)
        self.assertEqual([option["name"] for option in wanted], ["Triage", "Todo", "In Progress", "Done", "Blocked"])
        self.assertEqual([option.get("id") for option in wanted], [None, "a", "d", "c", "b"])
        self.assertEqual(wanted[1], {"id": "a", "name": "Todo", "color": "GREEN", "description": "x"})

    def test_status_options_already_in_order_need_nothing(self):
        options = setup_board.status_options(NEW_STATUS["options"])
        self.assertIsNone(setup_board.status_options([dict(option, id=option.get("id") or "t")
                                                       for option in options]))

    def test_a_priority_field_of_the_wrong_kind_needs_a_person(self):
        own = {"__typename": "ProjectV2SingleSelectField", "isIssueField": False, "options": [{"id": "x", "name": "x"}]}
        for owner, field in (("Organization", own), ("User", ISSUE_FIELD_ON_BOARD), ("User", dict(own, options=[])),
                             ("Organization", {"__typename": "ProjectV2Field"})):
            with self.assertRaises(board.BoardError):
                setup_board.priority_step(owner, field)
        self.assertEqual(setup_board.priority_step("Organization", ISSUE_FIELD_ON_BOARD), "ok")
        self.assertEqual(setup_board.priority_step("User", own), "ok")
        self.assertEqual(setup_board.priority_step("Organization", None), "add-issue-field")
        self.assertEqual(setup_board.priority_step("User", None), "create-board-field")

    def test_no_query_asks_for_a_field_by_name(self):
        # a new board has no Priority, and GitHub answers `field(name:)` for a missing field with an error
        for name in dir(setup_board):
            if name.endswith(("_QUERY", "_MUTATION")):
                self.assertNotIn("field(name:", getattr(setup_board, name).replace(" ", ""), name)

    def test_linked_boards_of_another_shape_stop_before_anything_changes(self):
        good = {"id": "PVT_1", "number": 1, "title": "r", "closed": False, "owner": {"login": "o"}}
        for broken in ({k: v for k, v in good.items() if k != "closed"}, dict(good, closed="no"),
                       dict(good, number="1"), dict(good, owner=None), dict(good, id="")):
            answer = {"data": {"repository": {"id": "R_1", "nameWithOwner": "o/r", "defaultBranchRef": None,
                                              "owner": {"__typename": "Organization", "id": "O_1", "login": "o"},
                                              "projectsV2": {"nodes": [broken]}}}}
            with self.assertRaises(board.GhError):
                setup_board.parse_repository(json.dumps(answer))

    def test_status_options_without_ids_or_with_two_of_one_name_stop(self):
        for options in ([{"name": "Todo"}], [{"id": "a", "name": "Todo"}, {"id": "b", "name": "Todo"}],
                        [{"id": "a", "name": ""}]):
            status = dict(NEW_STATUS, name="Status", options=options)
            answer = {"data": {"node": {"id": "PVT_1", "number": 1, "public": False, "fields": {"nodes": [status]},
                                        "views": {"nodes": []}, "workflows": {"nodes": []}}}}
            with self.assertRaises(board.GhError):
                setup_board.parse_setup(json.dumps(answer))

    def test_only_an_item_added_workflow_that_is_on_is_deleted(self):
        self.assertEqual(setup_board.item_added_workflows(NEW_WORKFLOWS), ["PWF_6"])
        self.assertEqual(setup_board.item_added_workflows([("PWF_6", "Item added to project", False)]), [])

    def test_the_issue_field_is_found_by_name_and_kind(self):
        self.assertEqual(setup_board.issue_field_id(json.dumps(ISSUE_FIELDS)), "IFSS_kgDOAp49jg")
        without = {"data": {"organization": {"issueFields": {"nodes": [{"__typename": "IssueFieldDate"}]}}}}
        with self.assertRaises(board.BoardError):
            setup_board.issue_field_id(json.dumps(without))


class Run(unittest.TestCase):
    def test_a_new_organization_board_is_created_linked_and_set_up(self):
        gh = FakeGh()
        config = run(gh)
        self.assertEqual(config, board.Config("o", 7, "o/r"))
        self.assertEqual(gh.mutations(), ["create", "status-options", "add-issue-field", "view", "delete-workflow"])
        options = gh.body("status-options")["variables"]["options"]
        self.assertEqual(options[0], {"name": "Triage", "color": "GRAY", "description": ""})
        self.assertEqual([option.get("id") for option in options[1:]], ["f75ad846", "47fc9ee4", "98236657"])
        self.assertEqual(gh.boards["PVT_7"]["title"], "r")
        self.assertEqual([name for _, name, _ in gh.boards["PVT_7"]["workflows"]],
                         [name for _, name, _ in NEW_WORKFLOWS if name != "Item added to project"])

    def test_a_new_users_board_gets_its_own_priority_field_and_the_view_by_login(self):
        gh = FakeGh(owner_type="User", owner_login="me")
        run(gh, repo="me/r")
        self.assertIn("create-priority", gh.mutations())
        self.assertNotIn("issue-fields", gh.kinds())
        self.assertEqual([option["name"] for option in gh.body("create-priority")["variables"]["options"]],
                         ["Urgent", "High", "Medium", "Low"])
        view = next(args for args, given in gh.calls if gh.kind(args, given) == "view")
        self.assertEqual(rest_path(view), "users/me/projectsV2/7/views")

    def test_a_rerun_changes_nothing(self):
        gh = FakeGh()
        run(gh)
        gh.calls.clear()
        run(gh)
        self.assertEqual(gh.mutations(), [])

    def test_a_run_that_stopped_partway_finishes_on_a_rerun_with_the_same_board(self):
        gh = FakeGh(fail_once_on="view")
        with self.assertRaises(board.GhError):
            run(gh)
        gh.calls.clear()
        run(gh)
        self.assertEqual(gh.mutations(), ["view", "delete-workflow"])
        self.assertEqual(len(gh.boards), 1)

    def test_a_public_board_is_made_private(self):
        gh = FakeGh(boards=[FakeGh.new_board(3, "r", "o", public=True)])
        run(gh)
        self.assertIn("private", gh.mutations())
        self.assertNotIn("create", gh.mutations())
        self.assertFalse(gh.boards["PVT_3"]["public"])

    def test_boards_of_another_title_owner_or_closed_are_not_reused(self):
        gh = FakeGh(boards=[FakeGh.new_board(1, "other", "o"), FakeGh.new_board(2, "r", "someone"),
                            FakeGh.new_board(3, "r", "o", closed=True)])
        self.assertEqual(run(gh).project, 7 + 3)
        self.assertIn("create", gh.mutations())

    def test_two_linked_boards_with_the_repositorys_name_need_a_person(self):
        gh = FakeGh(boards=[FakeGh.new_board(1, "r", "o"), FakeGh.new_board(2, "r", "o")])
        with self.assertRaisesRegex(board.BoardError, "#1, #2"):
            run(gh)
        self.assertEqual(gh.mutations(), [])

    def test_a_board_that_still_differs_after_the_steps_stops_naming_it(self):
        with self.assertRaisesRegex(board.GhError, "no Board view"):
            run(FakeGh(ignore={"view"}))

    def test_the_default_branch_must_exist_before_anything_changes(self):
        gh = FakeGh()
        with self.assertRaisesRegex(board.BoardError, "push it first"):
            run(gh, default_branch="develop")
        self.assertEqual(gh.mutations(), [])

    def test_the_default_branch_is_set_after_the_board_and_only_when_it_differs(self):
        gh = FakeGh(branches=("main", "develop"))
        run(gh, default_branch="develop")
        self.assertEqual(gh.default_branch, "develop")
        self.assertEqual(gh.mutations()[-1], "default-branch")
        gh.calls.clear()
        run(gh, default_branch="develop")
        self.assertEqual(gh.mutations(), [])

    def test_the_config_is_written_when_absent_and_never_overwritten(self):
        folder = Path(tempfile.mkdtemp())
        run(FakeGh(), checkout=folder)
        written = (folder / ".task-board.json").read_text()
        self.assertEqual(board.parse_config(written), board.Config("o", 7, "o/r"))
        run(FakeGh(), checkout=folder)  # the same content: left as it is
        (folder / ".task-board.json").write_text('{"owner": "o", "project": 1, "repo": "o/r"}\n')
        with self.assertRaisesRegex(board.BoardError, "not overwriting"):
            run(FakeGh(), checkout=folder)
        self.assertIn('"project": 1', (folder / ".task-board.json").read_text())


class CommandLine(unittest.TestCase):
    def test_exit_status_and_the_check_after_setup(self):
        seen = []
        self.assertEqual(setup_board.main(["o/r"], gh=FakeGh(), check=lambda config: seen.append(config) or []), 0)
        self.assertEqual(seen, [board.Config("o", 7, "o/r")])
        two = FakeGh(boards=[FakeGh.new_board(1, "r", "o"), FakeGh.new_board(2, "r", "o")])
        self.assertEqual(setup_board.main(["o/r"], gh=two, check=lambda config: []), 1)
        self.assertEqual(setup_board.main(["o/r"], gh=FakeGh(fail_once_on="create"), check=lambda config: []), 2)

    def test_the_repository_must_be_owner_slash_name(self):
        with self.assertRaises(SystemExit):
            setup_board.parse_args(["r"])


@unittest.skipUnless(shutil.which("gh"), "gh is not installed")
class ZzRealGhAcceptsEveryCommand(unittest.TestCase):
    """As in test_board.py: every distinct command these tests produced, run through the real gh with its host on a
    closed local port and a dummy token, must get as far as dialling the port."""

    def test_zz_gh_parses_every_command_setup_issues(self):
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
        self.assertGreater(len(seen), 3)
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
