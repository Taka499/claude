# Plan: Let /codex-review review a snapshot, and check the repository afterwards

## Goal

`/codex-review` said Codex "reads the diff read-only". Nothing enforced that. Codex runs inside the Claude Code sandbox with the write access the session has, which includes the repository under review. Only the prompt's "Do NOT modify anything" kept it read-only. On 2026-10-12, during a review of this repository's `feat/commit-approval-ladder` branch, Codex made an empty commit, `0f0b81f` "init", authored `x <x>`. The branch had to be rebuilt without it (plan 0018 § Evidence). The skill now gives Codex a copy to read and records the real repository's state, so that any write shows.

## Changes

- **`skills/codex-review/SKILL.md`:**
  - **Description and opening:** they no longer claim read-only. They say what happened, and that Codex now reviews a snapshot that is checked afterwards.
  - **New step 2:** clone the branch into `mktemp -d "$TMPDIR/codex-review.XXXXXX"`; for uncommitted work, apply `git diff HEAD` to the clone. Record the repository's last reflog entry, all refs and `git status --porcelain`. It also explains why `mktemp -d` needs the `$TMPDIR` template on macOS.
  - **Step 3** runs Codex from the snapshot, and its prompt names the snapshot path and adds "do not commit".
  - **New step 4:** record the three lists again, and report any difference to the user as an incident, before any finding. The user decides what to undo, because the global rules forbid rewriting history or deleting untracked files on one's own.
  - **Renumbering:** the remaining steps are renumbered (evaluate is 5, re-run is 6, report is 7), with their cross-references updated; a re-run takes a fresh snapshot.
- **Global `CLAUDE.md` § Skills:** the `/codex-review` line no longer says "read-only".

## Evidence (session 2026-10-12)

- **Round 2 of the review of plan 0018's branch wrote to the repository.** Its empty commit `0f0b81f`, by `x <x>` at 10:49:17, appeared in the branch's reflog between two of the agent's own commits. Nothing else changed.
- **Three later rounds ran on snapshot clones under `$TMPDIR`** (plans 0018 and 0019). Each time, the repository's reflog and refs were identical before and after. In one of them, Codex's log shows it installed and removed a hook inside the snapshot, which shows that the snapshot absorbed what would otherwise have been a write to the repository.
- **The `mktemp` pitfall** comes from plan 0020 § Evidence. A test script using `mktemp -d` without a template got the system temp directory, which the sandbox refused, then ran in this clone and made four commits.

## Decision Log (session 2026-10-12)

- **A clone, not a worktree.** A worktree shares the repository's refs and object store, so a commit made in it lands in the repository. A clone does not.
- **Report and stop; do not undo.** The incident is the user's to resolve. The agent may not rewrite history or delete untracked files without permission.
- **No ADR.** This is a procedure in a skill, easy to change again.

## Verification

- Prose only: there is no test to run. The procedure is the one used for the reviews of plans 0019 and 0020, where the before and after records matched.
- After merge, the deployed skill can be read through `~/.claude/skills/codex-review`, which is linked into this repository.
