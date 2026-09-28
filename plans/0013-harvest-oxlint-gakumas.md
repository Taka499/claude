# Plan: Harvest from the gakumas-supportcards Oxlint session — two stack-note facts, one skill note

## Goal

The gakumas-supportcards session of 2026-09-27Z carried out `docs/plans/EXECPLAN_OXLINT.md` there: Oxlint on the TypeScript 7 path, 60 findings drained, the lint a gate in three workflows, two Codex reviews. Three of its lessons generalise beyond that repository and would be rediscovered at a cost the next time the Oxlint path or the `codex-review` skill is used; the user chose these three of four proposed captures (the fourth, a memory of release habits, was declined).

## Changes

- `docs/typescript.md` § Oxlint path — a new paragraph after the configuration one: Oxlint 1.85 prints nothing on a clean run (no `Found 0 …` line; exit status and the injected-`any` probe are the proofs), and `security/detect-unsafe-regex` rejects any quantifier inside an optional or repeated group, so the accepted shape is one bare repetition with the empty case and the length bound decided in code.
- `skills/codex-review/SKILL.md` step 2 — in a worktree-isolated session the harness refuses a command whose quoted text mentions `git`, which the review prompt does; write the prompt to a file and run `codex exec … - < prompt.txt`.

## Decision Log (session 2026-09-27)

- **Additive, not a rewrite** — both notes extend the Oxlint section and step 2; nothing existing is contradicted, so nothing is replaced (global `CLAUDE.md` § Continuous Learning).
- **Not captured** — the plan-authoring lesson (one home per step, or the milestone counts disagree) and the Codex-intent lesson (an overstated intent comes back as a MUST-FIX) stay in that plan's retrospective; both are general but neither has a rule-shaped home yet. Revisit if either recurs.
- **No ADR** — prose notes, trivially reversible. Fails gate one.

## Verification

- Both facts were observed in the session, not inferred: the flagged `^(\?…+)?$` rewrite and the clean-run silence are in the plan's § Surprises with timestamps; the stdin form of `codex exec` ran to a verdict twice after the inline form was refused three times.
- Prose only: no test to run. Read the two edited sections once after merge through `~/.claude` (symlinked) to confirm they deploy.
