# Plan: Remove the git gate hook (`hooks/git_gate.py`)

## Goal

`~/.claude/settings.json` runs `hooks/git_gate.py` from this clone, outside the sandbox, before every Bash call of every session. Plan 0018 added it on 2026-10-12. Approving a task became standing permission to commit on its feature branch, while history on `main`, `master` or `develop` still needed the user's approval. A permission rule matches command text and cannot tell those branches apart; the hook could, by reading which branch is checked out.

On 2026-10-28 the user decided to remove it, after the comparison below. Two things weighed against it:
- **It undid the sandbox.** Every session can write this clone, because `sandbox.filesystem.allowWrite` opens `~/Developer/claude` to all of them. So one sandboxed write became code run outside the sandbox on the next Bash call of every session. That write could be to the script, to a module beside it, or a branch checked out here. It breaks the rule plan 0024 added to `docs/claude-code.md` § Code that runs outside the sandbox.
- **What it guarded alone was small, and it cost prompts.** Most of its prompts repeated another guard or came from commands it could not read (§ Evidence).

## What it guarded, and what stands without it

These stay:
- git's own `reference-transaction` hook, a copy at `~/.config/git/protect-branches` that no session can write. It refuses every update of `main`, `master` or `develop` that is not a merge, whatever program runs git;
- the `ask` rules on `git push` and `git checkout`, and the `deny` rules on `reset`, `rebase`, force pushes, `git add .` and `-A`, `clean`, and the mutating `git -C` forms;
- `git push` and `gh` run outside the sandbox, where `Bash(dangerouslyDisableSandbox:true)` asks;
- in auto mode, the classifier's `soft_deny` entry on protected-branch history and pushes;
- on GitHub, the ruleset against force pushes and deletion (public repositories).

Only the gate covered three things:
1. **A merge into a protected branch.** git's hook allows merges by design.
2. **Switching git's hook off for one command, or using a git that ignores it:** `-c core.hooksPath=…`, a `hook.*` setting, `--config-env`, `GIT_CONFIG_*` variables, and Apple's `/usr/bin/git`.
3. **`git branch -f`, `-d` and `-m` on a feature branch.** Only `-D` had an ask rule.

## Changes

- Delete `hooks/git_gate.py` and `hooks/test_git_gate.py`. The untracked `hooks/.claude/` and `hooks/__pycache__/` stay, per the global rule against deleting untracked files.
- Rewrite every text that described the gate:
  - the global `CLAUDE.md` § Git Operations, in four places;
  - `README.md`:
    - the layout entry for `hooks/` goes;
    - the gate's bullet under § The one file this repo does not deploy becomes what stands in its place;
    - the commit-rule, `autoMode`, `checkout` and `clean` bullets lose their references to it;
    - the overwrite-hook suggestion now points at `docs/claude-code.md`;
  - `docs/claude-code.md` § Permission rules;
  - `commands/commit.md`;
  - `skills/scaffold-project/SKILL.md`;
  - `skills/codex-review/SKILL.md`. Its snapshot clone now uses `GIT_ADVICE=0` instead of `-c advice.detachedHead=false`, which the new `Bash(git -c *)` rule would prompt for.
- `~/.claude/settings.json`, edited by the user, since it is hand-kept per ADR 0002:
  - remove the `hooks.PreToolUse` entry;
  - add to `permissions.ask`:
    - `Bash(git -c *)`, `Bash(git --config-env*)` and `Bash(/usr/bin/git *)`, for item 2;
    - `Bash(git branch -d*)`, `Bash(git branch -f*)`, `Bash(git branch -m*)`, `Bash(git branch -M*)`, `Bash(git branch -C*)`, `Bash(git branch --delete*)`, `Bash(git branch --force*)` and `Bash(git branch --move*)`, for item 3;
  - in the `autoMode.allow` entry that begins "Feature-branch commits", drop the clause "; the git_gate hook asks for the protected branches".

## Other projects

gkms-contest-ai says in two places that "the user's `git_gate.py` hook asks before any merge into" `develop` and `main`: `.claude/commands/coordinate.md` (line 185 on 2026-10-28) and `docs/PARALLEL_SESSIONS.md` (line 25). After this change that is false.
- **Unaffected:** `tools/integrate.sh` and `tools/spawn_worker.sh` each run as one unsandboxed command on the user's approval, so their merges still ask.
- **Affected:** a merge or revert merge into `develop` or `main` made without them now prompts only in auto mode.

That project should correct the two sentences. If it wants a prompt there in every mode, a project-level `Bash(git merge *)` ask rule would also prompt for its workers' merges of `develop` into their feature branches. Not changed here: it is another repository, and the choice is the user's.

## Evidence (2026-10-28)

- **The write.** A sandboxed command opened `hooks/git_gate.py` for appending and wrote nothing, and the open succeeded: the file was writable. Its size and modification time were unchanged afterwards.
- **A module beside the script.** The gate imports `json`, `re`, `shlex`, `subprocess` and `dataclasses`, and its settings entry runs it without `-I`. Measured with the same interpreter (`/opt/homebrew/opt/python@3.14/libexec/bin/python3`, 3.14.9), a `json.py` beside a script ran in place of the standard library's, and with `-I` it did not. So a new `hooks/json.py` would have run outside the sandbox without the gate itself changing.
- **Its prompts.** 626 session logs under `~/.claude/projects` were modified since 2026-10-12. 93 of them hold the gate's `permissionDecisionReason` texts: 225 records, of which a prompt can account for more than one.

  | Reason | Records | Covered without the gate? |
  |---|---|---|
  | git inside another command, or a branch or form it could not read (`fetch`, `merge-tree`, `worktree`, `commit-tree`, `reflog`, `checkout`, `branch`, a setting it did not know) | about 164 | Nothing to cover: these were not writes to a protected branch. |
  | `git push`, `gh pr merge` | 37 | Yes: those ask anyway. |
  | A write to a protected branch | 15 | The 6 commits (4 on `master`, 2 on `develop`): yes, git's hook refuses them. The 6 merges (4 into `develop`, 1 each into `main` and `master`) and 3 pulls on `master`: no. |
  | `core.hooksPath` or a `hook.*` setting | 9 | No. Whether the user or a session wrote them was not read. |

- **History.** Plan 0022 counted three PRs in the gate's first two days that only fixed false prompts, which took 13, 6 and 3 Codex rounds. Plan 0023: an upgrade of Homebrew's default Python removed the gate's interpreter, and the gate failed open on every Bash call from 2026-10-22 until the entry was changed.

## Decision Log (session 2026-10-28)

- **Removal, not a protected copy.** A copy the way `git-hooks/install-global.sh` deploys git's hook would close the exposure. It would keep the parser, its prompts and its upkeep, though. The user chose removal. This follows `CLAUDE.md` § Quality Gates: prefer the fix that removes a step.
- **No ask rule for `git merge`.** A rule cannot tell a merge into `develop` from a merge of `develop` into a feature branch, and the second is standing permission. A merge into a protected branch therefore rests on the written rule, and in auto mode on the classifier. The worst case is an unapproved merge commit on a local protected branch. It is visible, it reaches GitHub only through a push, which asks, and undoing it takes a revert merge or the user's bypass.
- **`Bash(git -c *)` broad rather than per setting.** Setting names are case-insensitive (`core.hookspath`), so a rule naming `core.hooksPath` misses spellings. The cost is a prompt for every `git -c`; the gate's records hold 15 such prompts in 16 days (9 `hooksPath`, 6 unknown settings). `/codex-review`'s clone was the routine use. It now sets `GIT_ADVICE=0`, which, measured with git 2.56.0, silences the detached-HEAD notice that `-c advice.detachedHead=false` did.
- **Left open, knowingly:**
  - `git -C <repo> branch -d …` passes through `allow Bash(git -C * branch*)`. Another eight rules for a rare form are not worth it.
  - Everything a text rule cannot see: `bash -c`, `GIT_CONFIG_*` variables, a script that runs git.
- **Plan 0022 stays proposed.** If unasked merges into protected branches become a problem, making git's hook refuse merges without an explicit marker is the structural fix. It would not need this gate.
- **Not captured, for the user to decide:**
  - Python's import of modules beside the script, for any Python hook, belongs in `docs/claude-code.md` § Code that runs outside the sandbox: protect the script's whole directory, and run it with `-I`.
  - The interpreter-path lesson (plan 0023) leaves the guidance with the gate's README bullet: name a Python hook's interpreter by a version's own link, never a bare `python3`, or a crash makes the hook fail open.
- **No ADR.** Adding a hook back is easy, so the decision fails gate one (hard to reverse).

## Verification

- `python3 -m unittest discover -s git-hooks` passes, and `git-hooks/install-global.sh --check` shows git's hook still configured and refusing a commit on `develop`.
- No `git_gate` remains outside `plans/`.
- After the user's edit, `~/.claude/settings.json` has no `PreToolUse` entry and holds the new `ask` rules, and a Bash call reports no hook error.
