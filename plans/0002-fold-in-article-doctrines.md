# Plan: Fold in the source article's doctrines (post-bootstrap follow-up)

## Goal

The bootstrap (plans/0001) was built from isamu/claude's repo contents alone — the article that motivated this whole repo (「1日500コミットは、もう読めない ── だからコードレビューをやめた」, zenn.dev/singularity, 2026-07-27) was 403-blocked at the time. The user then supplied the article HTML. This change folds in the doctrines the article states that were not visible from the repo.

## Changes

- `CLAUDE.md` — new **Quality Gates** section (never silence lint/type errors inline — config-file allowlist with reason + removal condition; drain-then-ratchet for new strict rules; gate-vs-report decision discipline; every CI gate states what it guards) and new **Testing** section (design-for-testability incl. existing code, verify-tests-go-red, pointer to `docs/testing.md`).
- `docs/testing.md` — new cross-stack testing doctrine: pure-function extraction with dependencies-as-arguments (clock, paths, **platform as parameter** so win32 behavior tests run anywhere), the 10-pattern test checklist, verify-red rule, prioritize silently-wrong-value failures over exception-throwing ones.
- `docs/typescript.md` — new **Lint & static-analysis policy** section with the article's concrete config doctrine: size/complexity limits as errors (60-line functions, complexity 20/15, sonarjs cognitive-complexity 15), tseslint `strict` + sonarjs/security recommended-as-maximum, type escape hatches closed as errors, config-file exception discipline, typed-lint cost model (program build dominates; run only the 4 bug-class rules), jscpd/knip as reports not gates.

## Not folded in (deliberate)

- **Cross-model review CI** (Claude writes → Codex reviews on every PR, verdict markers, the codex-local-review / codex-cross-review / gh-review-loop skills): the article names this the single most effective lever, but the user deselected porting these skills during the bootstrap grilling, and none of the target repos currently run bot reviewers. Revisit when a second reviewer (Codex CLI or CodeRabbit) is actually available — the triage classification principles it needs are already in the skills' source repo to adapt from.
- **MulmoTerminal-style parallel-session tooling**: out of scope for a config repo.

## Verification

- `CLAUDE.md` § Quality Gates / § Testing reference only files that exist (`docs/testing.md`, stack notes).
- No project-specific facts imported from the article's repos (thresholds are cited as baselines to tune, with provenance).
