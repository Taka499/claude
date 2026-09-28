# Plan: Harvest from the gakumas-supportcards Oxlint session — two stack-note facts, one skill note; no cross-repo paths in shared guidance

## Goal

The gakumas-supportcards session of 2026-09-27Z carried out `docs/plans/EXECPLAN_OXLINT.md` there: Oxlint on the TypeScript 7 path, 60 findings drained, the lint a gate in three workflows, two Codex reviews. Three of its lessons generalise beyond that repository and would be rediscovered at a cost the next time the Oxlint path or the `codex-review` skill is used; the user chose these three of four proposed captures (the fourth, a memory of release habits, was declined).

## Changes

- `docs/typescript.md` § Oxlint path — a new paragraph after the configuration one: Oxlint 1.85 prints nothing on a clean run (no `Found 0 …` line; exit status and the injected-`any` probe are the proofs), and `security/detect-unsafe-regex` rejects any quantifier inside an optional or repeated group, so the accepted shape is one bare repetition with the empty case and the length bound decided in code.
- `skills/codex-review/SKILL.md` step 2 — in a worktree-isolated session the harness refuses a command whose quoted text mentions `git`, which the review prompt does; write the prompt to a file and run `codex exec … - < prompt.txt`.
- Global `CLAUDE.md` § Continuous Learning — a new rule: shared guidance never cites file, document or section names from another repository; the source project is named by bare name with any date or version, and the evidence stays in the capture's `plans/` file.
- `docs/typescript.md`, `docs/rust.md`, `docs/python.md`, `docs/testing.md` — the existing entries brought under that rule: 221 source tags such as `(ss-assist execplan-phase2 Milestone 1)` or `(gakumas EXECPLAN_FEEDBACK_FORM, Surprises; \`runner.rs\`)` reduced to the project name, keeping the tags' dates, versions and commentary (`(ss-assist — this removed an entire planned milestone)`); the three "Extracted from" headers keep only the GitHub repository and the date. Lesson text is unchanged.

## Decision Log (session 2026-09-27)

- **Additive, not a rewrite** — both notes extend the Oxlint section and step 2; nothing existing is contradicted, so nothing is replaced (global `CLAUDE.md` § Continuous Learning).
- **Not captured** — the plan-authoring lesson (one home per step, or the milestone counts disagree) and the Codex-intent lesson (an overstated intent comes back as a MUST-FIX) stay in that plan's retrospective; both are general but neither has a rule-shaped home yet. Revisit if either recurs.
- **No ADR** — prose notes, trivially reversible. Fails gate one.
- **No cross-repo paths (session 2026-09-28)** — the Codex review of this PR flagged the new paragraph's citation of `docs/plans/EXECPLAN_OXLINT.md` as unresolvable from this repository. The user's point went further: the stack notes are loaded on every machine using this setup, and on one without that checkout a path from another repository cannot be opened, so it confuses rather than proves. Options weighed: fix only the lines Codex and the review named; strip every source tag; or strip paths only and keep the project name. Chosen: paths only — the name still says where a lesson came from, and a date or version still says how old it is, without pointing a session at a file it may not have. A second Codex pass on the expanded diff (CHANGES REQUESTED) found 22 `info-gathering` tags that had lost their `2026-06-11` date, now restored; headers that still listed document kinds, now reduced to repository and date; and a miscount (219 → 221, the Bun and Oxlint lines were edited outside the scripted pass). Its finding that skills still point into `isamu/claude` and the project template was taken as a scope problem in the rule rather than a violation: those are public references or deliberate operations on another repository, and the rule now says so, limiting it to *source citations* into another project's internals. Treated as a *correction* under § Continuous Learning, so replaced in place, not added beside; no project depends on the tags, so none is left on the old text.

## Verification

- Both facts were observed in the session, not inferred: the flagged `^(\?…+)?$` rewrite and the clean-run silence are in the plan's § Surprises with timestamps; the stdin form of `codex exec` ran to a verdict twice after the inline form was refused three times.
- After the tag rewrite, no `EXECPLAN`, `execplan`, `ADR 00`, `docs/adr/0` or `docs/plans/` remains in the four stack notes, and the diff touches only the parenthesised tags and the three header lines.
- Prose only: no test to run. Read the two edited sections once after merge through `~/.claude` (symlinked) to confirm they deploy.
