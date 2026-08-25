---
status: accepted
---

# `settings.json` stays untracked; the repo carries the policy it must satisfy

`~/.claude/settings.json` is **not** deployed from this repo, unlike `CLAUDE.md`, `skills/`, `docs/`, and `commands/`. Claude Code owns that file and rewrites it at runtime — `effortLevel`, `tui`, `alwaysThinkingEnabled`, `agentPushNotifEnabled`, and `enabledPlugins` are all written by the app itself, and there is no user-level `settings.local.json` tier to separate app-written preferences from hand-authored policy (the `.local.json` scope is project-only). Symlinking it was rejected because an app write via temp-file-and-rename replaces the symlink with a regular file, silently detaching the deployment while everything still appears to work; generating it by deep-merging a tracked base plus a per-OS overlay was rejected as machinery whose upkeep exceeds the value of versioning a file one machine edits through a settings UI.

The cost accepted in exchange is real: `permissions` is where rules like "never commit without permission" are actually *enforced*, and that enforcement layer is now unversioned. A live `allow` entry for `Bash(git commit *)` contradicted global `CLAUDE.md` § Git Operations for an unknown length of time, which is exactly the failure this ADR does not prevent. The mitigation is documentary rather than mechanical: `README.md` § The one file this repo does not deploy states the invariants the live file must satisfy, so the contradiction is at least findable by reading the repo. Revisit if Claude Code gains a user-level local-override tier, which would make a clean tracked/untracked split possible.

Hook commands are a second consequence. They run under `sh -c` on macOS and Linux and under Git Bash on Windows, so a bare `afplay …` produces a non-blocking hook-error notice on every Windows notification. Since the file is untracked and cannot reference a repo-relative helper script that is guaranteed to exist, hook commands must stay self-contained and portable: branch on `uname -s` inline and end with `exit 0` so no platform ever surfaces an error.

Source: user decision, session 2026-08-16, after a repo audit found the `git commit` allow-vs-`CLAUDE.md` contradiction; settings tiers and hook execution model confirmed against code.claude.com/docs/en/settings and /hooks the same day.
