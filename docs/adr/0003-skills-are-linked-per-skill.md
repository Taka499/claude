---
status: accepted
---

# `skills/` is deployed per skill, not as a directory

`~/.claude/skills` is a **real directory** that this repo links into one skill at a time, unlike `CLAUDE.md`, `docs/` and `commands/`, which are linked whole (ADR 0001). The reason is ownership: `~/.claude/skills` is a shared namespace that other tools install into. MulmoTerminal wrote ten skill directories into it mid-session, and because the directory was a symlink, those ten landed in this repository's working tree as untracked files. Linking a whole directory declares "this repo owns every skill on this machine", which was never true and becomes less true over time as more tools ship skills.

The rejected alternative was a `.gitignore` allowlist — `/skills/*` plus a `!/skills/<name>/` negation per skill we own — which keeps the whole-directory link and the instant liveness that comes with it (a new `skills/foo/SKILL.md` is live the moment it is written, with no redeploy). It was rejected on failure mode. Forget to add the negation and your own new skill is live but *untracked*, hiding inside a `git status` listing full of vendor noise — silent, and lost on the next machine. Forget to re-run `./setup.sh` under per-skill linking and the skill is tracked but not live, which announces itself the first time it fails to fire. A loud failure costing one command beats a silent one costing the work.

Two consequences follow. Adding or renaming a skill now requires a `./setup.sh` re-run, and the script grew a prune step, because a skill deleted from the repo — or merely absent on the branch now checked out — leaves a dangling link behind; prune only ever removes links that point into this repo. And because migrating off the old layout means moving files the user owns out of the repository, `setup.sh` refuses to run against the old layout and prints the migration steps rather than guessing which skills are external: an uncommitted skill of your own is indistinguishable from an installed one, and guessing wrong moves your work.

This narrows ADR 0001 rather than reversing it: the repo is still the live user-level config deployed by symlink, and `docs/` and `commands/` are still linked whole because nothing but this repo writes there. If that changes for either of them, the same fix applies.

Source: user decision, session 2026-08-24, prompted by MulmoTerminal installing ten skills into the working tree during the previous session. Per-entry symlink resolution was verified empirically first, by loading a probe skill whose directory was a symlink pointing outside the repo; prune and external-skill safety are covered by the checks recorded in `plans/0004-skills-ownership.md` § Verification.
