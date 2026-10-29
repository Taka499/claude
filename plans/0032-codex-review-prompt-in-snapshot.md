# Plan: codex-review keeps its prompt and output inside the review's snapshot

## Goal

The `codex-review` skill told a worktree-isolated session to write its prompt to `$TMPDIR/codex-prompt.txt` and Codex's output to `$TMPDIR/codex-review.txt`. Both are fixed names in a folder that every session on the machine shares. On 2026-10-29 a session in gmks-hif-final-stats reviewed a branch with them. Its run went wrong in four steps:

1. **The write was refused.** The Write tool refused to overwrite the prompt file, because the file existed and had not been read in this session. Another session had left its own prompt there, for a different project, pointing at that session's snapshot.
2. **Codex ran anyway.** The session started Codex in the background, in the same turn, before it saw the refusal.
3. **It reviewed the wrong project.** Codex read the stale prompt. It ran one read-only command (`git status`, `git diff`) in the other session's snapshot, and sent that diff to OpenAI.
4. **It was stopped within seconds.** Nothing was written to either repository.

The session first saw the failure when the prompt's first line, read back, named the other project.

## Changes

`skills/codex-review/SKILL.md` § Run Codex, the stdin form:
- The prompt goes to `"$snapshot/prompt.txt"` and the output to `"$snapshot/review.txt"`. That folder comes from a fresh `mktemp -d`, made for this review, so no other session writes there.
- A `grep -qF "$snapshot/repo" "$snapshot/prompt.txt"` before `codex exec` refuses a prompt that does not name this snapshot.
- A paragraph says why, gives the measured case, and adds: never run Codex after a failed write of its prompt.

The inline form (the prompt in the command) is unchanged: it reads no file.

## Verification

- `grep -n 'TMPDIR/codex' skills/codex-review/SKILL.md` finds two lines, neither a fixed path the skill writes. One is the `mktemp -d "$TMPDIR/codex-review.XXXXXX"` template, a new folder per review. The other is the new paragraph naming `$TMPDIR/codex-prompt.txt` as what not to do.
- In gmks-hif-final-stats the next five reviews of the same branch (2026-10-29) used `$snapshot/prompt.txt` and `$snapshot/review.txt`. Each prompt named its own snapshot, and in every review's log, every command ran in that snapshot.
- The guard, tried by hand: with a prompt naming another folder, the `grep` exits 1 and the run does not start.
