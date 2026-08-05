---
name: harvest-session
description: End-of-task ritual that mines the current session for durable learnings — corrections the user made, instructions repeated, gotchas discovered — and proposes routing each to its proper home (global CLAUDE.md, stack note, project CLAUDE.md/ADR, new skill, or memory). Use after completing a task, before ending a work session, or when the user says "harvest", "what did we learn", "capture the learnings from this session".
---

# Harvest Session

A session's hard-won knowledge evaporates when the context window closes. This ritual runs the Continuous Learning rule (global `CLAUDE.md` § Continuous Learning) deliberately instead of hoping it fires: review what happened, extract what should outlive the session, and propose a home for each item. Nothing is written without the user's confirmation.

## 1. Mine the session

Walk back through the conversation looking for exactly these signals:

- **Corrections and redirections** — the user stopped you, reversed a choice, or rephrased an instruction. Each one is evidence of a rule the harness was missing or stated too weakly.
- **Repeated instructions** — the same guidance given 2+ times (in this session, or that you recognize from prior sessions). Repetition means the harness, not the human, should carry it.
- **Discovered gotchas** — anything that behaved differently than documented or expected: an API quirk, a toolchain trap, a library limitation. Especially ones that cost real debugging time.
- **Manual multi-step procedures** — a sequence you executed by hand that will plausibly recur. Candidate for a skill.
- **Decisions with reusable rationale** — trade-offs resolved during the work whose reasoning applies beyond it.

## 2. Route each finding

For each item, propose ONE destination, using the narrowest scope that fully contains its value:

| Finding | Home |
| --- | --- |
| Cross-project rule or workflow | Global `CLAUDE.md` in the `Taka499/claude` repo (via PR) |
| Stack-specific lesson (Rust/TS/Python…) | The matching `docs/*.md` stack note in `Taka499/claude` (via PR) |
| Repeatable executable workflow | New or improved skill — user-level in `Taka499/claude` if general, the project's `.claude/skills/` if project-specific |
| Project-scoped rule | The project's `CLAUDE.md` |
| Project decision passing the three-gate test | ADR in the project's ADR home (see the project's ADR README) |
| Plan-scoped narrative | The active ExecPlan's Decision Log / Surprises & Discoveries |
| Fact about the user, preference, or feedback not derivable from code | File-based memory |
| None of the above (obvious, one-off, easily rediscovered) | Nowhere — recording everything buries what matters |

## 3. Propose, confirm, write

Present the findings as a short list — claim, evidence from the session, proposed home — and let the user strike or re-route items. Then write the accepted ones:

- Project-local captures: edit the files directly, propose the commit per the repo's discipline.
- Central-repo captures: make the change in the local `claude` repo clone on a feature branch and propose the PR, per that repo's README — never edit the deployed `~/.claude` copies outside a branch.

Expect most sessions to yield zero to two items. An empty harvest is a valid result; say so and stop rather than manufacturing learnings.

---

*Codifies the Continuous Learning / Automation Proposals loop from [isamu/claude](https://github.com/isamu/claude) `CLAUDE.md`, re-targeted to this system's homes (central repo, stack notes, ExecPlans, ADRs, memory).*
