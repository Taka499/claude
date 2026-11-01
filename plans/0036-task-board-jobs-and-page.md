# Plan: jobs for the user and an attention page on the task board

## Goal

gkms-contest-ai runs a coordinating session, gkms-coord, in its main checkout, with up to four workers in worktrees of their own. Its board is local: `coord/board.json`, written by a project script and rendered to `coord/board.md`. Its rules live in instruction prose. A review of its transcripts from 2026-10-24 to 11-01 found that this setup failed in four ways:

1. **Decisions the user never saw.**
   - **Done unless vetoed.** The coordinator settled calls as "done unless vetoed by the next window", with windows at 09:00 and 21:00 JST. No window ever fired, since nothing woke the coordinator at those times. The calls piled up in one free-text note, 20,527 characters long.
   - **The largest call.** On 11-01 at 00:58 a worker asked a question with a decision page: whether to fix two engine rules (E193, E194) before predicting. At 01:00 the coordinator answered it itself ("A, my call"). That left 140 of about 900 moves out of the test. The user vetoed it at 05:00, after reading the note.
2. **Rules lost at compaction.**
   - **The sandbox flag:** the user corrected a flag on the replace-worker script on 10-27. It recurred 13 times, starting 14 minutes after a compaction on 10-31.
   - **Hand edits:** `board.json` was edited by hand 7 times. 5 of those edits did something its script had no command for.
   - **Codex reviews:** the coordinator demanded a Codex review at a milestone's end 3 times, against the user's rule.
3. **Hard to read.**
   - **Length:** 7 of 155 final replies kept to the 5-line limit; the median was 12 lines. MulmoTerminal's closing summary alone adds 3–5 lines.
   - **Shorthand:** the user asked what something meant about 10 times. 2 of those were bare IDs.
4. **Workers replaced too often.** There were 43 replacements in 8 days, against the rule "only at a merge or past about 60% context". One worker was replaced 5 times in 3.5 hours, and no replacement cited context.

**The user's aim:** a page that saves their attention. They never open an issue to follow progress or to learn their jobs. It should use the GitHub board that every project can now have (plan 0033), and keep no record in a form as weak as free Markdown.

## Decisions (grilled with the user, 2026-11-01)

**What reaches the user**
- **D4 What the coordinator may decide alone.** Anything except a worker question that comes with a decision page. That question is always the user's job. Each of the coordinator's own calls shows as a "coord decided" line with its reason. This replaces "done unless vetoed" and the windows.
  - Rejected: also routing scope changes, since the coordinator would classify its own calls, the judgement that failed on E193/E194.
  - Rejected: routing everything beyond the plan, which would flood the page.
  - Accepted risk: a high-stakes call that no worker raises is seen only afterwards.
- **D20 Who files that question.** The worker files the decide job itself with the helper, from its worktree, and it holds up the worker's own issue. The coordinator may comment on it, but cannot answer or close it (D8). This is what makes D4 mechanical: on E193/E194 the coordinator never passed the question on.
  - Rejected: the coordinator filing it.
  - Rejected: the coordinator rewriting the worker's lines.
- **D5 Worker plans.** The coordinator approves them, and each approval shows as a "coord decided" line. A question a plan raises for the user goes through D20.
  - Rejected: the user approving every plan.
  - Rejected: the user approving only plans that start a new goal.

**How a job is held**
- **D6 One issue per job.** Every job for the user is its own issue, marked with its kind: decide, approve (a merge with its push), capture (data the user collects) or run (a command only the user can run). The work it holds up is "blocked by" it, through GitHub's own dependency, so `ready` skips that work. Cost accepted: about 1–2 extra issues a day for merge approvals.
- **D7 Where an issue's lines live.** In a JSON block in the issue's text, written by the helper with a readable rendering above it. It is checked against a schema on every write and every read:
  - **a job's lines:** the kind, the options each with its cost, the recommendation and why, and how to answer;
  - **a work issue's lines:** the goal it serves, step n of m, now, and next.

  A block in a bad shape shows on the page as "malformed", never as content.
  - Rejected: board fields, which cannot hold a list of options.
  - Rejected: the latest marked comment, since deleting a comment would roll the state back.
- **D8 How the user answers.** In a terminal cell, as in "#312 A". The `answer` step takes the quote, and refuses it unless the quote appears in a message the user typed into that same session; the transcript marks those `origin.kind == "human"`, and a worker's message has `peer`. A GitHub comment cannot be checked this way, because sessions act as the user's login there.
- **Filled in, not asked:** "coord decided" lines and findings are helper-written comments on the issue they concern, each marked as such. They are events added in order, so deleting one loses a past line, not current state.

**The page**
- **D1 Protection.**
  - The page is never the record, only drawn from it. A hand edit gains nothing, missing helper commands get added, and every restore is logged as "missing command?".
  - A FileChanged hook restores the page after a write by any program.
  - A PostToolUse hook restores it and tells the session in the same step.
  - The user ruled out going further: no separate macOS user writing the page, and no deny rule on it.
- **D2 Links.** Every issue on the page carries a link.
- **D3 Purpose.** The page answers, without a click: what the user must do and what waits on it; how far each goal and each piece of work has got; and what changed since they last looked.
- **Bounds:**
  - **Needs you** shows every open job, at most 5 lines each, with a warning line when more than 7 are open.
  - **In progress** gives one line per branch: goal, step n of m, now, next, and whose turn.
  - **Since you last looked** shows at most 10 lines, then a link to the rest.
  - **Goals** is a block a project adds (D10).
- **D9 Where it lives.** One file named in `.task-board.json`; for gkms that is `coord/board.md`, read in MulmoTerminal on desktop and in its mobile file view.
  - Rejected: a saved view on GitHub.
  - Rejected: a pinned issue rewritten by a GitHub Action, which costs Actions minutes on the free plan for a notification MulmoTerminal's push mostly gives already.
- **D12 When it is drawn.** After every helper write, from any session, and at the end of each of the coordinator's turns (a Stop hook). The first line reads "Updated HH:MM", or "Out of date since HH:MM: GitHub unreachable" when a read fails.
- **D13 "Since you last looked"** counts from the user's last typed message in the coordinator's cell. A hook records that time when the message is sent.
- **D19 Plain words.** The helper refuses a page line with a bare ID, such as E193 or a raw card ID, unless a plain explanation follows it. There is no glossary of terms, so plain wording otherwise stays the writer's judgement.

**Where the work lives**
- **D10 Ownership.**
  - **The skill:** the job steps, the data block and the page.
  - **A project:** extra page blocks, through a script named in its `.task-board.json`. gkms adds Goals this way.
  - **The two protection hooks:** wired in the project's own settings.
  - Rejected: building it in gkms first, because its sessions would then write the board outside the helper.
  - Rejected: putting the hooks in the global settings.
- **D11 Order.** This repository first, then gkms's migration.

**gkms only (outline for its ExecPlan)**
- **D14 The research record.**
  - **Form:** JSON with a schema, kept in git. That covers one file per research question, the project's goal, and each branch's scope, reserved ID ranges and the assumptions its results rest on. A question's file holds:
    - its status (settled, leaning, open or blocked);
    - a state line of at most 100 characters, with a measure;
    - links to the evidence;
    - what would settle it;
    - the next step.
  - **Writing:** only by a command, inside merge commits. Its checker refuses a merge that fails the schema.
  - **`docs/STATUS.md`** becomes a view built on demand, never committed.
  - **ADR 0007** is amended to match.
- **D15 The lists.**
  - **Next actions (about 12):** Todo issues, in their current order.
  - **Data wanted (about 7):** capture jobs.
  - **Backlog (about 20):** Triage.
  - **The Done history (about 61 entries, 47 KB):** frozen as an archive file.
- **D16 The old board.** Its open items and any vetoable call still waiting become jobs. Calls that already stood go to the archive.
- **D17 Reply length.** MulmoTerminal's closing summary is turned off in the main checkout only, and the 5-line rule stays. No hook can enforce length, since a reply is on screen before any hook runs.
- **D18 Replacing a worker.** The replace script refuses unless:
  - the branch merged;
  - the worker's context is past 60%; or
  - the user's own words OK it, checked as in D8.
- **Stand as designed:**
  - workers post their reports verbatim as comments on their own issue;
  - after a compaction, the session-start hook prints a coordinator card of at most 15 lines;
  - the obsolete sandbox prose and the old board's prose are pruned;
  - the old board's scripts are retired.
- **Sequencing:** the user set a new research direction on 11-01 at 06:09. It goes on a branch that rewrites the status page's § 0, and that branch waits for the user's go. The migration has to be ordered around it.

## Changes

`skills/task-board/board.py`:
- **New steps:**
  - `ask` files a job (D6, D7), with `--holds-up` setting the dependencies;
  - `answer N --quote …` records the quote and closes the job (D8);
  - `progress N` sets a work issue's lines;
  - `note N --decided|--finding` writes the marked comments;
  - `page` draws the page (D3, D9, D12, D13).
- **Every write step:** checks its lines against the schema and the ID rule (D19), then redraws the page.
- **The rules themselves:** pure functions in their own module, with tests (`docs/testing.md`). These are the schema, the ID check, the quote match and the page layout.

Also in the skill:
- **Hook scripts** a project wires in its settings: page restore (FileChanged, PostToolUse), the last-seen stamp, and the Stop redraw.
- **`.task-board.json`:** optional `page` and `page_blocks` keys.
- **`SKILL.md`:**
  - the new steps;
  - the rules: an answer only through `answer`, and a worker's question filed by the worker;
  - how a project wires the hooks.

`README.md`: the `task-board` bullet cites this plan.

## To check during the build

- How long one GitHub read takes per redraw (D12).
- Whether the quote check runs best as a hook limited to `answer` or inside the helper (D8, D18).
- Whether a hook sees `origin.kind` for typed and peer messages (D8, D13).
- How to read a worker's context share from its transcript (D18).

## Not covered

- **Blocking prompts.** A dry run that waited on a prompt stalled work for 5 h 47 min on 10-30. That is not a board problem.
- **Plain wording beyond IDs (D19).** It stays the writer's judgement.

## Verification

- **Tests** for each rule function, each shown to fail when its rule is broken.
- **Page protection in a scratch project:**
  - a `sed -i` write to the page is restored;
  - an Edit-tool write is restored, with the PostToolUse note;
  - the page's own redraw does not loop.
- **Answers:** a quote taken from a peer's message is refused.
- **Review:** `/codex-review` on the branch's whole diff.
- **In use:** gkms's first week on the board.
  - Every job is answered with a quote.
  - No "done unless vetoed" calls.
  - Each restore logged becomes a helper command.
