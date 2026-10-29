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

## Follow-up from the review of PR #48 (2026-10-29)

A review of the PR before merge found three more things. All are fixed on the same branch.

- **The rule missed how the incident happened.** "Never run Codex after a failed write of its prompt" assumes the session knew the write had failed. It did not: it started Codex in the same turn as the Write, so the refusal arrived after Codex was already running. The rule now says to start Codex only once the Write has reported success, never in the same turn. The `grep` covers that case too: if Codex starts before the file exists, the `grep` finds no file and refuses.
- **The placeholder did not match the guard.** The inline template said `(<snapshot path>)`, while the `grep` looks for `$snapshot/repo`. A prompt naming only `$snapshot` would be refused although it is this review's. The placeholder is now `(<the full path of "$snapshot/repo">)`, and the paragraph says the prompt must name that path in full.
- **The same mistake was in `scaffold-project`.** Its step 2 archived the template to the fixed `$TMPDIR/project-template.tar`, so two scaffolds at once could extract each other's archive. The risk is low: both archive the same template, possibly at different revisions, and nothing leaves the machine. The archive now goes into a folder of its own from `mktemp -d`.

The guard was tried in four cases with a scratch folder under `$TMPDIR`: a prompt naming this snapshot runs; a prompt naming another snapshot, a prompt never written, and an empty `$snapshot` (each Bash call is a fresh shell) are all refused.
