# claude — central Claude Code configuration

This repository **is** the live user-level Claude Code configuration (`~/.claude`) for this machine, versioned and developed like software. Merging a PR here changes the harness for every project.

The approach emulates [isamu/claude](https://github.com/isamu/claude) (see the article [「コードレビューをやめた」](https://zenn.dev/singularity/articles/stopped-reviewing-my-code)): the global config lives in a repo, every change is a PR, and the PR history records how the harness evolved. The content, however, follows this user's own system — ExecPlans as immutable narrative logs, ADRs with a three-gate filter and mandatory provenance, and `CLAUDE.md` as an auditable index — originally developed in `Taka499/project-template` and battle-tested in `gakumas-rehearsal-automation`.

## Layout

- `CLAUDE.md` — the global rules file, deployed as `~/.claude/CLAUDE.md`. Thin by design: always-on rules only; long reference material lives in `docs/` and is read on demand.
- `skills/` — user-level skills, deployed as `~/.claude/skills/`. General-purpose only; project-specific skills stay in their repos.
- `docs/` — read-on-demand references: distilled stack notes (`rust.md`, `typescript.md`, `python.md`) and this repo's ADRs (`docs/adr/`).
- `plans/` — lightweight plan files (goal / changes / verification) committed alongside non-trivial PRs. Not full ExecPlans: harness changes are small and reversible, so the ceremony is scaled down deliberately (see `plans/0001-bootstrap-central-claude.md` § Decision Log).

## Deployment

Clone anywhere, then symlink the tracked pieces into `~/.claude` (the rest of `~/.claude` — sessions, todos, settings — is runtime state and stays untouched):

    ./setup.sh        # macOS / Linux / WSL / Git Bash
    ./setup.ps1       # Windows PowerShell (uses junctions for dirs; may need Developer Mode for the file symlink)

Both scripts are idempotent and back up any pre-existing real files before linking. After deployment, the working tree of this clone is live config: keep it on `master` except while developing a change.

## Changing the harness

1. Feature branch, following `CLAUDE.md` § Git Operations (yes, this repo obeys its own rules).
2. Non-trivial change → add a short plan file in `plans/` (goal, changes, verification — ~40 lines, isamu-style).
3. Harness-architecture decision that passes the three-gate test (hard to reverse, surprising without context, real trade-off) → ADR in `docs/adr/`. Expected to stay in the low single digits; most changes need none.
4. PR to `master` with the rationale in the description. Merge = deploy.

## Relationship to project-template

`Taka499/project-template` remains the per-project scaffold: `docs/PLANS.md` (ExecPlan methodology), `docs/adr/README.md` (ADR convention), and the `CLAUDE.md` skeleton that new projects copy. Everything reusable across projects — rules, skills, stack notes — lives here instead and reaches projects through `~/.claude`.
