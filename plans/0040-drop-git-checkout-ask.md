# Plan: drop the `Bash(git checkout *)` ask rule

Issue #64.

## Goal

`permissions.ask` in `~/.claude/settings.json` held `Bash(git checkout *)`. It was added to ask before a branch switch in the deployed clone, which silently swaps the live global config (ADR 0001). It does not do that: sessions here switch branches with `git switch`, which it does not match (README, measured 2026-10-26: 18 `git switch` switches against 2 `git checkout` ones). Since the git gate hook went (plan 0025), its one remaining effect was a prompt for every `checkout` form, the path forms included.

## Measured (gkms-contest-ai, 2026-11-15 → 2026-11-22)

- **Method.** I selected the prompts by folder and time from `~/.claude/permission-requests.jsonl` (the README's `hooks.PermissionRequest` bullet). That log keeps only the first 200 characters of a command, and 50 of the 56 were cut. So I matched each logged prompt, by session id and prefix, to the full command in the session transcripts under `~/.claude/projects/`. All 56 matched. Every one was raised in auto mode.
- **35 of the 56 contained `git checkout`.** The issue, which counted the same eight days, has 53 and 34; the small gap is probably where each count put the window's edges. By form:
  - 22 `--theirs <file>`, taking one side of a generated file while merging the integration branch into a feature branch. The project is removing these at their source;
  - 10 restoring a path: `-- <path>`, `<path>`, or `develop -- <path>`. Most undo a deliberate edit, such as the mutation step in `docs/testing.md`;
  - 2 `--conflict=diff3 <files>` during a merge;
  - 1 `-q -b <branch> origin/<branch>` in a worktree.
  - None switched branches in this clone.
- **Every prompt was approved,** according to the issue. The log records that a dialog opened, not how it was answered.
- **Whole machine, since the log began on 2026-10-28:** 23 logged prompts contain `git checkout`, 22 of them in gkms-contest-ai folders. That is a lower bound, since the log cuts commands.

## Decision

The user chose B on 2026-11-22: drop the rule.
- **Rejected: A, keep it.** It costs the prompts above and guards nothing it was meant to guard.
- **Rejected: C, narrow it to `Bash(git checkout -- *)` and `Bash(git checkout -f*)`.** `git checkout <path>`, with no `--`, discards changes the same way and would not ask. An ask rule beats an allow rule, so no carve-out for `--theirs` could sit beside the broad rule.

## What is lost

- **In auto mode,** the classifier now judges `git checkout -- <path>` as it already judges `git restore <path>`, `git switch -f` and `--discard-changes` (plan 0025 § Left open).
- **In Manual mode,** a `checkout` command is not in `permissions.allow`, so it still prompts. Only auto mode loses the prompt.
- **What stays:** the deny rules for `git checkout .` and `git -C * checkout*`.

## Changes

- `~/.claude/settings.json` (untracked per ADR 0002), edited by the user: `"Bash(git checkout *)"` removed from `permissions.ask`.
- `README.md`: the `git checkout *` bullet now says the rule is gone and why. § Left open, under the git hook bullet, lists `git checkout <path>` beside `git restore`.

## Verification

- `jq '.permissions.ask | index("Bash(git checkout *)")' ~/.claude/settings.json` prints `null`, and `.permissions.deny` still contains both checkout entries.
