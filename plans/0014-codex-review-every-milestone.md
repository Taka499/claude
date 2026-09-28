# Plan: Run `/codex-review` on every milestone pull request, not only the risky ones

## Goal

The gakumas-supportcards sessions of 2026-09-28 and 2026-09-29 carried out a four-milestone ExecPlan (a badge and facet, a scoring input with a snapshot-format change, a per-item panel with a route-profile effect, an image-pipeline extension) and five post-release UI refinements. Every milestone reached its pull request with all gates green — tests, type check, lint, a score-stability check, a build — and on every one a `/codex-review` of the diff returned CHANGES REQUESTED with exactly one real defect the tests had not encoded. The global `CLAUDE.md` lists the skill as a *second opinion before committing*; nothing says when to reach for it, and the natural reading — "for the risky ones" — would have skipped the two milestones whose defects were the most consequential. One sentence beside the pointer fixes that.

## Changes

- Global `CLAUDE.md` § Skills, the `/codex-review` line — one added sentence: SHOULD run it on every milestone pull request, not only the risky ones, with the evidence in one clause and the source project named by bare name and date.

## Evidence (kept here; the rule above does not cite it by path)

Ten defects found by Codex in one plan, every one on a diff whose own gates were green, every one confirmed real before fixing:

1. A memo's dependency list omitted the new facet flag, so the table re-filtered only when something else changed — the unit tests covered the filter function, not the memo.
2. A committed score snapshot that was meant to be independent of a modelling parameter was independent only by circumstance (it recorded values under the preset chosen *by* that parameter); recording per preset made it structural.
3. A URL parameter's grammar let non-canonical text through (`Number("")` is 0, so `a=..10` read as a valid triple).
4. A pure slider helper returned NaN for a non-finite position.
5. A deck-level count was taken from an item's most frequent trigger rather than the trigger that actually produces the counted thing — latent, since every shipped item shared one trigger, but the generator allowed the other shape.
6. An uploader's "public rendition only" mode could publish a file without its private master, breaking a master-first guarantee that the *previous* plan had documented and never tested; the risk had existed since that plan.
7. A tooltip on a control was not announced (no `aria-describedby` in the wrapping mode) and a disabled input was unreachable by keyboard.
8. Escape cleared the pinned state but focus kept the tooltip open.
9. A second tap did not close a tooltip because the tap's own focus had opened it.
10. Escape was handled on the wrapper only, so a tooltip opened by hover with focus elsewhere could not be closed.

Items 1 and 2 came from the two milestones a "risky ones only" rule would have called safe (a badge; a documented format change). Items 7–10 are behaviours no test in that repository can encode (there is no DOM in its test runner), which is exactly where a reader with different priors substitutes for a test.

## Decision Log (session 2026-09-29)

- **Additive, one sentence** — the pointer stays as it is; the sentence says *when*, and the evidence clause says *why*. Nothing existing is contradicted (global `CLAUDE.md` § Continuous Learning).
- **SHOULD, not MUST** — the skill sends the diff to OpenAI, which some repositories cannot accept; the skill's own text carries that caveat, and a MUST here would collide with it.
- **Where** — beside the pointer, not in § Quality Gates: it is guidance on using a skill, not a lint rule, and the reader who is about to open a pull request is looking at the Skills list.
- **No ADR** — a prose recommendation, trivially reversible. Fails gate one.
- **Not captured** — the four tooltip behaviours themselves (they are a `Hint` component's concern, project-scoped, in that project's plan) and the "an editable value must be exactly what an edit writes" lesson from the post-release fixes (general, but no rule-shaped home yet; revisit if it recurs).

## Verification

- The counts above are taken from the plan's Progress and Decision Log entries written the same day as each review, not reconstructed afterwards.
- Prose only: no test to run. After merge, read the Skills list once through `~/.claude` (symlinked) to confirm the sentence deploys.
