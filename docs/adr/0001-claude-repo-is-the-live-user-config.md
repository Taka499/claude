---
status: accepted
---

# The claude repo is the live user-level config, deployed by symlink

The `Taka499/claude` repository is the single source of truth for the user-level Claude Code configuration: `~/.claude/CLAUDE.md`, `~/.claude/skills`, and `~/.claude/docs` are symlinks (junctions on Windows) into a clone of this repo, created by `setup.sh` / `setup.ps1`. Merging a PR to `master` therefore deploys the change to every project on the machine. Alternatives rejected: packaging as a Claude Code plugin (cleaner versioning and per-project opt-in, but always-on CLAUDE.md rules fit poorly and it adds moving parts) and keeping a copy-into-each-project template (the status quo whose manual propagation this repo exists to eliminate). `Taka499/project-template` survives, shrunk to only the genuinely project-scoped scaffold (PLANS.md, ADR convention, CLAUDE.md skeleton).

A consequence to respect: while a feature branch is checked out in the deployed clone, the live harness runs that branch's config. Isamu hit this exact hazard (his `feat/skills-refresh` plan stacks branches specifically because "main に戻すと生きているグローバル設定が巻き戻る") — keep the deployed clone on `master` except while deliberately testing a change.

Source: user decision, grilling session 2026-08-05 (deployment model chosen over plugin and template options); hazard note per isamu/claude `plans/feat-skills-refresh.md`.
