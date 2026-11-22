# Plan: a scratch root per session, and a delete command confined to it

Issue #65.

## Goal

`Bash(rm *)` is in `permissions.ask`, temp cleanup included. The README bullet "`Bash(rm *)` stays in `permissions.ask`" gives the reasons, weighed on 2026-10-26: `$TMPDIR` is shared by every session, project and app on the machine; nothing empties it; and a command cannot prove that a path it deletes is its own. That bullet also named the shape that would cut the prompts while the rule stays: a root per session plus a delete command confined to it. This plan builds that shape.

**Measured on 2026-11-22:**
- **The prompts.** In gkms-contest-ai, between 2026-11-15 and 2026-11-22, 18 of 56 permission prompts were `rm`, and all were approved. 15 deleted scratch that the same session had made under `$TMPDIR`. The full commands were matched from the transcripts, as plan 0040 describes. The project's written habit, "use a fresh `mktemp -d`", dated 2026-10-14, did not hold.
- **The shared root.** `$TMPDIR` (`/var/folders/…/T/`) held 4,330 entries and 26 GB:
  - 19.2 GB: 259 `verify-*` folders, left by gkms-contest-ai's `tools/verify.py`, which uses `mkdtemp` and never deletes;
  - 1.3 GB: 125 `/codex-review` snapshots;
  - 3,126 test-fixture folders, 0.5 MB in total.

  Claude Code's own `/tmp/claude-501` held 240 MB. Since the sandbox went off (plan 0034), every command gets the same `TMPDIR`, so the README's first reason no longer applies.

## Decisions (the user, 2026-11-22)

- **D1. The root is `/tmp/cs/<session id>/`, and a SessionStart hook points `TMPDIR` at it.**
  - **How:** the hook creates the root (mode 700) and appends `export TMPDIR=/tmp/cs/<id>/` to `CLAUDE_ENV_FILE`. Per the hooks docs, every later Bash command in the session runs that file first.
  - **What it gains:** anything that reads `TMPDIR` lands in the session's root, with no habit to remember (global `CLAUDE.md` § Quality Gates). That covers Python's `tempfile` (so pytest, uv and `verify.py`), Node's `os.tmpdir()`, and `mktemp "$TMPDIR/x.XXXXXX"` (so `/codex-review`'s snapshots).
  - **Not covered: macOS `mktemp` without a template.** `mktemp -d` and `mktemp -d -t x` ignore `TMPDIR` and use the per-user `/var/folders/…/T/` (measured on 2026-11-22). Their folders stay outside the root, and `scratch-rm` refuses them.
  - **The id:** `CLAUDE_CODE_SESSION_ID` is documented (env-vars page, read 2026-11-22) as matching the hooks' `session_id`. It changes on `/clear`, so a cleared session gets a new root.
  - **The cost:** a fixed name such as `$TMPDIR/uvcache-x` is no longer shared between sessions.
  - **Why so short:** macOS limits a Unix socket path to 104 bytes. Today's `TMPDIR` is 49 characters, and `ssh-askpass-<uuid>.sock` files sit in it. `/tmp/cs/<36-character id>/` is 45, so no socket path gets longer.
  - **Rejected:** a `CLAUDE_SCRATCH` variable with `TMPDIR` left shared. It relies on the habit that already failed.
- **D2. `scratch-rm` deletes only inside the current session's root.** It takes paths and removes each as `rm -rf` would.
  - **What it reads:** it never reads `TMPDIR`. It builds the root from `CLAUDE_CODE_SESSION_ID`, which must look like a UUID.
  - **What it refuses:** it resolves each target's parent with `pwd -P` and refuses, before deleting anything, any path that is not strictly inside `/private/tmp/cs/<id>/`. That includes the root itself, `.`, `..` and symlinked escapes.
  - **Its environment:** it resets its own with a fixed `PATH`.
  - **If an agent changes `TMPDIR`,** its files land outside the root, and deleting them goes back to `rm`, which asks.
- **D3. Deployment: an installed copy.** The source is in this repository under `scratch/`. `scratch/install.sh`, run by the user, copies it to `~/.local/libexec/claude-scratch/`, outside every repository, as `git-hooks/install-global.sh` does. An `Edit(…)` deny rule covers the copy.
  - **The allow rule** names the copy's absolute path. A bare `scratch-rm` would let a look-alike earlier on `PATH` match it.
  - **Rejected:** linking the repository copy through `~/.claude`. Any session working in this clone could then edit what the allow rule runs.
- **D4. Cleanup is manual.** `scratch-sweep [days]`, default 7, deletes roots under `/tmp/cs` whose newest file is older than that, and never the current session's. The user runs it when they choose. Nothing deletes automatically.
  - **Rejected:** a sweep at SessionStart. That would be a hook that deletes.
  - **Rejected:** deleting at SessionEnd. Its default timeout is 1.5 s, the docs promise nothing on a crash, and a later `--resume` would find its files gone.

## Left open, knowingly

- **A forged session id.** A session that sets `CLAUDE_CODE_SESSION_ID` itself, for example by appending an `export` to its env file, makes `scratch-rm` delete inside another session's root. Every session runs as the same user, and with the sandbox off nothing separates them. The damage stays inside `/tmp/cs`.
- **A swap between check and delete.** The parent is resolved before `rm` runs. A process that replaces a checked folder with a symlink in that gap could redirect the delete. `rm -rf` itself does not follow symlinks inside the tree it removes.
- **Subagents.** The docs do not say whether a subagent's Bash commands get the parent's id, or the env file. Measured below.
- **What is already in `$TMPDIR`** stays. This plan changes where new scratch goes.
- **`Bash(rm *)` stays,** for everything outside the root.

## Changes

- `scratch/session-start`, `scratch/scratch-rm`, `scratch/scratch-sweep`, `scratch/install.sh`, and their tests in `scratch/test_scratch.py`.
- `~/.claude/settings.json` (untracked per ADR 0002), edited by the user:
  - a `hooks.SessionStart` entry running the installed `session-start`;
  - `permissions.allow` gains `Bash(<copy>/scratch-rm *)`;
  - `permissions.deny` gains `Edit(<copy>/**)`.
- `README.md`: the `Bash(rm *)` bullet is updated for the sandbox being off and for the root.
- Global `CLAUDE.md`: one line telling sessions to delete scratch with `scratch-rm`.

## Verification

- **Tests:** deletion inside the root; refusal of the root itself, of `..`, of an absolute path outside, of a symlink pointing out, of a missing or malformed id, and of an option-looking argument. Each guard is shown failing when removed.
- **In a new session after install:**
  - `echo $TMPDIR` prints the root;
  - `mktemp -d` lands inside it;
  - `scratch-rm` on such a folder runs with no prompt, while `rm` on the same folder still asks;
  - a subagent's Bash prints its `CLAUDE_CODE_SESSION_ID` and `TMPDIR`.
