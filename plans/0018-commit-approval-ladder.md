# Plan: Approve tasks and merges, not commits

## Goal

Every commit needed the user's approval, two or three times over:
- the agent asked in chat, per `CLAUDE.md` § Git Operations ("NEVER run `git commit` … without explicit user permission for that operation");
- the `Bash(git commit *)` ask rule prompted again;
- in auto mode the classifier enforced the same rule a third time, through an `autoMode.soft_deny` entry and its own reading of `CLAUDE.md`.

With several parallel sessions, those approvals became the bottleneck. This change moves the user's review to where it carries information:
- **the task or plan:** approving it is standing permission to commit on its feature branch;
- **the merge into `main`, `master` or `develop`:** it still needs the user's approval, and it now has to bring the evidence the user needs to approve without reading the diff.

Between the two, machine checks and `/codex-review` stand in for per-commit sign-off. This is Phase 1. Merges stay human until there is a week of data to judge an automatic merge by.

## Changes

- **Global `CLAUDE.md` § Git Operations:**
  - The permission bullet now grants standing permission to commit on a feature branch (and to merge the integration branch into it). Commits on, merges into, pushes to and rebases of `main`, `master` and `develop` still need the user's permission per operation.
  - The commit-size bullet now says "commit and report", where it said "propose".
  - A new bullet makes a merge request bring evidence: checks green on the merged result, the `/codex-review` verdict on the branch's whole diff with every finding fixed or answered, and no decision still open.
  - The sandboxed-git bullet now points to `ask` rules or a hook for approvals, instead of recommending an `ask` rule per command.
- **`commands/commit.md`:** on a feature branch `/commit` commits; on a protected branch it proposes and waits.
- **`hooks/git_gate.py` (new) and `hooks/test_git_gate.py`:** a PreToolUse hook that asks before a `commit`, `merge`, `cherry-pick`, `revert` or `am` writes to a protected branch. It also asks before `gh pr merge`, and whenever it cannot tell the target branch. The rule is a pure function, `decide(command, branch_of)`, with git reached only through the injected `branch_of`.
- **`README.md`:** § Layout gains `hooks/`. § The one file this repo does not deploy gets three updates:
  - the git invariant is rewritten;
  - a new invariant gives the hook's settings entry and why it is guarded;
  - a new invariant says `autoMode` must agree with the rule.
- **`~/.claude/settings.json`** (untracked, applied by the user after merge, so the hook file exists on `master` first):
  - `permissions.ask`: remove `Bash(git commit *)` and `Bash(git merge *)`. The merge rule was added on 2026-10-12, before this design. An `ask` rule cannot be overridden by the hook, so it would make every merge prompt, including merging `develop` into a feature branch. `Bash(git branch -D *)`, added at the same time, stays.
  - `hooks.PreToolUse`: add `{"matcher": "Bash", "hooks": [{"type": "command", "command": "f=\"$HOME/Developer/claude/hooks/git_gate.py\"; if [ -f \"$f\" ]; then /opt/homebrew/bin/python3 \"$f\"; else echo \"git_gate.py not found at $f: the commit gate is off\" >&2; exit 1; fi"}]}`.
  - `autoMode.soft_deny`: replace `Bash(git commit*) / Bash(git push*) without explicit per-operation permission — CLAUDE.md mandates asking before any history-mutating git command` with: `Git history on protected branches: git commit, merge, cherry-pick, revert or am while main, master or develop is checked out, gh pr merge, and any git push, without the user's explicit permission for that operation (global CLAUDE.md § Git Operations)`.
  - `autoMode.allow` (new; keeps `"$defaults"`) gets two entries:
    - `Feature-branch commits: git add <files> and git commit on any branch other than main, master and develop, and merging one of those three into such a branch to update it, are routine under the user's standing permission for an approved task (global CLAUDE.md § Git Operations); the git_gate hook asks for the protected branches`
    - `Codex review: codex exec --sandbox danger-full-access with approvals off, run by the /codex-review skill to review the local diff read-only, is allowed. It runs as an ordinary sandboxed Bash command, so Claude Code's OS sandbox still confines it (writes only to the working directory, $TMPDIR and ~/.codex; network only to the allowlist; credential paths denied), and the user accepted sending the diff and the files Codex reads to OpenAI`

## Evidence (session 2026-10-12; Claude Code 2.1.296, git 2.50.1, macOS 26.7.1)

**The cost (gkms-contest-ai).**
- Commits per day across all branches: 44, 21, 17 and 9 on 2026-10-08 to 2026-10-11.
- A worker's two reviewed commits waited for approval from 2026-10-11 13:13 into the next day.
- Each commit took the chat approval, the `ask` prompt and, where the session ran git unsandboxed, the sandbox-retry prompt.
- `/codex-review` was refused four times by the classifier with `[Create Unsafe Agents]`.

**The reference practice.** isamu, who wrote the article this harness's testing doctrine comes from, and who maintains MulmoTerminal:
- **The last 100 merged PRs of `receptron/mulmoterminal`** (created 2026-10-02 to 2026-10-11):
  - 99 were merged by their author's account, with 0 human approving reviews and 0 GitHub auto-merge;
  - median 24 minutes from open to merge (p90 169), median 1 commit per PR;
  - CodeRabbit commented on 55;
  - PR bodies carry Summary (96), Items to Confirm (87) and User Prompt (87).
- **`main` has no branch protection and no rulesets.** Its first-parent history from 2026-09-28 to 2026-10-09 has 377 merges and 27 direct commits, all release version bumps or release notes.
- **The Codex GitHub workflow has been manual-only since 2026-09-10** (8485fad2d). The loop runs locally through his `/codex-cross-review` skill.
- **His public text lags his practice.** `isamu/claude` at e70498e still says "NEVER run `git commit`, `push`, `merge` … without explicit user permission", and its `pr-babysit` skill confirms each merge. He told the user directly that everything not needing human judgment now merges automatically, and that Codex cross-review is what made that safe.
- **The article (2026-07-27):**
  - Merge condition: all bots sign off, CI is green, and a human confirms, which he calls a formality.
  - Before full automation: reliable rollback and a record of what happened.

**Claude Code behaviour (documentation, read 2026-10-12):**
- Permissions § Extend permissions with hooks: "a matching ask rule still prompts even when the hook returned `"allow"` or `"ask"`". So the `git commit` ask rule has to go for the hook to matter.
- Auto-mode config § Where the classifier reads configuration: "The classifier reads the same CLAUDE.md content Claude itself loads". So the rule text and `autoMode` have to change together.
- `autoMode.allow` entries are exceptions to `soft_deny` rules, and lists that omit `"$defaults"` replace the built-ins.
- `claude auto-mode defaults --label 'Create Unsafe'`: a `soft_deny` rule covering "launching ANY agent … without sandbox isolation AND without a per-action approval/monitor gate". The classifier cannot see that `codex exec` runs inside Claude Code's Seatbelt, hence the allow entry that says so.
- Hooks: exit 2 blocks the tool call; another non-zero exit is a non-blocking error; a hook that crashes or times out does not block.

**Interpreters.**
- `/usr/bin/python3` is 3.9.6 (Command Line Tools 27.0) and is not upgradable on its own.
- `/opt/homebrew/bin/python3` is 3.14.3 and comes first on the session `PATH`.
- Python exits 2 on a missing script file. Measured: the unguarded command exits 2; the guarded one exits 1 with its message.

## Decision Log (session 2026-10-12)

- **Standing permission comes per task, not per commit.** This is the reference practice, and it keeps a human decision where one exists: what to build, and whether to integrate it. A commit on an unshared feature branch can be undone until it merges.
- **Merges stay human in Phase 1.** Phase 2, automatic merging when every check passes and nothing waits on the user, is decided after a week of data: approvals per day, commits per day, time from DONE to merge, and reverts or fixes of merged work.
- **A hook, not an `ask` rule.** Only a hook can see the branch. It asks when it cannot tell, so an unparseable command or an unknown directory prompts rather than passing.
- **The interpreter is named by absolute path, and the entry is guarded.** A crashed hook fails open, and an unguarded missing file blocks every Bash call. The code needs 3.10, and the user chose to require a modern Python rather than write for Apple's 3.9.
- **Python, not TypeScript, for the hook.** The parse needs a shell lexer, which Python has in `shlex`; a TypeScript version would need a package such as `shell-quote`, plus `tsc` for its types to be checked at all. This repo has no `package.json` or toolchain. Node here lives under `nvm`, at versioned paths a hook cannot rely on. Revisit if the harness grows enough scripts to justify a TypeScript toolchain with strict lint.
- **Push is unchanged.** It is not the bottleneck, and the keychain deny makes it run outside the sandbox anyway.
- **The rule is replaced in place.** It is a correction of the per-commit rule, made with the user's agreement (§ Continuous Learning). A project that restates the old rule, such as a coordinator's command file asking before every commit, should drop that restatement. Nothing else migrates.
- **No ADR.** The rule is text and settings, easy to reverse, so it fails the first gate.

## Verification

- `python3 -m unittest discover -s hooks`: 32 tests pass under Python 3.14.3. The suite includes an end-to-end run of the script against a real throwaway repository on `develop` and on a feature branch.
- Each of five deliberate breakages, run on a scratch copy, failed tests:
  - an empty protected set: 16 failures and 1 error;
  - no subshell scope for `cd`: 1 failure;
  - no fail-closed path on an error: 1 error;
  - no `--abort` exemption: 1 failure;
  - unknown branches passing: 4 failures.
- The guarded hook command was run against a present and a missing script file.
- After the user applies the settings, check in a live session:
  - a commit on a feature branch runs with no prompt;
  - a commit on `develop` prompts with the hook's reason.
