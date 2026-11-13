# Plan: a Needs you column and a needs-you label for the user's jobs

## Goal

The user said on 2026-11-13 that, working a board with no coordinating session, they cannot see which items are theirs. A job for the user (plan 0036: decide, approve, capture, run) was filed into Todo, beside the work sessions pick up, with no label and no assignee. Only its hidden task-board block marked it as a job. The attention page reads that block, but only projects that name a `page` have one, so elsewhere the session's reply was the only place a job showed.

**Measured the same day:**
- **Jobs are filed without a coordinator.** In 14 days of transcripts, gkms-memomemo's sessions ran `ask` 60 times and `answer` 49 times. It has no page.
- **On the board they look like work.** gkms-memomemo's Todo held #103, a session's work, and #104, the user's decision about it, with nothing to tell them apart.

The user chose the column, and the label with it. Making a coordinating session the default was not chosen: the page is what lists jobs, and the helper already draws it from any session.

## Decisions

**D1. Each Status has one side to move it.** `Needs you` joins the Status options, first:

| Status | Whose move |
|---|---|
| Needs you | the user: answer the job |
| Triage | the user: accept or reject |
| Todo | a session: claim it |
| In Progress | a session: finish it |
| Done | no one |

A job never passes through In Progress: it goes from filed to closed on the user's answer. So Todo holds only work a session may claim.
- Rejected: an `Owner` field beside Status. A second field can disagree with the column, and the Board view groups by one field.
- Rejected: the page in every project. It is a file per checkout, read apart from the board the user already opens.

**D2. The block still decides what a job is.** The column and the label show it; neither is read to decide anything. `ready`, `answer` and the page work as before. So an issue the user moves to Needs you by hand is not a job, and no step picks it up.

**D3. Every job also carries the label `needs-you`.** A column belongs to one board, and the user has six. One search lists every repository's open jobs: `is:open label:needs-you org:tia-tools`. Plan 0030 D5 rejected labels as the record of Status, because a label and a column drift apart. This label is set once at filing and never changes, and the job closes on its answer, so there is nothing to drift.

**D4. `sync` settles jobs.** It moves an open job found in Triage or Todo to Needs you, and labels one that lacks the label. That carries over the jobs filed before this change, and puts back one a hand moved. A job in any other Status is left where it is. `check` names what `sync` would settle, and changes nothing.

**D5. A board without the option stops every step,** as a missing Triage does, with a message naming `setup_board.py`. A fallback to Todo would bring back the two cases this plan removes.
- **The cost:** every board needs the option before this merges, since the merge deploys the helper. The earlier helper is unaffected by the extra option, so the boards go first.

## Changes

`skills/task-board/board.py`:
- **`STATUSES`** gains `Needs you`, first. A board lacking it stops with exit 1 (D5).
- **`ask`** creates the label where the repository lacks it, files the issue with it, and sets Needs you. The label comes first, because `gh issue create` refuses a label the repository does not have.
- **`sync`** settles jobs (D4), and returns what it settled beside what it added. An issue list without labels stops the run: read as unlabelled, every job would be labelled again on each `sync`.
- **`check`** warns for each job `sync` would settle.

`skills/task-board/setup_board.py`: the option list puts Needs you first, in red. The options already there keep their IDs.

`skills/task-board/SKILL.md` and `CLAUDE.md` § General: a job goes to Needs you with the label; the search that lists every repository's jobs.

## Verification

- **`python3 -m unittest discover -s skills/task-board`:** 195 tests.
  - **Shown to catch a break:** each of 15 rules was broken in turn, and each break failed at least one test. Among them: `ask` filing into Todo, or without the label; `sync` not moving a job, moving one in In Progress, or settling an issue that is not a job; a label list read as empty; the option not required.
  - **The real `gh` accepts every command** the tests produce, the three new ones included (`label list`, `label create`, `issue edit --add-label`).
- **On the scratch board `tia-tools` #9 (private), 2026-11-13:**
  - **Before setup,** `check` stopped with exit 1, naming the missing option and `setup_board.py`.
  - **Setup** added `Needs you` with a new ID. Triage, Todo, In Progress and Done kept theirs, and the three items kept their Status.
  - **`ask`** created the label, and filed #4 in Needs you with it.
  - **A job as filed before this change:** #4 was put in Todo and its label removed, by hand. `check` warned, `ready` listed nothing, `sync` moved and labelled it, and a second `sync` found nothing.
  - **`gh search issues --label needs-you --state open --owner tia-tools --owner Taka499`** listed it.
  - **#4 was then closed by the session,** with a comment saying it was a test, not answered by the user.

## Rollout

1. **The five other boards get the option first** (done 2026-11-13: the user ran it, and all six boards were read back with Needs you, Triage, Todo, In Progress, Done)**:** `setup_board.py tia-tools/<repo>` for gkms-hif-final-stats, gkms-memomemo, gakumas-supportcards, gkms-contest-ai and gkms-library. The user runs these: a session's attempt to change five live boards in one run was refused by the permission classifier.
2. **The merge.**
3. **Each project's next `sync`,** which every session runs at its start, moves its open jobs and labels them.

A project still on a board without the option after the merge sees every step stop with the message of D5, and step 1 for its repository fixes it.

**Found during the build:** `~/.claude/skills/task-board` is a link to the main checkout's working tree, so a branch checked out there is deployed before it merges. For at most 6 minutes (the branch was checked out there from 09:58 to 10:04 JST, by the reflog) the unmerged helper was live, and would have stopped a step on any of the five boards. The branch moved to a worktree of its own, and the main checkout went back to `master`.

## Codex review (2026-11-13)

`/codex-review` on the branch's whole diff at `0552f35`, in a snapshot: **CHANGES REQUESTED, one LOW, accepted.**
- **The finding:** `SKILL.md` said `sync` "puts both back on a job that lost one". It moves a job only out of Triage or Todo, and never one whose item is archived.
- **The fix:** the sentence now states those limits. Only text changed, so the review was not run again.
- **Confirmed by the pass:** repository scoping and `block_of` keep `sync` from moving a stranger's issue or a non-job; the orderings in `ask` and `sync` are safe and finished by a rerun; setup keeps each existing option's ID, colour and description; the new tests assert what their names say.
- **The sandbox check:** the skill's script printed `SANDBOX NOT SHOWN`, because the log's first line was `Reading additional input from stdin...` and the script wants the `OpenAI Codex v…` banner there. The header under the banner read `approval: never` and `sandbox: read-only`, and the canary's two writes were refused. Nothing was written in the worktree and no ref moved; the main checkout's `.git/index` changed, with nothing else in `.git`.
