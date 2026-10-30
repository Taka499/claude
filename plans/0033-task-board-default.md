# Plan: the task board as the default for new projects, with its setup scripted

Status: **draft**, 2026-10-30. Open choices O1 and O2 below wait for the user.

## Goal

**D1 (the user, 2026-10-30): a new `tia-tools` project keeps its tasks on a GitHub board by default.** The board, the helper and the PR flow come from plans 0030 and 0031.

D1 first left out two kinds of project, and both reasons rested on the per-project fine-grained tokens:
- **projects under `Taka499`,** because those tokens cannot reach boards owned by a user account (plan 0030 D5);
- **private `tia-tools` repositories,** until plan 0030 D11 is settled.

**D2 (the user, 2026-10-30, widening D1): every new project keeps its tasks on a board by default,** whatever its owner (`Taka499` or `tia-tools`) and whether public or private.
- **Why both exclusions fall:** plan 0034 turned the sandbox off the same day, so `gh` runs with the user's own login and the tokens are unused. That login reaches boards owned by the user account and private repositories alike.
- **D2 holds only while the sandbox stays off.** Turning it back on brings back both limits:
  - sessions in `Taka499` projects could not reach their boards with a fine-grained token;
  - the rule "no private data on an owner's boards while a public token of that owner can write boards" (global `CLAUDE.md`'s `gh` bullet, which applies only with the sandbox on) would bar boards for private `tia-tools` repositories.

  Turning the sandbox back on must therefore revisit this plan.
- **Existing projects are not affected:** they keep what their `CLAUDE.md` says, `docs/BACKLOG.md` or a board, and `/backlog` keeps its fallback. Adopting a board in one of them is a separate ask: gkms-contest-ai (20 open items in `docs/BACKLOG.md`), jot, karasu, gakumas-supportcards.

Today a board takes about ten manual steps, most of them in GitHub's web UI (`skills/task-board/SKILL.md` § Setting up a project's board). This plan scripts what GitHub's API allows. What it does not allow is reduced to as few clicks as possible, and each one is checked by the helper afterwards.

## The evidence for D1

The first board was assessed on 2026-10-30: `tia-tools/gkms-hif-final-stats`, from 2026-10-28 18:07Z to 2026-10-30 07:05Z. The sources were its public issues, PRs and issue events, and its session transcripts.
- **What worked:**
  - nine of nine work issues closed through `Closes #N`, and moved to Done with no manual step;
  - seven follow-ups were filed into Triage as they were found;
  - the helper ran sandboxed with no permission prompt.
- **What was never exercised:** `ready` returned 0 every time, every Priority was the default, and the nine claims were never contested. One session worked through the issues one after another.
- **Two live bugs in `file`:**
  - `Content already exists in this project` on #12 and #15. The board's auto-add placed the issue first, although GitHub documents `addProjectV2ItemById` as returning the existing item;
  - a rejected issue URL after the repository's rename from gmks to gkms (#27).

## Facts the design rests on

Read 2026-10-30, by two research agents, from:
- docs.github.com;
- the public GraphQL schema (`schema.docs.graphql`);
- `github/rest-api-description`;
- gh 2.103.3's help and source.

**Automatable by API:**
- **Creating and linking a board:** `createProjectV2(ownerId, title, repositoryId)` creates a board and links it to the repository in one call.
- **Copying from a template:** `copyProjectV2` or `gh project copy` copies a board. A copy carries "views, custom fields, draft issues…, configured workflows (except any auto-add workflows), and insights". It drops items, collaborators, and repository and team links, so `linkProjectV2ToRepository` (or `gh project link`) follows.
- **Visibility:** `updateProjectV2(public: false)`, or `gh project edit --visibility PRIVATE`. The default visibility of a new or copied board is undocumented, so it is set every time.
- **Status options:** `updateProjectV2Field.singleSelectOptions` replaces the whole option list. Since 2026-04-23, an option's `id` keeps its identity, so existing items keep their values. Whether it accepts the built-in Status field, and keeps the order sent, is undocumented.
- **Priority:** the issue field is not shown on a new board until it is added, with `createProjectV2IssueField(projectId, issueFieldId)` or REST `POST /orgs/{org}/projectsV2/{n}/fields` with `issue_field_id`.
- **User accounts have no issue fields.** In the GraphQL schema, `Organization` and `Repository` have `issueFields` and `User` does not. Every REST issue-field path is under `/orgs/{org}/` or a repository's issue. A board owned by `Taka499` therefore needs Priority as a single-select field of the board itself: plan 0030's first design, before D20.
- **A Board view grouped by Status:** only REST `POST /orgs/{org}/projectsV2/{n}/views`, or `/users/{user_id}/projectsV2/{n}/views` for a user's board, can set the grouping (`layout: board`, `vertical_group_by`), and it can only create a view. GraphQL views take no grouping.
- **Templates:** only boards owned by an organization can be marked as a template (`markProjectV2AsTemplate`).
- **Workflows, read only:** `ProjectV2.workflows { name enabled }`. On a new board, "Item closed" and "Pull request merged" set Done, and "Item added" is off.
- **The default branch:** `gh repo edit --default-branch develop`. It needs repository admin, and `develop` must exist first.

**Web UI only:**
- **Workflows:** turning one on or off, and auto-add's repository and filter. The only workflow mutation is `deleteProjectV2Workflow`. GitHub's "Create custom automation flows" roadmap item was closed as not planned on 2024-11-20.
- **Auto-add:** never copied. GitHub Free allows one per board, and it never adds issues that existed before it was turned on.
- **Fine-grained tokens:** creating one, or adding a repository to one. GitHub's org token endpoints can only list, approve, deny or revoke, and only a GitHub App can call them. "All repositories" would also cover private `tia-tools` repositories and break the public/private split (plan 0029).

**Tokens:**
- a classic or OAuth token needs the `project` scope. The user's `gh` login has none: `gh auth status` on 2026-10-30 lists `admin:public_key`, `gist`, `read:org` and `repo`. `read:project` was refused on 2026-10-29, when a helper call ran outside the sandbox;
- **with the sandbox off** (plan 0034), every `gh` call uses that login. So `board.py` fails on every board read in gkms-hif-final-stats until the user runs `gh auth refresh -h github.com -s project` once;
- for fine-grained tokens, GitHub documents org Projects: write for the REST field and view endpoints, but gives no permission list per GraphQL mutation.

**Community tools:**
- **Terraform and Pulumi:** neither GitHub provider supports Projects v2 (`integrations/terraform-provider-github` #1681 has been open since 2023-05). PR #3541 is open.
- **Settings-as-code:** `safe-settings` and the Probot settings app have no board support.
- **`actions/add-to-project`** (v2.0.0, 2026-05) can replace auto-add. It needs a token with Projects write in a repository or org secret. On Free, an org secret reaches every public repository's workflows, and Projects write reaches every board of the organization.
- **Agent bootstrap repositories** follow the same pattern as this plan: create or copy the board, link it, set fields and views by API, then print the workflow steps no API can do.

## Proposed design

1. **A setup script beside the helper,** `skills/task-board/setup_board.py`: standard-library Python, tested like `board.py`, and sharing its GraphQL and REST code.
   - **It is idempotent:** it finds a board already linked to the repository before creating one. Each step reads its result back.
   - **It writes `.task-board.json`.** It prints each remaining manual step with its direct URL, then runs `board.py check`.
2. **O1, how the board is made (the user's choice):**
   - **(a) Built by the script (recommended):**
     1. `createProjectV2` with `repositoryId`;
     2. `updateProjectV2` private;
     3. the Status options Triage, Todo, In Progress, Done, keeping the existing IDs;
     4. Priority: on an organization's board, the organization's issue field; on a user's board, a single-select field `Priority` with Urgent, High, Medium, Low;
     5. a REST Board view grouped by Status.

     The board's whole configuration lives in this repository, reviewed and versioned. The default workflows already match what the helper needs. The same code serves both kinds of owner.
   - **(b) Copied from a private template board,** then linked and set private. Fewer calls, and settings beyond the defaults come along.
     - **Against it:** the configuration then lives in GitHub's UI, outside review, and what a copy keeps (the Status options, the grouping, each workflow's state, the Priority column) is not documented.
     - **Under D2:** only an organization can mark a template. A `Taka499` board would need either a copy across owners, which is untested, or a second template board kept in step with the first.
3. **O2, auto-add (the user's choice):**
   - **(a) Drop it, and let the helper reconcile (recommended).**
     - **How:** a step that adds every open issue of the repository that is not on the board, with no Status, so as Triage. It runs at the start of a session, next to `check`.
     - **Gains:** this removes the last web step on the board. It also removes the race behind the `Content already exists` failures.
     - **Cost:** an issue opened outside a session, by the user or by a stranger, reaches the board only when the next session starts. The assessment found the user does not look at the board between sessions.
   - **(b) Keep auto-add as one manual click per board.** The script prints the workflows page. `check` reads `workflows { name enabled }` and fails while "Auto-add to project" is off; it cannot read the filter or the repository.
   - **Not chosen:** `actions/add-to-project`. It needs a Projects-write token as a secret reachable by every public repository's workflows.
4. **The credential is the user's login,** with the `project` scope added once. With the sandbox off (plan 0034), sessions and the setup script use the same login, so no step per project adds a repository to a token.
   - **If the sandbox comes back,** the per-project token returns as one manual click per project: adding the repository to the `tia-tools-public` token, which no API can do. The script would print the URL, and `check`, run with that token, would fail until the click is done.
   - **Not chosen for that case:** a GitHub App. It would make adding a repository scriptable (`PUT /user/installations/{id}/repositories/{repo_id}`), but replaces plan 0027/0029's token design with a long-lived private key on disk and one-hour tokens minted for each session.
5. **Setup runs as one command with the user's login.** It creates the board and sets the Status options, Priority and the view.
   - **For a project that merges through PRs,** it also makes `develop` the default branch, which needs repository admin, so that `Closes #N` closes issues.
   - **A project that merges locally** keeps its default branch and closes issues with `done`.
   - `scaffold-project` step 7 already creates the repository with the same login.
6. **`scaffold-project`:** for every new repository, step 7 continues with the board setup.
   - **For PR projects,** it first creates `develop`, pushes it and makes it the default branch.
   - **The project's `CLAUDE.md`** gets the Tasks line, saying how it merges.
   - While the sandbox is off, no token folder goes in `.claude/settings.local.json`.
7. **The helper's two live bugs are fixed first:**
   - `file` treats `Content already exists` as the issue being on the board, and looks up its item;
   - `file` accepts the issue URL of a renamed repository, and tells the user to update `.task-board.json`.
8. **The helper reaches boards owned by a user account (D2).**
   - **Today:** `board.py` reads the board through `organization(login:)` and Priority through `/orgs/{org}/issue-fields`.
   - **The change:** it reads the board through whichever owner the repository has. On a user's board, it reads and writes Priority as the board's own single-select field, ranked in the board's order.
   - **Unchanged:** an organization's board keeps the issue field.
9. **Global `CLAUDE.md`:** the line on where a project's tasks live says that a new project gets a board by default, while an existing one keeps what its `CLAUDE.md` names. It also says D2 holds only while the sandbox is off.

## Verification

1. **A scratch test,** first, on one scratch board in `tia-tools` and one under `Taka499`, both deleted afterwards. It settles what is undocumented:
   - that the user's login with the `project` scope suffices for each mutation;
   - `updateProjectV2Field` on the built-in Status field, keeping order and IDs;
   - the REST Board view;
   - the default visibility;
   - the default workflows, read back;
   - for O1 (b): what a copy keeps;
   - on the user's board: the board-level Priority field, written and read back.

   The responses are captured as fixtures, as plan 0031 did.
2. **Tests:** the setup script's tests pass, and each is seen failing against a broken copy (global `CLAUDE.md` § Testing). The same goes for the two bug fixes, the user-owned board path and, under O2 (a), the reconcile step.
3. **A live run** on the next new repository:
   - `scaffold-project` through to `board.py check` passing;
   - one issue filed and claimed, and closed: by a PR's `Closes #N`, or by `done` in a project that merges locally (that path has not yet run live);
   - under O2 (a), an issue opened in the web UI appears in Triage at the next session.

   The first project under `Taka499` gets the same run.
4. **Not in this plan:**
   - moving gkms-hif-final-stats onto O2 (a) by turning its auto-add off;
   - adopting a board in gakumas-supportcards (no task list today, default branch `main`).

   Each is a separate ask.
