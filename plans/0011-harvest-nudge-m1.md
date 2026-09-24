# Plan: Harvest from the nudge Milestone 1 session — two global rules, two stack-note entries, one skill fix

## Goal

The nudge session of 2026-09-22 to 2026-09-24 built and accepted a Cloudflare Worker end to end. Five of its lessons generalise beyond that repository and would otherwise be rediscovered at a cost: one near-miss on production, about thirty minutes of hung installs, one premature review report, and one correction from the user about how shared guidance may change.

## Changes

- `CLAUDE.md` § Continuous Learning — captures that change shared guidance are additive while projects still follow the old guidance.
- `CLAUDE.md` § Debugging — never trim warning or error lines out of a command's output, above all for dry runs and deploys.
- `docs/typescript.md` — new § Cloudflare Workers deployment (environments inherit custom-domain routes; `routes = []` pinned by a test) and § Bun install and tooling traps (the install-cache hang; no `timeout` on macOS).
- `skills/codex-review/SKILL.md` step 2 — wait for a standalone verdict line or process exit, never the bare phrase.

## Decision Log (session 2026-09-24)

- **Additive-change rule in the global file, not only in the TypeScript note** — the user's correction ("rather than switching all … list them both, since there should be some project already using typescript 6") is about how any shared guidance changes, not about linters. It was already applied once in plan 0010; stating it once in `CLAUDE.md` stops the next stack note from needing the same correction.
- **Warning-filter rule under Debugging** — the failure was an agent habit (trimming noisy output with `grep -v`), not a wrangler quirk; the wrangler specifics go to the stack note.
- **Not captured**: sandbox friction around `gh` certificate checks and `.git/config` writes is already covered by the sandbox documentation (`#13` landed the `.git/config` case while this session ran); nudge-specific facts live in that repository's plan.
- **No ADR** — prose rules and notes, trivially reversible. Fails gate one.

## Verification

- `git diff master --stat` touches exactly the four files above plus this plan.
- The codex-review `grep` pattern matches a standalone verdict line and does not match the prompt text `'CODEX VERDICT: LGTM' or 'CODEX VERDICT: CHANGES REQUESTED'` (checked against the nudge review log of 2026-09-24).
