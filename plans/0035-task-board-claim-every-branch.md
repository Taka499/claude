# Plan: every branch of work claims an issue on the board

## Goal

On 2026-10-31 the user reported that gkms-memomemo, the first project scaffolded with a board by default (plan 0033), was not using it. Its board, `tia-tools` #7, passed `check`, and its `CLAUDE.md` named it. Yet the session working its ExecPlan did Milestone 0 and Milestone 2 on two branches with no issue on the board. The plan review and Milestone 0 merged as PRs #1 and #2 with no `Closes #N`. Only after the user said "You are not using GitHub board" did the session file #3 for Milestone 2, claim it for its branch and cite it in the plan.

The session had loaded the `task-board` skill at its start and run `check`, `sync` and `ready`: "0 ready", so it wrote "Board is empty". The user then said "start proceeding the plan". Three things in the skill let the work bypass the board:

1. **Claiming was a step of picking work from `ready`.** Work the user asked for directly never reached it. Filing appeared under "Filing", not as a gate before work, so an empty board read as having nothing to do with the work.
2. **"Plan milestones are not issues"** (plan 0030 D1). D1 says so in those words, and names milestone sub-issues under one item as the option not chosen, because progress would then be kept twice. A session reads the line as: a milestone needs no issue. gkms-hif-final-stats had already worked the other way: one issue per milestone, each closed by its PR (#4, #6, #8, #10, #12, #15).
3. **The skill's description** loaded it only for talk of issues ("what is next", "pick up", "file"…). "Proceed the plan" does not match. Here it was loaded already; another session may never load it.

## Decision

**D1 revised (the user's go, 2026-10-31):** a plan milestone that takes a branch of its own gets an issue of its own, closed when that branch merges. The rest of D1 stands: one issue is one backlog item sized to one branch, the plan keeps the design and progress, and milestone sub-issues under one item stay rejected. Plan 0030 is left as written; this plan records the revision.

## Changes

`skills/task-board/SKILL.md`:
- **The description:** the skill also applies whenever a session starts a branch of work in a board project.
- **§ The board:** a plan whose milestones each take a branch of their own gets one issue per milestone (D1 revised). Sub-issues stay rejected.
- **Step 2:** the claim comes before the branch's first commit. Work the user asks for with no issue covering it is filed with `file --todo` (the ask is what queues it), then claimed. An empty `ready` list does not mean the board has nothing to do with the work.
- **Step 4:** a plan with an issue per milestone cites each in that milestone's Progress entry.
- **§ Rules:** no branch of work without a claim. A branch of work is any branch that will merge into the integration branch, a plan's close-out on a branch of its own included; work continued on a branch stays under its claim, and a release into `main` needs none. A branch found working without a claim gets its issue filed and claimed at once.

Global `CLAUDE.md`, the board bullet of § General: start no branch of work before claiming its issue, filing one first if the user's ask has none. It is always loaded, so it reaches a session that never loads the skill.

`README.md`: the `task-board` bullet cites this plan.

**Not done:** a CI check in each project failing a PR into `develop` without `Closes #N`. It would catch the miss only at PR time, needs a workflow file per project, and does not reach projects that merge locally. Revisit if the prose rule fails again.

## Verification

- `grep` finds "Plan milestones are not issues" nowhere outside `plans/`.
- `/codex-review` on the branch's whole diff.
- In use: the next branch of work in gkms-memomemo, or any board project, holds a claim from before its first commit.

## Codex review (2026-10-31)

`/codex-review` on the branch's whole diff at `35b531d`. Verdict: **CHANGES REQUESTED**. It ran in a snapshot, and no refs moved.

- **MEDIUM, "branch of work" undefined: accepted, fixed.** The rule said "every feature branch" while `CLAUDE.md` said "branch of work", and neither said what a release, a close-out or work continued on a branch needs. § Rules now defines it: any branch that will merge into the integration branch.
- **MEDIUM, the plan called the new wording what D1 meant: accepted, fixed.** D1's own words are "Plan milestones are not issues". § Decision now records the revision as one.
- **Second pass, at `233844a`:** **LGTM**. Both findings resolved; the Triage gate and the follow-up filing exception agree with the new rule.
