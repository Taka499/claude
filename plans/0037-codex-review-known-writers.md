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

**Only after a command check.** Each signature can also be made by Codex, so it excuses an entry only after a new script, `skills/codex-review/commands_check.py`, has read Codex's log. The script requires two things of every command Codex ran:
- **where it ran:** in the snapshot;
- **where its paths land:** inside the snapshot, or under a system prefix.

**How a path is resolved:** against the command's working directory, with `~` and `$HOME` expanded and symlinks followed. So `../` out of the snapshot is caught, and so is a link into the repository, such as those under `~/.claude` in this setup.

**Commands are split as a shell splits them** (Python's `shlex`), so quotes and backslashes cannot disguise a path. A command that will not split is flagged.

**How each word is checked:** every word is checked, not only path-like ones. Before resolving, the check expands `~user` and brace patterns, and matches globs against the files there.

**Paths attached to a prefix count too:**
- `file://` URLs to this machine;
- a path right after an option's letters (`-C/p`);
- a path after `:`, `@` or `+`.

**What the check refuses:**
- a path through any other variable;
- a log with no records, or with a record of an unknown shape or with no status line.

**A flag is judged by hand:**
- **only reads,** such as a search pattern that holds a path: the classification stands;
- **could write, or unclear:** every entry is Codex's.

**A review with no snapshot** (a repository with no commit) skips the check, and treats every entry as Codex's.

**What the plugin's signature requires:**
- the log line is written after the marker, at the second of the WIP commit's time;
- every other new object is reachable from that commit (`git rev-list --objects <WIP>`, its whole closure, since git refreshes the times of an object that already exists);
- the empty blob `e69de29…` that the plugin's Stop hook writes with `git add -N` when files are untracked is confirmed by its `Stop hook:` log line.

**Step 3:** its inline form now saves Codex's log to `"$snapshot/review.txt"`, as the stdin form already did, so the script has a log to read.

**Everything else stays an incident:** any entry that matches no kind, and every entry when the check fails. This corrects the rule, so the rule is replaced in place rather than added beside the old one.

**Not caught:** a command that builds the repository's path out of sight, for example by decoding it. Like a process setting times back, that is deliberate evasion, outside what step 4 can see.

## Verification

- In this repository, with an uncommitted change, a prompt to the session adds a WIP/index pair whose SHA is logged as `Captured git baseline` (seen four times on 2026-11-01).
- **`python3 -m unittest discover -s skills/codex-review`:** 19 tests. Each of the check's 16 rules was removed in turn, with bytecode caching off, and every one of those 16 versions failed at least one test.
  - **They cover:**
    - the repository named in four forms, by `../` from the snapshot, and through a symlink;
    - nine prefix-attached forms;
    - ordinary tokens such as `HEAD~1`, `HEAD:path`, `origin/master...HEAD` and a URL to GitHub, which pass;
    - the plugin's log;
    - a command run outside the snapshot;
    - other variables and outside paths;
    - an empty log, an unknown shape, a record with no status line, and a script that will not split;
    - paths disguised by backslashes or by quotes;
    - the exit statuses.
  - **Each tested rule shown to catch a break,** its tests failing once the rule is removed:
    - realpath;
    - the snapshot test;
    - the repository test;
    - the variable test;
    - the URL rule;
    - the option rule;
    - the `:@+` rule;
    - the status-line rule;
    - the token filter;
    - the reason ranking;
    - the shell-style split;
    - the parse refusal.
- **Against this session's nine real Codex logs,** 23 commands, all of which split:
  - **Five pass.**
  - **Three are flagged for read-only searches:** an `rg` pattern holding `/Users` and `~`, and two `sed '/…/,/…/p'` addresses. That is the judged-by-hand case.
  - **One is flagged for an example log record** pasted into the prompt, which Codex's log echoes back. That is the unknown-shape case.
- **The plugin's signature, against the real objects:**
  - **The pair from 14:24:38:** all 5 of its objects are reachable from `d3d117d`, and the log line has the commit's second.
  - **The sixth review pass's run (14:59):** 9 objects appeared. 8 are reachable from the WIP commit `0b32118`, which is logged at 14:59:57. The ninth is the empty blob, written at 14:59:38 by the plugin's Stop hook (logged `Stop hook: review_set=4`) while two new files were untracked. That led to the Stop-hook rule.
- `/codex-review` on this branch's diff.

## Codex review (2026-11-01)

**First pass, at `897ef67`: CHANGES REQUESTED.** Both HIGH findings were accepted.
- **HIGH, the poller's signature could excuse Codex creating and deleting a file in `.git`.**
- **HIGH, the plugin's signature could excuse Codex running `git stash create`, or appending the matching log line.** "At the commit's time" was also too loose.

**The fix:** both signatures now apply only after the command check, and the plugin's signature gained the time and object conditions. The rest of Codex's suggestion was not taken: process attribution that Codex cannot forge would need tracing every process on the machine, and the threat step 4 guards against is an ordinary command landing in the repository after the sandbox silently dropped. That command names the repository, so the check sees it.

**Two LOW findings confirmed the rest:** no contradiction with the rest of the skill, and the citations follow § Continuous Learning.

**Second pass: CHANGES REQUESTED.** Every finding was accepted.
- **HIGH, the check matched path strings.** A `../` or a symlink reached the repository unnamed. This session had found the same gap in its own reading. Fixed: paths are resolved, and links are followed.
- **MEDIUM, an empty or reshaped log passed as "0 commands".** Fixed: the check fails closed.
- **MEDIUM, a review with no snapshot could not pass the check.** Fixed: that mode skips the check, and counts every entry as Codex's.
- **LOW:** the redirect in step 3 is consistent with the rest of the skill.

**Third pass: CHANGES REQUESTED.** Every finding was accepted.
- **HIGH, a path attached to a prefix went unseen.** Examples: `file:///repo/x` and `-o/repo/x`. This session had found the same gap while the pass ran. Fixed by the prefix rules.
- **MEDIUM, a record with no status line was accepted.** Fixed: it fails closed.
- **MEDIUM, no test covered the tokenizer's edges.** Fixed: three tests added, each shown to catch its rule's removal.
- **LOW:** the judged-by-hand rule is safe as written.

Codex could not run the tests in its read-only sandbox, since `TemporaryDirectory` had nowhere to write. This session ran them.

**Fourth pass: CHANGES REQUESTED.** Every finding was accepted.
- **HIGH, an attached path spelled `./…` was not examined.** Example: `-o./../../repo/x`.
  - **The fix:** any path-like remainder after a prefix is now checked.
  - **Ranking:** when a token can be read several ways, the gravest reason is reported, so a path into the repository wins over "outside the snapshot".
- **MEDIUM, § 4's claim did not match:** it holds now.
- **LOW:** ordinary review commands still pass.

**Fifth pass: CHANGES REQUESTED.** It confirmed the fourth pass's finding resolved.
- **HIGH, a path disguised by backslashes passed.** Example: `\/Users\/…`.
  - **The fix covers the class,** quotes as well as backslashes: commands are now split by `shlex`, as a shell splits them.
  - **Still out of scope:** `$'…'` quoting, `eval` and the like, named as such in § 4.
- **MEDIUM, § 4's claim:** updated to match.

**Sixth pass: CHANGES REQUESTED, one MEDIUM, accepted.**
- **The finding:** a valid heredoc holding an apostrophe does not split under `shlex`. It is flagged, which is safe, but § 4 said only commands that "will not split" are flagged. § 4 now says so.
- **The pass's own LOW:** Codex found no ordinary write that names its path and passes the check.
- **Applying the rules to that pass's own run** found the plugin's Stop-hook blob and the closure point above. § 4 gained both.
- **Not re-run:** a seventh pass was not run. The one finding was wording, and the new rule only excuses a single fixed object, confirmed by its log line and gated by the check Codex had just passed.

**The security-guidance plugin's automated review of the commit and of the push** found five more gaps. All were real and all are fixed, each with a test:
- **`~user/…`** was not expanded.
- **Brace expansion** was not modelled.
- **A status-like line inside a script** could end its record early. A record must now split as exactly `<shell> -lc <script> in <dir>`.
- **A glob** could reach a symlink in the snapshot.
- **A bare word naming a symlink** in the snapshot, as in `echo x > lnk`, was never resolved. Every word is checked now.

**Real logs:** of this session's ten, 23 commands in all, five pass. The other five are flagged:
- three read-only searches;
- the echoed example record;
- one heredoc carrying a Python program, whose braces do not expand. That falls under "a program that picks its own paths", judged by hand.
