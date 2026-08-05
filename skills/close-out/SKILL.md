---
name: close-out
description: Close out a completed ExecPlan — extract its durable decisions into ADRs, update CLAUDE.md's snapshot with source citations, write the plan's retrospective, and stamp it complete. Use when an ExecPlan's acceptance has passed, when the user says a plan is done/finished/accepted, or asks to "close out", "wrap up", or "archive" a plan.
---

# Close-Out

An ExecPlan accumulates decisions, discoveries, and terminology while it is alive; when it completes, that knowledge is stranded in a document no future session reads end-to-end. Close-out is the ETL step that keeps the two documentation layers consistent: the immutable log (ExecPlans) and the mutable snapshot (the project `CLAUDE.md`, backed by ADRs).

This skill is installed user-level; repo layouts differ. First locate this repo's conventions: its PLANS.md (`docs/PLANS.md`, then `_docs/PLANS.md`) and its ADR home (`docs/adr/README.md` or the equivalent named in the project `CLAUDE.md`). If the ADR scaffold is missing, offer to add it from `Taka499/project-template`; if declined, record the durable decisions as clearly-cited entries in the project `CLAUDE.md` instead — degraded routing, but no lost knowledge.

Run it once per plan, when acceptance has passed (or the user declares the plan done). Steps, in order:

## 1. Read the whole plan

Read the full ExecPlan document — every section, not just Progress. You are looking for claims that outlived the plan, not summarizing it.

## 2. Write the retrospective

If `Outcomes & Retrospective` is missing or stale, write it now (what was achieved, what remains, lessons learned) — this is the last edit the plan will ever receive, per the immutability contract in the project's ADR convention.

## 3. Sweep for durable decisions

Go through the `Decision Log` and `Surprises & Discoveries` sections and test each entry against the ADR three-gate filter: hard to reverse, surprising without context, the result of a real trade-off. For each survivor:

- If no ADR covers it, write one — a few sentences plus the mandatory `Source:` line citing this plan and the evidence level (e.g. "confirmed by N-row field replay, `<plan path>` M4").
- If an existing ADR is contradicted, don't edit its content — set its status to `superseded-by-NNNN` (or `rescinded` if it turned out to have been false all along), append one sentence saying what changed, and write the successor.
- If the lesson's value reaches **beyond this repository** (a stack gotcha, a workflow rule), additionally propose capturing it in the central `Taka499/claude` config repo (stack note, global rule, or skill) via its PR flow.

Most plans yield zero or one ADR. Forcing more dilutes the set.

## 4. Update the snapshot

Bring the project `CLAUDE.md` back in line with post-plan reality:

- Update the plan's own entry (in the active-plans list or equivalent): status → complete, with the acceptance evidence in one line.
- Add or update the ADR index lines for any ADRs written or re-statused in step 3.
- Fix any other CLAUDE.md claim this plan changed (new commands, moved files, renamed concepts). Every non-obvious claim you touch must cite its source — `per docs/adr/NNNN` or `per <plan path>` — so the snapshot stays auditable and rebuildable from the log.

## 5. Stamp and stop

Mark the plan complete in its own `Progress` section. From here the plan is immutable history: future corrections happen in ADRs and CLAUDE.md, never by retrofitting the plan. Propose a commit following the repo's commit discipline, keeping the plan stamp, ADRs, and CLAUDE.md edits in one coherent commit (or small series) so the close-out is atomic in history.

If, mid-sweep, you find the plan asserted something now known to be false, that is not a close-out edit — write the correcting ADR (status `rescinded` on the old belief's record, or a new ADR if none exists) and leave the plan's text as the record of what was believed at the time.
