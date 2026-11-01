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

`skills/codex-review/SKILL.md` § 4 now asks first whether Codex could write at all. That is the question the step exists for: its read-only sandbox may silently not be in force, after a mistyped flag or a CLI upgrade. Two direct checks answer it:
- **The run's own header.** `codex exec` prints the mode its commands run under; the log must show `sandbox: read-only` and `approval: never`.
- **A canary run by the CLI, not the model.** `codex sandbox -c 'sandbox_mode="read-only"' -- touch` runs once inside the snapshot and once beside it. Both writes must be refused with `Operation not permitted`, and neither file may exist.

**When both hold (`SANDBOX HELD`):** nothing on the file list is Codex's. The known writers are named only so each entry can be explained:
- the session's own git commands;
- a process polling the index;
- the security-guidance plugin's stash baseline and its empty blob.

An entry they do not explain is reported as another process's write.

**When either fails (`SANDBOX NOT SHOWN`):** the earlier rule stands. Every listed entry the session did not write is Codex's, and the review is reported as run without a proven sandbox.

Step 3's inline form also saves Codex's log to `"$snapshot/review.txt"`, as the stdin form already did, so the header can be read.

## The parser that was dropped

The first version of this branch attributed each entry differently: it read the commands Codex ran, from its log, and excused an entry only when no command could have written into the repository. That meant proving a negative over shell syntax, and it did not converge.

**Review rounds:** six `/codex-review` passes and four rounds of the security-guidance plugin's automated review each found a new way a command could name a path the parser did not see. Each fix was sound and each round found another:
- `../` and symlinks;
- `file://` and paths attached to options;
- `./` after a prefix;
- escapes and quoting;
- `#`;
- braces and zsh globs;
- bare variables;
- a symlink removed after use.

**Size:** the checker reached 283 lines, its tests 172, and step 4 a long list of what it could not see.

**Why every hole was the same hole:** each one needed the sandbox to be off, so a direct check of the sandbox closes all of them at once, and needs no parsing. The user asked whether the fixes were only patching holes, and whether to step back. With the user's go, this branch took that step.

The parser's commits stay in the branch's history: `85ba6cd`, `96851db`, `91fde17`, `fbfc820`.

## Verification

- **The canary under each mode,** with codex-cli 0.150.1:
  - **read-only:** both writes refused with `Operation not permitted`, and neither file exists;
  - **workspace-write:** both files written;
  - **danger-full-access:** both files written.
- **The step-4 block on a real review snapshot** (the sixth pass's): it prints `SANDBOX HELD`.
- **Negatives:**
  - **a log header edited to `sandbox: workspace-write`** fails the header check;
  - **the canary run under `workspace-write`** does not print `SANDBOX HELD`.
- **The header check on today's logs:** all ten show `sandbox: read-only` and `approval: never`.
- **A model-run canary, tried first:** asked in the prompt to run the `touch`, Codex replied "I'll run the exact command now" and then ran nothing. That is why the CLI runs the canary.
- **The known writers,** from the first version's evidence:
  - **the plugin:** each WIP commit matched a `Captured git baseline` log line to the second;
  - **its Stop hook:** the empty blob matched a `Stop hook:` line;
  - **the poller:** gakumas-supportcards' watch saw only `index.lock`.
- `/codex-review` on this branch's diff.
