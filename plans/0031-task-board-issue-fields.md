# Plan: task-board on gh 2.103.3, with Priority as the organization's issue field

## Goal

The first real use of the `task-board` helper (plan 0030), on `tia-tools/gmks-hif-final-stats` and its board `tia-tools` project 1, failed on 2026-10-29 in two ways, before a single item was on the board:

1. **gh refuses `--format` together with `--field`.** Its message: `cannot use --format with --field or --field-id`. The helper listed the board's items with `gh project item-list … --field Status --field Priority --format json`, a fix from plan 0030 D18, so every step that lists items exited 2: `ready`, `claim`, `queue`, `release` and `done`. The project's session found the clash, on gh 2.103.3.

   **Correction (research, 2026-10-29):** this plan first blamed the move to 2.103.3. That was wrong. gh's source has the refusal since `--field` was added: v2.96.0 has no `--field`, while v2.97.0 and v2.103.0 both carry the line `"cannot use --format with --field or --field-id"` (`pkg/cmd/project/item-list/item_list.go`, fetched 2026-10-29). D18's call never worked on any gh release. Two things let it through:
   - Codex's first pass read `--field` in gh's help as what adds field values to JSON, and it only adds table columns;
   - the test double accepted any arguments.

   Running the real `gh` once with those exact arguments would have failed before any network call, without a token.
2. **The board's Priority is the organization's issue field, not a field of the board.** On the board it shows as a single-select field with no options, so the helper's check found no Priority options. Its values live on each issue, and its options and their order come from the organization.

The user chose to keep the organization's field (plan 0030 D20), and added the organization permission Issue Fields: Read-only to the public token. They also asked that the real responses be captured before the code changed. An assumption about `gh`'s output shape had just failed.

## What was measured (2026-10-29, gh 2.103.3)

Captured by the session in gmks-hif-final-stats, sandboxed with the public token, into `/tmp/claude-501/task-board-capture/`. No file holds a token string. All commands exited 0, except the one that shows the clash.
- **`gh project item-list 1 --owner tia-tools --field Status --field Priority --format json`:** exit 1, `cannot use --format with --field or --field-id`.
- **`gh project field-list 1 --owner tia-tools --format json`:** `Status` has the options `Triage`, `Todo`, `In Progress`, `Done`, in that order. `Priority` is a `ProjectV2SingleSelectField` with no `options` key.
- **`gh api /orgs/tia-tools/issue-fields`:** fields `Priority`, `Start date`, `Target date` and `Effort`, each with an integer `id`.
  - `Priority` is `single_select`, visible to `organization_members_only`, with options listed as High, Low, Medium, Urgent. Each carries a `"priority"` number: Urgent 1, High 2, Medium 3, Low 4.
  - `Effort` also has options named High, Medium and Low.
- **`gh api repos/tia-tools/gmks-hif-final-stats/issues/1/issue-field-values`:** `[]` for a new issue.
- **The GraphQL query for the board's items, asking for `fieldValueByName(name: "Status")`:** answered `{"data":{"organization":{"projectV2":{"items":{"pageInfo":{…},"nodes":[]}}}}}`.
- **`gh project item-list 1 --owner tia-tools --format json`,** without `--field`: `{"items":[],"totalCount":0}`. Whether it carries field values could not be seen on an empty board.
- **The board's workflows:**
  - on: "Auto-add to project", "Auto-close issue", "Item closed", "Item reopened", "Pull request linked to issue", "Pull request merged" and "Auto-add sub-issues to project";
  - off: "Item added to project".
- **GitHub's permission table for fine-grained tokens** (read 2026-10-29):
  - **Repository permission Issues:** write for `POST`/`PUT`/`DELETE …/issues/{n}/issue-field-values`, and read for `GET`;
  - **Organization permission Issue Fields:** read for `GET /orgs/{org}/issue-fields`, and write for creating, changing or deleting fields.
- **The REST reference for issue field values:** a single-select value is written by option name, `{"issue_field_values": [{"field_id": <id>, "value": "<name>"}]}`. A `GET` returns entries with `issue_field_id` and `single_select_option.name`.

## Research on stability (2026-10-29)

The user asked whether GraphQL could break as well. A research agent read GitHub's policies, changelogs, schemas and gh's source. Every point below is sourced, read 2026-10-29.
- **GraphQL:**
  - **Notice:** breaking changes come with at least three months' notice, and take effect only on 1 January, April, July or October (docs.github.com/en/graphql/overview/breaking-changes).
  - **GA:** the ProjectsV2 API has been GA since 2022-07-27. No change is scheduled for `projectV2`, `items`, `fieldValueByName`, `ProjectV2ItemFieldSingleSelectValue` or `updateProjectV2ItemFieldValue`, and the public schema marks none of them preview or deprecated.
  - **One silent case:** `fieldValueByName` returns the first field with that name, so a renamed Status field turns every value into null, which reads as Triage.
- **REST:**
  - **Versioned:** breaking changes ship only in a new `X-GitHub-Api-Version`, and the previous version is supported at least 24 months. `2022-11-28` ends on 2028-03-10.
  - **Default:** gh sends `2022-11-28` itself, overridable with `-H`.
  - **Previews:** GitHub "may change or discontinue Previews at any time without notice".
- **Issue fields** are **GA since 2026-07-02** (github.blog changelog), not in preview, as this plan and the conversation first assumed. GitHub's published REST description shows additive changes only from April to now. GraphQL equivalents exist and are GA: `Issue.issueFieldValues`, `setIssueFieldValue`, `Organization.issueFields`.
- **A REST API for Projects** has existed since 2025-09-11. GitHub states no stability phase for it, and its schema leaves an item's field values untyped (`additionalProperties: true`).
- **The gh CLI** has no user-facing stability policy, and its `gh project` subcommands changed in v2.97.0 and v2.98.0. Their JSON is gh's own shape, and `item-edit` and `item-add` only wrap the GraphQL mutations. `gh api` passes the request through as written.
- **The agent's recommendation:**
  - use GraphQL through `gh api graphql` for everything on the board: list, set Status, add an issue, read the Status field and its options. That leaves one contract, with three months' notice;
  - keep REST for issue fields, with `X-GitHub-Api-Version` passed explicitly;
  - fail closed on every shape the helper reads;
  - watch GitHub's changelog feed for Projects and Issues, and gh's releases feed.

## Design

Revised after the research, on the user's choice "All of it now", 2026-10-29. The first version of this fix still used four `gh project` subcommands. It was reviewed LGTM at 5c7005e, below, and then replaced.

- **The board only through GraphQL, via `gh api graphql`.** It is one contract: GA, breaking changes announced three months ahead, every field used checked against the public schema, none deprecated.
  - **`BOARD_QUERY`** asks for the board's `id`, its field `field(name: "Status")` with `__typename`, `id` and `options { id name }`, and the items 100 to a page. Each item comes with `fieldValueByName(name: "Status") { __typename … on ProjectV2ItemFieldSingleSelectValue { name } }` and its issue's `number`, `title`, `url` and `repository`.
  - **`SET_STATUS_MUTATION`** is `updateProjectV2ItemFieldValue`, with `singleSelectOptionId`. It must answer with the same item ID.
  - **`ADD_ITEM_MUTATION`** is `addProjectV2ItemById`. The issue's node ID comes from `GET repos/{repo}/issues/{n}`.
  - `gh project view`, `field-list`, `item-edit` and `item-add` are no longer used.
- **REST with the version named.** Every REST call sends `X-GitHub-Api-Version: 2022-11-28` itself, supported until at least 2028-03-10, so a change of `gh`'s default cannot move it. That covers the issue fields, their values, an issue's node ID and the list of versions.
- **Fail closed.** Any of these stops the run with exit 2, or exit 1 for the board's configuration, instead of being read as Triage or Medium:
  - a Status value that is not a named single-select option;
  - a missing, renamed or retyped Status field;
  - a missing option;
  - a Priority entry without an option name;
  - an option without a name;
  - a mutation that answers without an ID, or for another item;
  - GraphQL `errors`;
  - a page cursor that does not advance.
- **`check`, read-only.** It reads the board, the Priority field, the open issues and up to three issues' Priority, the account, `GET versions` and the headers of one REST call. It fails if the pinned version is no longer listed, and warns on `Deprecation` or `Sunset`. The skill has a session run it once before its first step.
- **A test that runs the real `gh`.** Every distinct command the other tests produced, 25 shapes covering all 15 kinds of call, is replayed through the installed `gh`. Its host is a closed local port and its token a dummy. `gh` checks flags, argument combinations and `--json` field names before it connects, so each must reach `dial tcp`. A refused argument fails the test, with nothing sent.
- **Unchanged:** Priority from the organization's issue field, ranked by its `"priority"` number and read and written per issue; claims, holders, blockers, reruns and step order.

## Changes

- `skills/task-board/board.py`:
  - the three GraphQL operations and the pinned REST version;
  - `parse_board_page`, `mutation_id`, `graphql_data`, `parse_priority_field`, `priority_value` (fails closed), `parse_headers` and `ready_candidates`;
  - `Board.graphql`, `rest`, `board`, `add_to_board`, `set_status`, `set_priority` and `check`;
  - `Gh.run` takes a request body.
- `skills/task-board/test_board.py`: 66 tests. The fixtures for the Status options and the organization's issue fields are trimmed from the captures. The last test replays every command through the real `gh`.
- `skills/task-board/SKILL.md`:
  - what Priority is;
  - the token's Issue Fields permission;
  - `check` as step 0;
  - exit 2 failing closed;
  - setup steps 4 and 7.
- Global `CLAUDE.md` and `README.md`: the token permission Issue Fields, Read-only, never write.

## Decision Log (2026-10-29)

- **Measure first** (the user). The responses above were captured before the helper changed, and two of them are the test fixtures. Plan 0030's fixtures had been the assumptions that failed.
- **GraphQL for the items, over `item-list` without `--field`.** Whether `item-list --format json` carries field values could not be seen on an empty board. Even if it does today, `--field`'s meaning has just changed under the helper. GraphQL asks for exactly the values the helper relies on.
- **The organization's Priority field, read-only on the organization side** (the user chose the field; read-only follows least privilege). Writing values needs only the Issues permission the token already has. Issue Fields write would let any session in the project change the organization's field definitions.
- **Rank by the options' `"priority"` number.** The captured options were listed out of order. Ranking by position would have made High the most urgent.
- **GraphQL for every board operation, REST pinned for issue fields, fail closed, `check`, and the real-`gh` test** (the user, "All of it now", after the research above). A rename or a shape change now stops the helper and names the cause, instead of quietly misreading the board.
- **Not built: a weekly job outside the helper** that diffs GitHub's public GraphQL schema and REST description for the exact fields used. The schema was checked by hand on 2026-10-29, below. The user can watch GitHub's changelog feed and `gh`'s release feed.
- **No ADR.** It is a fix to a helper, reversible.
- **Codex review of the revision, pass 1 at 820f98a: CHANGES REQUESTED.** Four findings, all accepted, fixed in the commit after 820f98a:
  - **Medium:** a missing `items`, `nodes`, `pageInfo` or `hasNextPage`, or `hasNextPage` without an `endCursor`, still read as an empty or shorter board. Now each stops the run.
  - **Medium:** a Priority value that is not one of the field's options was accepted and sorted last. Now it stops the run; `priority_value` takes the whole field.
  - **Low:** `gh api user` did not name the pinned REST version. Now it goes through the same REST call as the rest.
  - **Low:** the real-`gh` replay assumed local port 9 was closed. Now it takes a port the system has just handed out and taken back, and confirms a connection there is refused before replaying. If something answers, it skips rather than send the dummy token there. Where the sandbox forbids binding, it checks port 9 the same way; inside the sandbox even the connection is not permitted.

  68 tests, OK on 3.9.6 and 3.14.9; the replay ran, 25 shapes, nothing skipped. Each fix was seen failing against a broken copy:
  - a malformed page accepted;
  - more items without a cursor;
  - a Priority outside the options;
  - the login without the pinned version.
- **Codex review, one pass on `origin/master...HEAD` at 5c7005e: LGTM, no findings.** It confirmed:
  - the GraphQL handling: null Status, items that are not issues, paging with the loop guard, GraphQL errors, a null board, and `-F number=1` passing an integer;
  - the Priority handling: selection, ranking, reading by field ID, the request body on stdin, validation before any change, and Priority before Status;
  - that the unchanged safeguards and the texts still agree with the code.

  All 57 tests passed. No ref moved. The new files in `.git` were the automatic security review's markers for the commit (`sg-reviewed-shas`, `sg-reviewed-diffs`), not Codex's.

- **Codex review of the revision, pass 2 at e9881ba: CHANGES REQUESTED.** It confirmed pass 1's fixes, legitimate empty and last pages included. Two findings, both accepted:
  - **High:** a blocker whose state was anything but `OPEN` counted as closed, so a new or malformed state could make blocked work look ready. Now only `OPEN` and `CLOSED` are known, and any other state stops the run.
  - **Medium:** a Priority option without a `priority` number sorted last. GitHub documents the number as nullable, but the ready list's order rests on it. So an option without an integer one now stops the run, with a message to set the order in the organization's issue-field settings.
  - **Low:** the texts' claim of failing closed was overstated until these two. It holds now.
- **My own sweep of every remaining fallback in `board.py`,** after pass 2:
  - **Two more fixed:**
    - an issue without `blockedBy`, or with one of another shape, read as "no blockers", and now stops the run;
    - a comment by this account without `createdAt` sorted first, which could change who holds a claim, and now stops the run.
  - **Left as they are, because each only makes work look not ready:** an item whose content is missing (a redacted or draft item is skipped), a missing repository, a blocker without a state.
  - **Left lenient on purpose:** a missing title or creation date only affects the display, and the order among ready items.

  72 tests, OK on 3.9.6 and 3.14.9; the replay ran, 25 shapes, nothing skipped. Each fix was seen failing against a broken copy:
  - an unknown blocker state;
  - an unranked option;
  - a missing `blockedBy`;
  - a `blockedBy` of another shape;
  - an undated own comment.

- **Codex review of the revision, pass 3 at 87e93f1: CHANGES REQUESTED, one Low, accepted.** `SKILL.md` said a renamed Status field makes `check` exit 2; the helper raises a configuration error, exit 1. Fixed in the text.
  - **What the pass confirmed:**
    - pass 2's fixes reject nothing legitimate: empty blocker lists, lowercase states and integer priorities all pass;
    - each fallback kept only fails toward "not ready";
    - there is no remaining path where malformed input makes blocked, unqueued, claimed or closed work ready, changes who holds a claim, or sends a write to the wrong item or field.
  - **No fourth pass:** the fix is one sentence of the skill.

## Verification

- **The schema, checked 2026-10-29.** In GitHub's public GraphQL schema (docs.github.com/public/fpt/schema.docs.graphql, 1,561,946 bytes), every field and input the operations use exists, and none is `@deprecated`:
  - `Organization.projectV2(number: Int!)`;
  - `ProjectV2.id`, `field(name: String!)` and `items`;
  - `ProjectV2Item.id`, `fieldValueByName` and `content`;
  - `ProjectV2ItemFieldSingleSelectValue.name`;
  - `ProjectV2SingleSelectField.id` and `options`;
  - `ProjectV2SingleSelectFieldOption.id: String!` and `name: String!`;
  - the two mutations and their payloads, and their inputs: `projectId`, `itemId`, `fieldId`, `value.singleSelectOptionId: String`, `contentId`.

  The unions `ProjectV2FieldConfiguration`, `ProjectV2ItemFieldValue` and `ProjectV2ItemContent` (DraftIssue | Issue | PullRequest) hold the types the fragments name.
- **Tests, after the revision:** 66, OK on 3.9.6 and 3.14.9. The real-`gh` test replayed 25 shapes, 0 skipped. Seen failing against broken copies:
  - a `--json` field `gh` lacks, caught only by the real-`gh` test, the same kind of failure as the original bug;
  - a Status of another shape read leniently;
  - a missing Status field let through;
  - a Priority entry without a name let through;
  - REST calls without the pinned version;
  - a mutation answer for another item accepted;
  - `check` ignoring `Deprecation`/`Sunset`;
  - `check` ignoring an unlisted version.
- **Tests, first version:** `python3 -m unittest discover -s skills/task-board`, 57 tests, OK on 3.9.6 and 3.14.9. Each new part was seen failing against a broken copy:
  - Priority ranked by listed order;
  - another single-select field taken;
  - a missing Status read as Todo;
  - later pages not requested;
  - a Priority value taken from any field;
  - priorities not read for the ready candidates;
  - `file` setting Status before Priority.

  Without the stuck-cursor guard, its test runs until the time limit, so it cannot pass without it.
- **Still to capture, once issue #1 is on the board** and the user has set it to Todo and High: `issue-field-values` and the GraphQL items page again. Their shapes then become fixtures as well. The board did not add #1 on its own: auto-add was on, but nothing arrived within four minutes. The user checks the workflow's repository and filter.
- **Then, in a session in gmks-hif-final-stats:** `ready`, `claim`, the PR with `Closes #1`, the merge, and Done.

## The first live run (2026-10-29, after PR #46)

Run by the user and a session in gmks-hif-final-stats, against `tia-tools` project 1. Checked from this repository with unauthenticated reads of the public repository, and with the session's captures in `/tmp/claude-501/task-board-capture/`.
- **Auto-add:** it brought in nothing at first because the workflow pointed at the wrong repository; the user corrected it. Then a new issue, #2 "Auto-add test", arrived under No Status, and the user closed it.
  - GitHub's documentation adds a second condition (docs.github.com, "Adding items to your project automatically", read 2026-10-29): "When you enable the auto-add workflow, existing items matching your criteria will not be added". So the user added #1, created earlier, by hand.
  - `SKILL.md`'s setup step 5 now says both, and how to test auto-add with a new issue.
- **The helper on the real board:**
  - the user set #1 to Todo, Priority High;
  - the session's `claim` wrote `task-board claim: feature/adopt-task-board in ~/Developer/gmks-hif-final-stats…` on #1, as `Taka499`, at 19:22:28Z;
  - it then opened PR #3, "Adopt the task board", into `develop`, with a body starting `Closes #1`. The PR added `.task-board.json` and the board line to the project's `CLAUDE.md`.
- **The PR flow (D21 of plan 0030):** the user merged PR #3 into `develop`, the default branch (merge commit e3a266f), at 19:27:03Z. #1 closed as `completed` at 19:27:05Z. The user then saw #1 in Done on the board, moved there by the "Item closed" workflow. The board itself cannot be seen from this session.
- **Shapes the fixtures had assumed, now captured:**
  - **An issue's Priority value:** `{"issue_field_id": 43924878, "data_type": "single_select", "issue_field_name": "Priority", "value": 76872379, "single_select_option": {"id": 76872379, "name": "High", "color": "red"}}`. `value` is the option's numeric ID, not its name. The helper reads `single_select_option.name`, so it was right. It is now a fixture, with a test that fails if the helper reads `value` instead (seen failing).
  - **Comments from `gh issue view --json comments`:** `author.login`, `authorAssociation`, `body`, `createdAt`, as the helper expects.
- 73 tests, OK on 3.9.6 and 3.14.9.
- **Codex review of this follow-up, at 7c5cae0: LGTM, no findings.** The fixture matches the capture, the new test pins reading the option's name, and the plan separates what was observed from what was documented. The Done observation was added after the review; it is one sentence.
