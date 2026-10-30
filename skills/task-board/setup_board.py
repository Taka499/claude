#!/usr/bin/env python3
"""Set up a repository's task board, as the task-board skill needs it, and check it. Plan 0033 in the Taka499/claude
repo records why each step is what it is, and what GitHub answered when each was measured on 2026-10-30.

    python3 -I setup_board.py OWNER/REPO [--checkout PATH] [--default-branch develop]

Every step reads the board first and changes only what differs, so a rerun finishes a run that stopped partway and
changes nothing on a board already set up:
1. the board: the one linked to the repository and titled with its name, or a new one, created linked to it;
2. private;
3. Status options Triage, Todo, In Progress, Done in that order, keeping the IDs of the options already there, so
   no item loses its Status (any other option is kept, after them);
4. Priority: on an organization's board, the organization's issue field; on a user's board, which has no issue
   fields, a single-select field of the board with Urgent, High, Medium, Low;
5. a Board view with Status as its columns;
6. the workflow "Item added to project" deleted while it is on: it sets Todo on every item added, so nothing would
   wait in Triage, and no API can turn it off (D6). GitHub's auto-add is never turned on: the helper's `sync` puts
   the repository's open issues on the board instead (D4);
7. with --default-branch, the repository's default branch, for a project whose PRs close issues with `Closes #N`
   (the branch must already be pushed);
8. with --checkout, `.task-board.json` written there, unless one with other content is already there;
then board.py's own `check`, read-only.

It needs gh logged in with the `project` scope, and admin on the repository for --default-branch. Exit status: 0
done, 1 bad usage or a board that cannot be set up without a person's decision, 2 gh failed or answered in an
unexpected shape. Tests: python3 -m unittest discover -s skills/task-board
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import board  # beside this file
from board import (CONFIG_FILE, ITEM_ADDED_WORKFLOW, ORGANIZATION, PRIORITY_FIELD, STATUS_FIELD, STATUSES, USER,
                   BoardError, Config, Gh, GhError, graphql_data, mutation_id)

BOARD_LAYOUT = "BOARD_LAYOUT"
NEW_OPTION_COLOR = "GRAY"
# A user's board's own Priority, most urgent first: the names of the organization's issue field, so both read alike.
USER_PRIORITIES = (("Urgent", "RED"), ("High", "ORANGE"), ("Medium", "YELLOW"), ("Low", "GRAY"))

REPO_QUERY = """query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id nameWithOwner
    defaultBranchRef { name }
    owner { __typename id login }
    projectsV2(first: 50) {
      nodes { id number title closed owner { __typename ... on Organization { login } ... on User { login } } }
    }
  }
}"""
CREATE_MUTATION = """mutation($owner: ID!, $title: String!, $repository: ID!) {
  createProjectV2(input: {ownerId: $owner, title: $title, repositoryId: $repository}) { projectV2 { id number } }
}"""
# The fields are listed, not asked for with `field(name:)`, which answers a field the board lacks (Priority, on a new
# board) with an error instead of null (measured 2026-10-30).
SETUP_QUERY = """query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2 {
      id number public
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2FieldCommon { name }
          ... on ProjectV2SingleSelectField { id databaseId isIssueField options { id name color description } }
        }
      }
      views(first: 50) {
        nodes { layout verticalGroupByFields(first: 5) { nodes { ... on ProjectV2FieldCommon { name } } } }
      }
      workflows(first: 50) { nodes { id name enabled } }
    }
  }
}"""
PRIVATE_MUTATION = """mutation($id: ID!) {
  updateProjectV2(input: {projectId: $id, public: false}) { projectV2 { id } }
}"""
STATUS_OPTIONS_MUTATION = """mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id } }
  }
}"""
ISSUE_FIELDS_QUERY = """query($org: String!) {
  organization(login: $org) {
    issueFields(first: 50) { nodes { __typename ... on IssueFieldSingleSelect { id name } } }
  }
}"""
ADD_ISSUE_FIELD_MUTATION = """mutation($project: ID!, $field: ID!) {
  createProjectV2IssueField(input: {projectId: $project, issueFieldId: $field}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id } }
  }
}"""
CREATE_PRIORITY_MUTATION = """mutation($project: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  createProjectV2Field(input: {projectId: $project, dataType: SINGLE_SELECT, name: "Priority",
                               singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id } }
  }
}"""
DELETE_WORKFLOW_MUTATION = """mutation($id: ID!) {
  deleteProjectV2Workflow(input: {workflowId: $id}) { deletedWorkflowId }
}"""


@dataclass(frozen=True)
class Repository:
    id: str
    name_with_owner: str
    default_branch: str
    owner_type: str
    owner_id: str
    owner_login: str
    boards: tuple  # linked boards: dicts with id, number, title, closed, owner


@dataclass(frozen=True)
class SetupState:
    project_id: str
    number: int
    public: bool
    status: dict  # id, databaseId, options [{id, name, color, description}]
    priority: object  # the board's field named Priority, or None
    views: tuple  # (layout, (names of its column fields)) per view
    workflows: tuple  # (id, name, enabled) per workflow


# ---- pure functions -------------------------------------------------------------------------------------------------

def parse_repository(response_json: str) -> Repository:
    repository = graphql_data(response_json).get("repository")
    if not repository:
        raise BoardError("no such repository, or the login cannot read it")
    owner = repository.get("owner") or {}
    if owner.get("__typename") not in (ORGANIZATION, USER):
        raise GhError(f"the repository's owner is a {owner.get('__typename')!r}, not an organization or a user")
    if not all(isinstance(value, str) and value for value in (repository.get("id"), repository.get("nameWithOwner"),
                                                              owner.get("id"), owner.get("login"))):
        raise GhError("the repository came back without its ID, its name or its owner's ID and login")
    nodes = (repository.get("projectsV2") or {}).get("nodes")
    if not isinstance(nodes, list):
        raise GhError("the repository's boards came back without a list")
    for node in nodes:  # which board to reuse rests on every one of these, so none may be guessed
        if not (isinstance(node, dict) and isinstance(node.get("id"), str) and node["id"]
                and isinstance(node.get("number"), int) and not isinstance(node["number"], bool)
                and isinstance(node.get("title"), str) and isinstance(node.get("closed"), bool)
                and isinstance((node.get("owner") or {}).get("login"), str)):
            raise GhError(f"a board linked to the repository came back in an unexpected shape: {node!r}")
    boards = tuple({"id": node["id"], "number": node["number"], "title": node["title"], "closed": node["closed"],
                    "owner": node["owner"]["login"]} for node in nodes)
    return Repository(repository["id"], repository["nameWithOwner"], (repository.get("defaultBranchRef") or {})
                      .get("name", ""), owner["__typename"], owner["id"], owner["login"], boards)


def existing_board(repository: Repository, title: str):
    """The open board linked to the repository, owned by its owner and titled `title`, or None. Two of them would
    leave the choice to a person."""
    found = [entry for entry in repository.boards if entry["title"] == title and not entry["closed"]
             and entry["owner"] == repository.owner_login]
    if len(found) > 1:
        raise BoardError(f"{len(found)} open boards titled {title!r} are linked to {repository.name_with_owner}"
                         f" (#{', #'.join(str(entry['number']) for entry in found)}); close or rename all but one")
    return found[0] if found else None


def parse_setup(response_json: str) -> SetupState:
    node = graphql_data(response_json).get("node")
    if not node or not node.get("id"):
        raise GhError("the board came back empty")
    fields = board.fields_by_name(node)
    status = fields.get(STATUS_FIELD)
    if not status or status.get("__typename") != "ProjectV2SingleSelectField" or not status.get("options"):
        raise BoardError(f"the board has no single-select field {STATUS_FIELD!r} with options; was it renamed?")
    options = status["options"]
    if not all(isinstance(option, dict) and isinstance(option.get("id"), str) and option["id"]
               and isinstance(option.get("name"), str) and option["name"] for option in options) \
            or len({option["name"] for option in options}) != len(options) \
            or not isinstance(status.get("databaseId"), int) or not isinstance(status.get("id"), str):
        raise GhError(f"the board's {STATUS_FIELD} field came back without IDs, or with an option without an ID or"
                      f" a name, or two options of one name")
    for key, kind in (("views", "views"), ("workflows", "workflows")):
        if not isinstance((node.get(key) or {}).get("nodes"), list):
            raise GhError(f"the board's {kind} came back without a list")
    views = tuple((view.get("layout"), tuple(field.get("name") for field in
                                             (view.get("verticalGroupByFields") or {}).get("nodes") or []))
                  for view in node["views"]["nodes"])
    workflows = tuple((flow.get("id"), flow.get("name"), flow.get("enabled")) for flow in node["workflows"]["nodes"])
    if not all(isinstance(name, str) and isinstance(enabled, bool) for _, name, enabled in workflows):
        raise GhError("the board's workflows came back without names and enabled flags")
    if not isinstance(node.get("public"), bool):
        raise GhError("the board came back without its visibility")
    return SetupState(node["id"], node["number"], node["public"], status, fields.get(PRIORITY_FIELD), views, workflows)


def status_options(options: list):
    """The option list that puts Triage, Todo, In Progress and Done first, in that order, or None if they already
    are. Options already there keep their ID, colour and description, so items keep their Status; any other option
    is kept, after them."""
    names = [option["name"] for option in options]
    if names[:len(STATUSES)] == list(STATUSES):
        return None
    by_name = {option["name"]: option for option in options}

    def given(option: dict) -> dict:
        return {"id": option["id"], "name": option["name"], "color": option.get("color") or NEW_OPTION_COLOR,
                "description": option.get("description") or ""}

    wanted = [given(by_name[name]) if name in by_name else {"name": name, "color": NEW_OPTION_COLOR, "description": ""}
              for name in STATUSES]
    return wanted + [given(option) for option in options if option["name"] not in STATUSES]


def priority_step(owner_type: str, field) -> str:
    """What the board's Priority needs: "ok", "add-issue-field" (an organization's) or "create-board-field" (a
    user's). A field named Priority of the wrong kind needs a person, since replacing it would drop its values."""
    if field is None:
        return "add-issue-field" if owner_type == ORGANIZATION else "create-board-field"
    if field.get("__typename") != "ProjectV2SingleSelectField":
        raise BoardError(f"the board has a {PRIORITY_FIELD!r} field that is a {field.get('__typename')}; delete or"
                         f" rename it, then rerun")
    if owner_type == ORGANIZATION and field.get("isIssueField") is not True:
        raise BoardError(f"the board's {PRIORITY_FIELD!r} is a field of the board, not the organization's issue"
                         f" field; delete or rename it, then rerun")
    if owner_type == USER and (field.get("isIssueField") is not False or not field.get("options")):
        raise BoardError(f"the board's {PRIORITY_FIELD!r} field has no options; delete it, then rerun")
    return "ok"


def issue_field_id(response_json: str) -> str:
    """The node ID of the organization's single-select issue field Priority."""
    nodes = ((graphql_data(response_json).get("organization") or {}).get("issueFields") or {}).get("nodes")
    if not isinstance(nodes, list):
        raise GhError("the organization's issue fields came back without a list")
    for node in nodes:
        if node.get("__typename") == "IssueFieldSingleSelect" and node.get("name") == PRIORITY_FIELD and node.get("id"):
            return node["id"]
    raise BoardError(f"the organization has no single-select issue field {PRIORITY_FIELD!r}")


def has_board_view(views) -> bool:
    return any(layout == BOARD_LAYOUT and STATUS_FIELD in columns for layout, columns in views)


def item_added_workflows(workflows) -> list:
    """IDs of the "Item added to project" workflows that are on."""
    return [flow_id for flow_id, name, enabled in workflows if name == ITEM_ADDED_WORKFLOW and enabled]


def config_text(owner: str, project: int, repo: str) -> str:
    return json.dumps({"owner": owner, "project": project, "repo": repo}) + "\n"


# ---- gh at the edge ---------------------------------------------------------------------------------------------

class Setup:
    def __init__(self, gh: Gh, say=print):
        self.gh, self.say = gh, say

    def graphql(self, query: str, **variables) -> str:
        """`gh api graphql` with the query and variables as a JSON body on stdin, so lists and integers keep their
        types."""
        return self.gh.run("api", "graphql", "--input", "-", input=json.dumps({"query": query,
                                                                                  "variables": variables}))

    def rest(self, path: str, *extra: str) -> str:
        return self.gh.run("api", "-H", board.REST_HEADER, *extra, path)

    def state(self, project_id: str) -> SetupState:
        return parse_setup(self.graphql(SETUP_QUERY, id=project_id))

    def run(self, repo: str, checkout: Path | None, default_branch: str | None) -> Config:
        owner, _, name = repo.partition("/")
        repository = parse_repository(self.graphql(REPO_QUERY, owner=owner, name=name))
        if default_branch:  # before anything changes: a branch not yet pushed stops the run here
            try:
                self.rest(f"repos/{repository.name_with_owner}/branches/{default_branch}")
            except GhError as error:
                raise BoardError(f"{repository.name_with_owner} has no branch {default_branch!r} on GitHub; push it"
                                 f" first ({error})") from None
        found = existing_board(repository, name)
        if found:
            project_id = found["id"]
            self.say(f"board {repository.owner_login} #{found['number']} is linked to {repository.name_with_owner}")
        else:
            created = self.graphql(CREATE_MUTATION, owner=repository.owner_id, title=name, repository=repository.id)
            project_id = mutation_id(created, "createProjectV2", "projectV2", "id")
            self.say(f"created a board for {repository.name_with_owner}, linked to it")
        state = self.state(project_id)
        if state.public:
            mutation_id(self.graphql(PRIVATE_MUTATION, id=project_id), "updateProjectV2", "projectV2", "id")
            self.say("made the board private")
        options = status_options(state.status["options"])
        if options is not None:
            mutation_id(self.graphql(STATUS_OPTIONS_MUTATION, field=state.status["id"], options=options),
                        "updateProjectV2Field", "projectV2Field", "id")
            self.say(f"{STATUS_FIELD} options set: {', '.join(option['name'] for option in options)}")
        step = priority_step(repository.owner_type, state.priority)
        if step == "add-issue-field":
            field = issue_field_id(self.graphql(ISSUE_FIELDS_QUERY, org=repository.owner_login))
            mutation_id(self.graphql(ADD_ISSUE_FIELD_MUTATION, project=project_id, field=field),
                        "createProjectV2IssueField", "projectV2Field", "id")
            self.say(f"added the organization's issue field {PRIORITY_FIELD}")
        elif step == "create-board-field":
            mutation_id(self.graphql(CREATE_PRIORITY_MUTATION, project=project_id, options=[
                {"name": option, "color": color, "description": ""} for option, color in USER_PRIORITIES]),
                "createProjectV2Field", "projectV2Field", "id")
            self.say(f"created the board's own {PRIORITY_FIELD} field: {', '.join(n for n, _ in USER_PRIORITIES)}")
        if not has_board_view(state.views):
            kind = "orgs" if repository.owner_type == ORGANIZATION else "users"  # the user path takes the login
            self.gh.run("api", "-H", board.REST_HEADER, "--method", "POST",
                        f"{kind}/{repository.owner_login}/projectsV2/{state.number}/views", "--input", "-",
                        input=json.dumps({"name": "Board", "layout": "board",
                                          "vertical_group_by": [state.status["databaseId"]]}))
            self.say(f"added a Board view with {STATUS_FIELD} as its columns")
        for flow_id in item_added_workflows(state.workflows):
            mutation_id(self.graphql(DELETE_WORKFLOW_MUTATION, id=flow_id), "deleteProjectV2Workflow",
                        "deletedWorkflowId")
            self.say(f"deleted the workflow {ITEM_ADDED_WORKFLOW!r}, which set Todo on every item added")
        self.verify(project_id, repository.owner_type)
        if default_branch and repository.default_branch != default_branch:
            self.rest(f"repos/{repository.name_with_owner}", "--method", "PATCH", "-f",
                      f"default_branch={default_branch}")
            self.say(f"made {default_branch} the default branch of {repository.name_with_owner}")
        config = Config(repository.owner_login, state.number, repository.name_with_owner)
        if checkout is not None:
            self.write_config(checkout / CONFIG_FILE, config)
        return config

    def verify(self, project_id: str, owner_type: str) -> None:
        """Reads the board back: every step's result, or the run stops naming what is still wrong."""
        state = self.state(project_id)
        wrong = []
        if state.public:
            wrong.append("it is public")
        if status_options(state.status["options"]) is not None:
            wrong.append(f"its {STATUS_FIELD} options are not {', '.join(STATUSES)} first")
        if priority_step(owner_type, state.priority) != "ok":
            wrong.append(f"it has no {PRIORITY_FIELD}")
        if not has_board_view(state.views):
            wrong.append(f"it has no Board view grouped by {STATUS_FIELD}")
        if item_added_workflows(state.workflows):
            wrong.append(f"its workflow {ITEM_ADDED_WORKFLOW!r} is still on")
        if wrong:
            raise GhError(f"after setting up, the board still differs: {'; '.join(wrong)}. Rerun to finish")

    def write_config(self, path: Path, config: Config) -> None:
        text = config_text(config.owner, config.project, config.repo)
        if path.exists():
            if path.read_text() != text:
                raise BoardError(f"{path} already holds {path.read_text().strip()}, not {text.strip()};"
                                 f" not overwriting it")
            return
        path.write_text(text)
        self.say(f"wrote {path}")


# ---- command line -----------------------------------------------------------------------------------------------

def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="setup_board.py", description="Set up a repository's task board.")
    parser.add_argument("repo", help="OWNER/REPO")
    parser.add_argument("--checkout", type=Path, help="the repository's checkout, to write .task-board.json into")
    parser.add_argument("--default-branch", help="make this pushed branch the default (projects merging by PR)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        parser.error(f"the repository must be OWNER/REPO, not {args.repo!r}")
    if args.checkout is not None and not args.checkout.is_dir():
        parser.error(f"--checkout {args.checkout} is not a folder")
    return args


def main(argv: list, gh: Gh | None = None, check=None) -> int:
    """`check` is board.py's read-only check of the finished board; tests replace it."""
    try:
        args = parse_args(argv)
        gh = gh or Gh()
        config = Setup(gh).run(args.repo, args.checkout, args.default_branch)
        print(f"board {config.owner} #{config.project} is set up for {config.repo}; checking it with board.py:")
        for line in (check or (lambda found: board.Board(found, gh).check()))(config):
            print(line)
        return 0
    except BoardError as error:
        print(f"setup_board.py: {error}", file=sys.stderr)
        return 1
    except GhError as error:
        print(f"setup_board.py: {error}", file=sys.stderr)
        return 2
    except (KeyError, ValueError, TypeError, IndexError, AttributeError) as error:
        print(f"setup_board.py: unexpected output from gh ({type(error).__name__}: {error})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
