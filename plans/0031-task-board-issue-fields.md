# Plan: task-board on gh 2.103.3, with Priority as the organization's issue field

## Goal

The first real use of the `task-board` helper (plan 0030), on `tia-tools/gmks-hif-final-stats` and its board `tia-tools` project 1, failed on 2026-10-29 in two ways, before a single item was on the board:

1. **gh 2.103.3 refuses `--format` together with `--field`.** Its message: `cannot use --format with --field or --field-id`. The helper listed the board's items with `gh project item-list … --field Status --field Priority --format json`, a fix from plan 0030 D18, so every step that lists items exited 2: `ready`, `claim`, `queue`, `release` and `done`. The helper's tests ran on gh 2.103.0, before Homebrew moved to 2.103.3 on the evening of 2026-10-28. The project's session found the clash.
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

## Design

- **The board's items through GraphQL, Status asked for by name.** The query `ITEMS_QUERY` asks for each item's `id`, `fieldValueByName(name: "Status")` and its issue's `number`, `title`, `url` and `repository`. It pages 100 at a time. A missing Status then truly means the item has none, which counts as Triage (plan 0030 D14). `gh project item-list` is no longer used. A page cursor that comes back twice is reported as an error, not looped on.
- **Priority from the organization's issue field `Priority`:**
  - its options come from `GET /orgs/{owner}/issue-fields`, ranked by each option's `"priority"` number, 1 the most urgent, not by listed order. An option without a number goes last;
  - the field is picked by name, so `Effort`, with the same option names, is never taken;
  - an issue's value is read with `GET …/issue-field-values`, only for the ready candidates;
  - it is written with `POST …/issue-field-values` by option name, the body passed on stdin (`--input -`);
  - the default for an issue without one stays the middle option (Medium).
- **Status is still written with `gh project item-edit`.** The field list still gives its IDs.
- **What does not change:** claims, holders, blockers, reruns and the order of each step. Priority goes before Status in `file` and `queue`, as before.

## Changes

- `skills/task-board/board.py`:
  - `parse_status_field`, `parse_priority_field`, `parse_item_page`, `priority_value` and `ready_candidates`;
  - `Board.items` through GraphQL, `priority_field`, `priority_of` and `set_priority`;
  - `Gh.run` takes a request body.
- `skills/task-board/test_board.py`: 57 tests. The fixtures for the field list and the organization's issue fields are trimmed from the captures.
- `skills/task-board/SKILL.md`: what Priority is, the token's Issue Fields permission, and setup step 4.
- Global `CLAUDE.md` and `README.md`: the token permission Issue Fields, Read-only, never write.

## Decision Log (2026-10-29)

- **Measure first** (the user). The responses above were captured before the helper changed, and two of them are the test fixtures. Plan 0030's fixtures had been the assumptions that failed.
- **GraphQL for the items, over `item-list` without `--field`.** Whether `item-list --format json` carries field values could not be seen on an empty board. Even if it does today, `--field`'s meaning has just changed under the helper. GraphQL asks for exactly the values the helper relies on.
- **The organization's Priority field, read-only on the organization side** (the user chose the field; read-only follows least privilege). Writing values needs only the Issues permission the token already has. Issue Fields write would let any session in the project change the organization's field definitions.
- **Rank by the options' `"priority"` number.** The captured options were listed out of order. Ranking by position would have made High the most urgent.
- **No ADR.** It is a fix to a helper, reversible.
- **Codex review, one pass on `origin/master...HEAD` at 5c7005e: LGTM, no findings.** It confirmed:
  - the GraphQL handling: null Status, items that are not issues, paging with the loop guard, GraphQL errors, a null board, and `-F number=1` passing an integer;
  - the Priority handling: selection, ranking, reading by field ID, the request body on stdin, validation before any change, and Priority before Status;
  - that the unchanged safeguards and the texts still agree with the code.

  All 57 tests passed. No ref moved. The new files in `.git` were the automatic security review's markers for the commit (`sg-reviewed-shas`, `sg-reviewed-diffs`), not Codex's.

## Verification

- **Tests:** `python3 -m unittest discover -s skills/task-board`, 57 tests, OK on 3.9.6 and 3.14.9. Each new part was seen failing against a broken copy:
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
