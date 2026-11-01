# Plan: jobs for the user and an attention page on the task board

## Goal

gkms-contest-ai runs one coordinating session and up to four worker sessions, each worker in a worktree of its own. Its board is a local JSON file, written by a project script and rendered to a Markdown page. Its rules live in instruction prose. A review of the coordinator's transcripts from 2026-10-24 to 11-01 found four failures:

1. **Decisions the user never saw.**
   - **Done unless vetoed.** The coordinator settled calls as "done unless vetoed by the next window", with two windows a day. No window ever fired, since nothing woke the coordinator at those times. The calls piled up in one free-text note of about 20,000 characters.
   - **The largest call.** A worker put a question to the user with a decision page, and two minutes later the coordinator answered it itself. That cut part of a planned test. The user reversed it four hours later, after reading the note.
2. **Rules lost at compaction.**
   - **A corrected flag:** a flag the user corrected recurred 13 times, starting 14 minutes after a compaction.
   - **Hand edits:** the board was edited by hand 7 times, 5 of them for lack of a command.
   - **A dropped review:** a review the user had dropped was demanded 3 times.
3. **Hard to read.**
   - **Length:** 7 of 155 final replies kept to the 5-line limit; the median was 12 lines.
   - **Shorthand:** the user asked about 10 times what something meant, 2 of those about bare IDs.
4. **Workers replaced too often:** 43 replacements in 8 days, one worker 5 times in 3.5 hours. None cited the context limit the rule names.

**The user's aim:** a page that saves their attention. They should never have to open an issue to follow progress or to learn what they need to do. It should use the GitHub board that every project can now have (plan 0033), and keep no record in a form as weak as free Markdown.

The full evidence, with the project's private detail, stays in that project (D22).

## Decisions (grilled with the user, 2026-11-01)

**What reaches the user**
- **D4 What the coordinator may decide alone.** Anything except a worker's question that comes with a decision page; that question is always the user's job. Each of the coordinator's own calls shows as a "coord decided" line with its reason. This replaces "done unless vetoed" and its windows.
  - Rejected: also routing scope changes, since the coordinator would classify its own calls, the judgement that failed.
  - Rejected: routing everything beyond the plan, which would flood the page.
  - Accepted risk: a high-stakes call no worker raises is seen only afterwards.
- **D20 Who files that question.** The worker files the decide job itself with the helper, from its worktree, and it holds up the worker's own issue.
  - **Once filed,** only the user's words close it (D8, D21).
  - **Whether to file** stays the worker's judgement, as writing a decision page was. The worker's session card carries the rule: "a question for the user is filed with `ask` before it is sent to anyone".
  - Accepted risk: the coordinator can still answer a worker by message before any job exists.
  - Rejected: the coordinator filing it.
  - Rejected: the coordinator rewriting the worker's lines.
- **D5 Worker plans.** The coordinator approves them, and each approval shows as a "coord decided" line. A question a plan raises for the user goes through D20.
  - Rejected: the user approving every plan.
  - Rejected: the user approving only plans that start a new goal.

**How a job is held**
- **D6 One issue per job.**
  - **Kinds:** every job for the user is its own issue, marked with its kind: decide; approve (a merge, with its push); capture (data the user collects); or run (a command only the user can run).
  - **Blocking:** the work it holds up is "blocked by" it, through GitHub's own dependency.
  - **Status:** a job goes straight to Todo. It is the user's own work, so the Triage gate, which keeps sessions from starting work the user has not queued, does not apply to it. `ready` and `claim` never list or take a job.
  - Cost accepted: about 1–2 extra issues a day for merge approvals.
- **D7 Where an issue's lines live.** In a JSON block in the issue's text, written by the helper with a readable rendering above it:
  - **a job:** its kind, the options each with its cost, the recommendation and why, and how to answer;
  - **work:** the goal it serves, step n of m, now, and next.

  Every write checks the block against a schema.
  - **Reading:** `ready`, `claim` and `page` check each block when they read it. `ready` skips a work issue whose block is malformed and says so in a warn line, and `page` shows such a block as "malformed", never as content.
  - **Other steps:** `check` lists malformed blocks, and `sync` reads no bodies.
  - Rejected: board fields, which cannot hold a list of options.
  - Rejected: the latest marked comment, since deleting a comment would roll the state back.
- **D8 How the user answers.** In a terminal cell, as in "#312 A". `answer` takes the quote and accepts it only if it meets all three conditions:
  - **Where it came from:** a message the user typed into the answering session, sent after the job was filed.
  - **What it names:** the job, by its number.
  - **What it answers:** one of the answers the job declares, such as an option's letter, or "approve" for an approval.

  **One message, several jobs:** a message may answer several jobs only by naming each, as in "#312 A, #315 approve". Each job still takes its own `answer N` call. That call checks only its own job: the job must be open, filed before the message, and given a declared answer in it. The call ignores the other jobs the message names, so a closed or unknown one there blocks nothing.

  **What is refused:** a quote that does not name the call's own job, names that job twice, or gives it an answer it does not declare. The user then retypes it in the form the page shows.
  - **Finding the transcript:** Bash tool processes carry `CLAUDE_CODE_SESSION_ID`, which is the transcript's file name under `~/.claude/projects/` (measured with Claude Code 2.1.316). The helper finds its own transcript that way.
  - **What counts as typed:** the transcript marks a typed message `origin.kind: "human"` and a worker's message `"peer"`, both on `user` records and on `queued_command` attachments (the messages typed while a turn runs). In the coordinator's transcript that was 72 typed against 82 from peers.
  - **The record:** the answer comment carries the message's time.
  - **Why not GitHub:** a GitHub comment cannot be checked this way, because sessions act as the user's login there.
  - **After a compaction:** the transcript keeps the records from before it, and this session read its own pre-compaction messages back from its file.
  - **After a resume:** the session may continue under a new ID. If the user's words are then not in the current transcript, `answer` refuses, and the user retypes them.
  - **Residual risk:** a session can set that variable falsely or append to its own transcript. Like the page's hooks, the check stops the habitual path, not a deliberate forgery.
- **D21 Who runs `answer`.** Whichever session holds the user's words, usually the coordinator, may run `answer` on any open job. The quote check is the gate. The user answers every job in one place.
  - Rejected: answering in the filer's cell, which means switching cells for each job.
  - Rejected: the coordinator filing workers' jobs, which reverts D20.
- **Notes.** "Coord decided" lines and findings are comments the helper writes and marks as such, on the issue they concern. Comments are only added, never changed, so deleting one loses a past line, not current state.
- **The skill's own-issues rule, revised.** It names every step that may touch an issue the session neither filed nor claimed:
  - `sync`, as now: it adds open issues missing from the board, in Triage;
  - `queue`, as now: on the user's ask;
  - `note`, new: it may add its marked comments to any open issue;
  - `answer`, new: it may close any open job (D21).

  Every other edit, move and close stays limited to issues the session filed or claimed.
- **Global `CLAUDE.md`, revised.** § General lets a session file a follow-up into Triage with no ask. A second exception joins it: filing a job for the user with `ask` is itself a way of asking, and builds nothing. So it needs no ask, and goes straight to Todo (D6).

**The page**
- **D1 Protection.**
  - **Not the record:** the page is only drawn from the record, so a hand edit gains nothing. Missing helper commands get added.
  - **A FileChanged hook** restores the page after a write by any program.
  - **A PostToolUse hook** restores it and tells the session in the same step.
  - **The log:** each restore appends a line to a local, untracked log beside the page. It is a diagnostic, not a record. `check` warns with the count, as a sign of a missing command.
  - **Ruled out by the user:** a separate macOS user writing the page, and a deny rule on it.
- **D2 Links.** Every issue on the page carries a link.
- **D3 Purpose.** Without a click, the page answers:
  - what the user must do, and what waits on it;
  - how far each goal and each piece of work has got;
  - what changed since they last looked.
- **Bounds:**
  - **Needs you:** every open job, at most 5 lines each, with a warning line when more than 7 are open.
  - **In progress:** one line per branch with its goal, step n of m, now, next, and whose turn. The turn is derived: the user's when an open job blocks the work, else the worker's.
  - **Since you last looked:** at most 10 lines, then a link to the rest.
  - **Goals:** a block the project adds (D10).
- **D9 Where it lives.** In one file in the project's checkout, named in `.task-board.json`, read in MulmoTerminal on desktop and in its mobile file view.
  - Rejected: a saved view on GitHub.
  - Rejected: a pinned issue that a GitHub Action rewrites. It costs Actions minutes on the free plan for a notification MulmoTerminal's push mostly gives already.
- **D12 When it is drawn.** After every helper write, from any session, and at the end of each coordinator turn, through a Stop hook. The first line reads "Updated HH:MM", or "Out of date since HH:MM: GitHub unreachable" when a read fails.
- **D13 "Since you last looked"** counts from the user's last typed message in the coordinator's cell. The coordinator's Stop hook finds that message in its own transcript (the `transcript_path` its hook input carries) and records the time before it redraws the page.
- **D19 Plain words.** The helper refuses a page line with a bare internal ID unless a plain explanation follows it. An ID here means something like an assumption number or a raw record ID. There is no glossary of terms; plain wording otherwise stays the writer's judgement.

**Where the work lives**
- **D10 Ownership.**
  - **The skill:** the job steps, the data block and the page.
  - **A project:** extra page blocks, through a script named in its `.task-board.json`. gkms adds its Goals block this way.
  - **The two protection hooks:** wired in the project's own settings.
  - Rejected: building it in gkms first, because its sessions would then write the board outside the helper.
  - Rejected: putting the hooks in the global settings.
- **D11 Order.** This repository first, then the gkms migration.
- **D22 Disclosure.** This repository is public and gkms-contest-ai is private. So this plan keeps the failures as counts and dates, and the decisions in general terms. The full log, research detail included, stays untracked in the project until its ExecPlan takes it in.

**gkms, in its own ExecPlan**
- **D14 The research record.**
  - **The new form:** the project's status page becomes JSON with a schema in git, written only by a command, inside merge commits, and checked at every merge.
  - **The page:** it survives only as a view built on demand.
  - **The project's ADR** that names the old page is amended to match.
- **D15 The task lists.**
  - **Next actions:** Todo issues, in their current order.
  - **Data wanted:** capture jobs.
  - **Backlog:** Triage.
  - **The done history:** frozen as an archive.
- **D16 The old board.** Its open items become jobs.
- **D17 Reply length.** MulmoTerminal's closing summary is turned off in the coordinator's checkout only, and the 5-line rule stays. No hook can enforce length, since a reply is on screen before any hook runs.
- **D18 Replacing a worker.** The replace script refuses unless one of these holds:
  - the branch has merged;
  - the worker's context is past 60%;
  - the user answered a run job for that replacement ("Replace the stuck worker on #298?"). The script asks the helper whether that job was closed by `answer` with "approve". So an off-rule replacement is a job like any other, and needs no second kind of check.
- **Stand as designed:**
  - workers post their reports verbatim as comments on their own issue;
  - after a compaction, the coordinator gets a card of at most 15 lines;
  - obsolete instruction prose is pruned;
  - the old board's scripts are retired.
- **Sequencing:** the ExecPlan orders the migration around the project's other open branches.

## Changes

`skills/task-board/board.py`:
- **New steps:**
  - **`ask`** files a job (D6, D7). `--holds-up` sets the dependencies.
  - **`answer N --quote …`** checks the quote, records it, and closes the job (D8, D21).
  - **`job-state N`** prints a job's state and the answer that closed it, for project scripts (D18).
  - **`progress N`** sets a work issue's lines.
  - **`note N --decided|--finding`** writes the marked comments.
  - **`page`** draws the page (D3, D9, D12, D13).
- **Existing steps:**
  - **`ready` and `claim`** leave jobs out (D6) and check blocks as they read them (D7).
  - **`check`** lists malformed blocks and the count of page restores (D1, D7).
- **Every write step** checks its lines against the schema and the ID rule (D19), then redraws the page.
- **The rules as pure functions,** in a module of their own, with tests (`docs/testing.md`):
  - the schema;
  - the ID check;
  - the quote match over transcript records;
  - the page layout, including derived whose-turn.

Also in the skill:
- **Hook scripts** for a project to wire in its settings:
  - the page restore, on FileChanged and PostToolUse, which also appends to the restore log;
  - the Stop redraw, which also stamps the user's last message.
- **`.task-board.json`:** optional `page` and `page_blocks` keys.
- **`SKILL.md`:**
  - the new steps;
  - the revised own-issues rule;
  - jobs skipping Triage;
  - workers filing their own questions;
  - how a project wires the hooks.

Global `CLAUDE.md`, § General: the exception for filing a job for the user (above).

`README.md`: the `task-board` bullet cites this plan.

## To check during the build

- **Speed:** how long one GitHub read takes per redraw (D12).
- **Context:** how to read a worker's context share from the usage of its transcript's last turn (D18).

## Not covered

- **Blocking prompts.** A prompt that blocked one session stalled work for hours. That is not a board problem.
- **Plain wording beyond IDs (D19).** It stays the writer's judgement.
- **Deliberate forgery** of a session's transcript or its variables (D8).

## Verification

- **Tests:** each rule function has tests, each shown to fail when its rule is broken.
- **Page protection, in a scratch project:**
  - a `sed -i` write to the page is restored and logged;
  - an Edit-tool write is restored, with the PostToolUse note;
  - the page's own redraw does not loop.
- **Answers:**
  - a quote from a peer's message is refused;
  - so is a quote sent before the job was filed;
  - so is one that names no job or gives an undeclared answer;
  - for "#312 A, #315 approve", `answer 312` and `answer 315` each succeed, and `answer 316` is refused;
  - `answer 312` still succeeds when #315 is already closed.
- **Review:** `/codex-review` on the branch's whole diff.
- **In use, gkms's first week on the board:**
  - every job is closed by a quote;
  - no "done unless vetoed" calls;
  - each logged restore becomes a helper command.

## Codex review (2026-11-01)

`/codex-review` on the plan's first draft, at `d4a3ece`, returned **CHANGES REQUESTED**. It ran in a snapshot and moved no refs. Every finding was accepted.

- **HIGH, a deadlock between D8 and D20: fixed by D21,** the user's call. A worker filed the job, but the user answered in another session, and the own-issues rule kept that session from closing it.
- **HIGH, `answer` not buildable as specified: fixed in D8.** How the helper finds its transcript, and which records count as typed, were measured, not left to the build.
- **MEDIUM, D20 overclaimed "mechanical": narrowed.** Only a filed job is mechanical; filing stays the worker's judgement, and the remaining risk is stated.
- **MEDIUM, comments on others' issues, and `note`: fixed.** The own-issues rule is revised explicitly.
- **MEDIUM, jobs and the Triage gate: fixed in D6.** Jobs go to Todo and are never ready work.
- **MEDIUM, "checked on every read" with no readers named: fixed in D7.**
- **MEDIUM, the restore log had no home: fixed in D1.**
- **MEDIUM, private detail in a public repository: fixed by D22,** the user's call. This plan keeps counts and dates; the full log stays in the project.
- **Second pass, on the revision: CHANGES REQUESTED.** It confirmed the first pass's findings resolved, and raised three new ones, all accepted.
  - **HIGH, a quote not bound to its job: fixed in D8.** A bare "A" could have closed the wrong job. A quote must now name the job and give one of its declared answers. The plan also says how compaction and a resume behave.
  - **MEDIUM, the own-issues rule omitted `sync` and `queue`: fixed.** The rule now names every step that may touch another session's issue.
  - **MEDIUM, jobs skipping Triage contradicted global `CLAUDE.md`: fixed.** Its filing exception gains jobs for the user, listed in Changes.
- **Third pass: CHANGES REQUESTED.** It confirmed the second pass's findings resolved, and raised two new ones, both accepted.
  - **HIGH, D18 could not use D8's check:** a replacement has no job to name. Fixed: an off-rule replacement is now a run job, and the script reads its state through `job-state`.
  - **MEDIUM, several jobs in one message against a one-job `answer`: fixed in D8.** Each call checks only its own job.
- **Fourth pass: CHANGES REQUESTED, one MEDIUM, accepted.** The refusal of "names one twice" contradicted "each call checks only its own job". It is now scoped to the call's own job. The fix is a wording change, so the review was not run again.
- **Found on this session's own reading:**
  - whose turn is derived, now written in Bounds;
  - D13 now uses the Stop hook's transcript, not a hook on sending.

## Build (2026-11-01)

**Built on `feat/task-board-jobs-and-page-build`:**
- **`skills/task-board/jobs.py`:** the pure rules (the block and its schema, the line and ID rules, the quote match, the page's layout).
- **`board.py`:** the steps `ask`, `answer`, `job-state`, `progress`, `note` and `page`. `ready` and `claim` leave jobs out, and every write step redraws the page.
- **`skills/task-board/page_hook.py`:** the four hooks.
- **Tests:** `test_jobs.py`, `test_page_hook.py`, and new cases in `test_board.py`.
  - **Mutations:** each new rule was removed in turn, with bytecode caching off, and every one of those versions failed a test.
  - **The real-`gh` replay** accepted every new command shape, among them `issue edit --add-blocked-by`, `--body-file -` and `issue list --search`.

**Where the build settled what the decisions left open:**
- **The page's local state:** the generated copy, the last-seen stamp and the restore log live in the main checkout's `.git/task-board/`, not beside the page. They stay local and untracked, and away from the files sessions edit.
- **Declared answers:** a decision's option letters; `approve` or `decline`; `done` for a capture or a run.
- **Lines:** at most 120 characters. The default ID pattern is letters then digits (E193, S54-4), or a raw record ID with an underscore and a digit; a project may set its own in `id_pattern`.
- **D8, tightened:** the whole message the quote comes from must name the job once, with that answer, so a quote cut from "#312 A #312 B" cannot pick one. A clear later message still counts.
- **The answer comment** records the message's time.

**The security-guidance plugin's automated review of the first build commit found two points, both fixed:**
- **A stranger's block:** a block counts only in an issue the board's login wrote. On a public repository a stranger's issue could otherwise show as a job, or hide work from `ready`.
- **Whose settings:** the page's settings, including the `page_blocks` command, come from the main checkout's own `.task-board.json`, not from a worker's branch. The page's real path must stay inside the main checkout.

**`/codex-review` of the build at `aec60ee`: CHANGES REQUESTED, two MEDIUMs, both accepted.**
- **A progress block in an issue someone else opened was ignored,** although the helper wrote it. A work block now also counts when the board's login was the last to edit the issue's text, read from GraphQL's `Issue.editor` for in-progress issues opened by another account. When that account edits the text again, it is theirs again, and the block no longer counts.
- **One hand edit can go unlogged:** one landing between the helper's two writes, copy and then page, is overwritten by the helper's own page write. The page ends right, but no line records the edit.
  - **Decided:** the window is the time between two `os.replace` calls, so `SKILL.md` now says this, rather than adding machinery to catch it.
  - **Correction:** the earlier claim that every change is logged was too strong.

**Not done yet:**
- **No live run.** Nothing here has run against a real board, and no Claude Code session has run the hooks wired: the end-to-end checks in § Verification need a scratch project and board.
- **Not measured:** how long one GitHub read takes per redraw (§ To check during the build).
- **gkms's side,** including reading a worker's context share for D18, is its own ExecPlan.
