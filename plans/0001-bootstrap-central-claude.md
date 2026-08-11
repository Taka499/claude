# Plan: Bootstrap the central claude repo as the live ~/.claude

## Goal

Stop copy-pasting `project-template` into every new project. Centralize the user-level Claude Code configuration in this repo, emulating isamu/claude's delivery mechanism (repo = live `~/.claude` via symlink; every harness change is a PR) while keeping this user's own knowledge system (ExecPlans, three-gate ADRs, grill-me/close-out capture rituals) as the content.

## Changes

- `CLAUDE.md` — global rules: RFC-2119 keywords; strict git permission gating (ask before any commit/push/merge) combined with the small-frequent-commit discipline as *proposed* commits; commit-prefix convention observed from actual repo history; documentation self-sufficiency; ExecPlan/ADR project layer with convention discovery; debugging, continuous learning, automation-proposal rules; skills index; stack-note pointers.
- `skills/` — user-level seed: `grill-me` and `close-out` (moved from project-template, generalized to discover each repo's docs layout — `docs/` vs `_docs/` — and to offer scaffolding from project-template when missing), `codebase-design` (verbatim from gakumas-rehearsal-automation), `adopt-from-sibling` (adapted from isamu/claude, de-specialized), `harvest-session` (new; codifies isamu's Continuous Learning loop with this system's routing table).
- `docs/adr/` — harness-scoped ADR convention + `0001` (symlink deployment model).
- `docs/rust.md`, `docs/typescript.md`, `docs/python.md` — stack notes distilled from gakumas-rehearsal-automation, ss-assist, and info-gathering (CLAUDE.md files, ADRs, ExecPlan Surprises/Decision sections), filtered to lessons with value beyond their source repo.
- `setup.sh` / `setup.ps1` — idempotent symlink deployment with backup of pre-existing files.
- Companion change in `project-template`: remove `.claude/skills/` (now user-level), point its CLAUDE.md at the central repo for generic skills.

## Decision Log (from the grilling session, 2026-08-05)

- **Deployment = repo-is-~/.claude via symlink** over plugin or improved-template. → ADR 0001.
- **Provenance = light plans + minimal ADRs**: PR history is the main record; `plans/` files like this one for non-trivial PRs; full ExecPlan machinery deliberately NOT installed here (harness changes are small, reversible, single-sitting — the ceremony wouldn't pay for itself); `docs/adr/` reserved for harness-architecture decisions, expected low single digits. Chosen after weighing ADR pros (global rules have the widest blast radius and least visible context; PR-only provenance is invisible to future sessions reading the working tree) against cons (near-empty directory, redundancy with rule text, ceremony tax).
- **Git posture = isamu-strict**: every history-mutating git command requires explicit permission, overriding the earlier autonomous-commit reading of the per-repo Commit Discipline. Small-frequent-commits survives as small *proposed* commits.
- **Skill seed** = grill-me + close-out + codebase-design + adopt-from-sibling + harvest-session; isamu's stack-specific skills (yarn-update, publish, discord-release) excluded as a stack mismatch.
- **Skills are convention-discovering, not layout-standardizing**: repos keep their layouts (`_docs/` in ss-assist stays); skills locate PLANS.md/ADR homes per-repo and offer scaffolding when absent.
- **Source repos are distillation inputs**: gakumas (Rust/Windows), ss-assist (TS/React), info-gathering (Python) are mined for stack notes; the repos themselves stay untouched this round.

## Verification

- Every path referenced from `CLAUDE.md` (skills, `docs/*.md`, ADR) exists in the repo.
- Skill frontmatter is valid YAML; `name` matches its directory.
- `setup.sh` reviewed for idempotency (re-run → "already linked"; pre-existing real file → timestamped backup).
- Stack notes contain no project-specific facts (crop regions, hotkeys, game schemas, feed lists).
