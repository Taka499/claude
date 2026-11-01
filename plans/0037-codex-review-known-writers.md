# Plan: step 4 of `/codex-review` names the writers that are not Codex

## Goal

Step 4 of `/codex-review` lists every file in the repository whose change time is newer than the marker taken just before Codex ran, and compares the refs. The step said that anything listed which the session did not write itself is Codex's, and is to be reported as an incident. On 2026-11-01 two sessions found entries that Codex did not write.

1. **gakumas-supportcards.** The check listed `.git` itself, with nothing inside it changed and no ref moved.
   - **The watch:** a 75-second watch of `.git` saw it change about 150 times, every few seconds. The only file seen coming and going was `index.lock`.
   - **The explanation:** a process refreshing the index, such as an editor's git integration or another session's `git status`.
   - **What stayed unidentified:** which process it was. Its git commands end too fast for a `ps` sample to catch one.
2. **This repository.** Plan 0036 went through four Codex passes. After each of the last three, the check listed 5 new loose objects under `.git/objects/`: two commits titled "WIP on feat/task-board-jobs-and-page: …" and "index on …", their trees, and a blob, all unreferenced. No ref moved.
   - **Not Codex's:** the objects were absent from Codex's snapshot.
   - **Who wrote them:** the `security-guidance` plugin (claude-plugins-official, 2.0.17). Its UserPromptSubmit hook records a "git baseline" with `git stash create`, run on a copy of the index each time a prompt reaches the session. A background task's completion notice counts as one.
   - **The proof:** `~/.claude/security/log.txt` has `Captured git baseline: <sha>` for each WIP commit, at its exact time: 14:24:38, 14:27:07 and 14:28:17, then 14:37:56 for the user's next message.
   - **The first pass:** the tree was clean, so `stash create` wrote nothing.
   - **Where it works:** the plugin keeps its index copy in a temporary folder and runs git with `GIT_OPTIONAL_LOCKS=0`, so it is not the poller in case 1.

Both are harmless, but as the step was written, each would be reported as an incident.

## Change

`skills/codex-review/SKILL.md` § 4: the paragraph on entries that are not Codex's now names three kinds, each with how to recognise it:
- **the session's own writes;**
- **an index poller:** `.git` and possibly `.git/index` only, with no ref moved;
- **the plugin's baseline:** "WIP on" / "index on" commits, each matched by a `Captured git baseline` line in the plugin's log.

Anything else stays an incident. This corrects the rule, so the rule is replaced in place rather than added beside the old one.

## Verification

- In this repository, with an uncommitted change, a prompt to the session adds a WIP/index pair whose SHA is logged as `Captured git baseline` (seen four times on 2026-11-01).
- `/codex-review` on this branch's diff.
