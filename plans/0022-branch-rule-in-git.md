# Plan: Move the protected-branch rule from command text into git

Status: proposed, for the user's review. Nothing here is built yet.

## Goal

`hooks/git_gate.py` decides from a Bash command's text whether the command could write to `main`, `master` or `develop`, and asks whenever it cannot vouch for it. Vouching takes three open-ended bodies of knowledge:
- shell syntax: here-documents, quoting, nested shells, variables;
- git's commands: git 2.56 has 181 (`git --list-cmds=main`), and the gate classifies about 60;
- the options of each command that can move a branch (`branch`, `fetch`, `switch`, `worktree`, …).

Each gap is a false ask that costs the user an approval. Each fix is a PR with a long Codex review. The user asked on 2026-10-14 whether these fixes will keep coming. They will, so this plan proposes ending them structurally.

Git's own `reference-transaction` hook (`git-hooks/reference-transaction`) already sees every branch update made through git, however the command is written. Today it refuses every update of a protected branch except a merge. If it refused merges too, unless the command carries an explicit marker, git itself would enforce the whole rule. `git_gate.py` would then only need to ask when it sees the marker or one of the few ways to switch the hook off. Those are rare words, whatever the rest of the command looks like.

## Evidence (2026-10-14)

- **Three false-ask PRs since `git_gate.py` landed on 2026-10-12.** Codex took 13, 6 and 3 rounds:
  - #30: here-documents and nested shells, and the `/codex-review` snapshot fetch;
  - #31: `merge-tree`;
  - #32: `branch --list` with a pattern.
- **gkms-contest-ai's coordination-loop worker got 14 asks from `git_gate.py` between 2026-10-12 and 2026-10-14:**

  | Kind | Asks | Example |
  |---|---|---|
  | Shell syntax | 6 | "git runs inside another command" (4), "could not tell which branch" (2) |
  | Settings allowlist | 2 | |
  | Command options | 2 | `fetch`, `branch` |
  | Unclassified subcommand | 2 | `merge-tree` |
  | Bypass settings | 2 | `core.hooksPath`; the only intended asks |

- **gkms-contest-ai's engine-deviations worker, 2026-10-14 13:47 JST:** `git hash-object -w` asked as unclassified. The same command's `git update-index --cacheinfo` would have asked next.
- **The docstring says listing dangerous shapes cannot be completed.** `git_gate.py` records that finding from review. It stays true. This plan keeps an allowlist, but moves it to where it is finite: the hook lets a protected branch move in one shape only, whatever command or program moved it.

## Proposed design

1. **`git-hooks/reference-transaction`:**
   - An update of `main`, `master` or `develop` needs the environment variable `PROTECT_BRANCHES_ALLOW` naming that branch. Without it, the update is refused, whatever its shape.
   - With it, today's merge-only rules still apply.
   - Creating the branch stays allowed: a first commit, `git branch develop <start>`.
2. **`hooks/git_gate.py` asks only for:**
   - the marker, anywhere in the command text;
   - anything that stops git from running the hook:
     - `core.hooksPath` and `hook.*` settings (as today);
     - new: `include.*` and `includeIf.*` settings, `GIT_CONFIG_GLOBAL` (today `/dev/null` passes), `HOME` changed or cleared for git (`HOME=…`, `env -i`, `env -u HOME`);
     - a `PATH` prefix (as today) and Apple's `/usr/bin/git` (as today);
   - `push` and `gh pr merge` (as today).

   Everything else is silent. The shell parsing, the subcommand tables, the option rules and the allowlist of settings that name no program all go. A program that git runs is no more able to move a branch than one the agent runs directly.
3. **Callers that update a protected branch locally add the marker:**
   - gkms-contest-ai's `tools/integrate.sh`, inside the script; its run is already approved each time;
   - the user's own merges;
   - syncing a local `master` after a GitHub PR merge: `PROTECT_BRANCHES_ALLOW=master git pull --ff-only`. Today that pull already asks.
4. **Documents:**
   - global `CLAUDE.md` § Git Operations: the protection bullet, and how a merge is approved;
   - `README.md`;
   - `git_gate.py`'s docstring.

   `install-global.sh --check` also proves that a merge into `develop` without the marker is refused.

## Rollout order

The new hook refuses today's merge flows the moment it is installed. And a stripped `git_gate.py` would let them through silently until it is. So the order is:
1. **PR A:** the hook, the marker ask in `git_gate.py`, and the documents. Then the user runs `install-global.sh`.
2. **gkms-contest-ai:** `integrate.sh` adds the marker.
3. **PR B:** strips `git_gate.py`'s parser, only after `install-global.sh --check` passes with the new hook.

## Open questions for the user

1. **Whom the marker binds.** Required everywhere, it also refuses the user's own `git merge` or `git pull` on a protected branch typed in a terminal. Claude Code sets `CLAUDECODE=1` in its Bash commands (seen 2026-10-14), so the hook could require the marker only there, and leave the user's terminal as today. Then `git_gate.py` must also ask when a command unsets `CLAUDECODE`. Recommended: Claude Code sessions only. Still to measure: whether `!` commands carry `CLAUDECODE`.
2. **The marker's form.** An environment variable naming the branch shows what is approved in the prompt itself: `PROTECT_BRANCHES_ALLOW=develop git merge --no-ff feature/x`. A `-c` setting is the alternative. Recommended: the environment variable.
3. **Repositories outside the owner check** (third-party clones such as mulmoterminal). There the hook does nothing, so a stripped `git_gate.py` would no longer guard their `main`. Two options:
   - extend the marker rule, without the merge-only shape, to every repository;
   - have `git_gate.py` ask on any git write in a repository with no remote under `Taka499` or `tia-tools`.

   Recommended: extend the rule.
4. **Push.** Keep `git_gate.py`'s push ask and the `Bash(git push *)` rule as they are. Pushes also run outside the sandbox, which prompts. Moving push into a `pre-push` hook is out of scope.

## Accepted gaps (unchanged)

- A process that writes ref files itself.
- A script file that sets the marker. Today a script can merge into `develop` with no marker at all, so this gap narrows.
- Apple's git where no Homebrew git is installed.

## Verification (when built)

- **Hook tests (`git-hooks`), with Homebrew git 2.56.** Without the marker, each of these is refused on a protected branch:
  - commit, merge, `merge --ff-only`, pull;
  - `update-ref`, `branch -f`, `checkout -B`;
  - `fetch` into `refs/heads/…`;
  - cherry-pick, reset.

  With the marker, a merge passes and a non-merge is still refused. Other branches are untouched, and creating a branch is allowed. Each rule is broken deliberately and shown to fail tests.
- **Measure, not assume, on git 2.56:** that `GIT_CONFIG_GLOBAL=/dev/null`, a changed or cleared `HOME`, `-c include.path=…` and `-c core.hooksPath=…` each stop the hook. Each must then be an ask in `git_gate.py`.
- **`git_gate.py` tests:**
  - a replay set of every false ask recorded so far (the loop worker's twelve, engine-deviations' `hash-object`) is silent;
  - the marker and each bypass ask.
- **`/codex-review`** of each PR, in a snapshot clone.

## Decision Log

- 2026-10-14, the user: plan the redesign first. No more one-off fixes to `git_gate.py`'s text parser meanwhile; occasional false asks are approved by hand. The `hash-object` / `update-index` false ask from engine-deviations is left unfixed.
