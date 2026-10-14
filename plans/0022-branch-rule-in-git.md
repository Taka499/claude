# Plan: Move the protected-branch rule from command text into git

Status: proposed; nothing here is built yet. Revised after three Codex reviews of this plan; the user settled its five open questions on 2026-10-14 (§ Decisions; § Decision Log).

## Goal

`hooks/git_gate.py` decides from a Bash command's text whether the command could write to `main`, `master` or `develop`, and asks whenever it cannot vouch for it. Vouching takes three open-ended bodies of knowledge:
- shell syntax: here-documents, quoting, nested shells, variables;
- git's commands: git 2.56 has 181 (`git --list-cmds=main`), and the gate classifies about 60;
- the options of each command that can move a branch (`branch`, `fetch`, `switch`, `worktree`, …).

Each gap is a false ask that costs the user an approval. Each fix is a PR with a long Codex review. The user asked on 2026-10-14 whether these fixes will keep coming. They will, so this plan proposes ending most of them structurally.

Git's own `reference-transaction` hook (`git-hooks/reference-transaction`) already sees every branch update made through git, however the command is written. Today it refuses every update of a protected branch except a merge. If it refused merges too, unless the command carries an explicit marker, git itself would decide which commands move a protected branch. `git_gate.py` would no longer need to know git's commands or their options.

It would still read the command text, for a narrower question: does the command carry the marker, or anything that stops git from running the hook? Codex's first review showed that second list is longer than first written. It is § Proposed design, item 2.

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
- **The docstring says listing dangerous shapes cannot be completed.** `git_gate.py` records that finding from review. It stays true for the shapes of commands that move a branch. This plan moves that question to the hook, which allows a protected branch to move in one shape only, whatever command or program moved it. The list that stays in `git_gate.py` is of a different kind: the ways to stop git from running the hook. That list is short, measured, and can be tested item by item.

## Proposed design

1. **`git-hooks/reference-transaction`:**
   - In a Claude Code session (`CLAUDECODE=1`; § Decisions, 1), an update of `main`, `master` or `develop` needs the environment variable `PROTECT_BRANCHES_ALLOW` naming that branch. Without it, the update is refused, whatever its shape. A terminal outside Claude Code keeps today's rules. The user's `!` commands run inside Claude Code, carry `CLAUDECODE=1`, and so need the marker too.
   - **The marker is required in every repository.** The owner check decides only whether today's merge-only rules apply on top, which they do in the user's own repositories.

     The owner check cannot decide whether the marker is needed, because a command can steer it. Codex's second review showed this: `-c url.https://github.com/foreign/.insteadOf=https://github.com/Taka499/` made a `Taka499` repository look foreign, and the hook let `update-ref` move `master`.
   - Creating the branch stays allowed: a first commit, `git branch develop <start>`.
2. **`hooks/git_gate.py` asks for:**
   - **the marker,** anywhere in the command text;
   - **anything that stops git from running the hook.** Measured on git 2.56 in scratch repositories (§ Decision Log):
     - **Settings:** `core.hooksPath`, `hook.*`, `include.*`, `includeIf.*` and `alias.*`. An alias can carry `-c hook.<name>.enabled=false`. Each counts however it is given:
       - `-c` or `--config-env`;
       - `GIT_CONFIG_PARAMETERS`;
       - `GIT_CONFIG_COUNT` with `GIT_CONFIG_KEY_<n>` and `GIT_CONFIG_VALUE_<n>`;
       - written with `git config`.
     - **Another config file:**
       - `GIT_CONFIG_GLOBAL` with any value;
       - `GIT_CONFIG_SYSTEM` with any value but `/dev/null`;
       - `HOME` changed or cleared: `HOME=…`, `env -u HOME`, or the whole environment cleared (`env -i`, BSD `env -`, `env --ignore-environment`, `exec -c`).
     - **A git that ignores hooks defined in config:**
       - a program named `git`, or `git-<name>`, run by any path other than Homebrew's `/opt/homebrew/bin/git`. That covers Apple's `/usr/bin/git`, the copies in Xcode and in the Command Line Tools, and their `git-core` directories;
       - a `PATH` set or exported anywhere in the command;
       - `command -p`, `xcrun`, `--exec-path`, `GIT_EXEC_PATH`.
     - **A subcommand that is not one of git's own commands** (`git --list-cmds=main`), because it is an alias or an external `git-<name>`:
       - this catches an alias defined before the command, which no word in the command reveals;
       - git ignores an alias that shares the name of one of its own commands (git-config(1), `alias.*`), so the names on the list need no further check, once a test confirms that.
     - **A git setting, environment value or program path that is not literal,** such as `git -c "$x"` or `$G`, because it can spell any of the above. The same goes for anything that sets the environment from non-literal text: `export`, `env`, `declare` or `unset` with a non-literal word, or `eval`.
     - **`CLAUDECODE` changed in any way,** because the marker binds only Claude Code sessions (§ Decisions, 1): an assignment, an export, an `unset`, or the environment cleared as above.
   - **`push` and `gh pr merge`,** as today.

   **Everything else is silent.** The tables of what each subcommand does and the option rules go, and with them the false asks for:
   - unclassified subcommands (`merge-tree`, `hash-object`), now silent as two of git's own commands;
   - command options (`branch --list`, `fetch`).

   **Some reading of the text stays.** Shell-syntax asks remain only where git's settings, environment or path cannot be read. Elsewhere, a scan of the whole text for the words above is enough, because those words are rare in ordinary commands.

   **The allowlist of settings that name no program also goes.** A setting can make git run a program: a pager, a merge driver, a credential helper. Either way, no new gap opens:
   - **Code written inline in such a setting is command text,** and the scan reads it like any other text. To move a protected branch it has to use the marker or a bypass from the list above, which ask, or write ref files itself, an accepted gap below.
   - **A setting that names a file** is a script file, the accepted gap below.

   **Not bypasses, measured on git 2.56:**
   - `XDG_CONFIG_HOME` changed alone: `~/.gitconfig` is still read;
   - the reftable ref backend: it runs the hook;
   - `GIT_DIR` or `--git-dir`: they select a repository, and the global hook runs there too;
   - `safe.directory`: it can stop an operation, not the hook.
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
1. **gkms-contest-ai:** `integrate.sh` sets the marker. Today's hook ignores the marker, so this step is harmless alone.
2. **PR A:** the hook, `git_gate.py`'s new asks (the marker and every bypass in design item 2) with today's parser kept, and the documents. Then the user runs `install-global.sh`.
3. **PR B:** strips `git_gate.py`'s subcommand and option rules, only after `install-global.sh --check` passes with the new hook. The check must cover both a repository of the user's and a third-party one, since design item 1 requires the marker in every repository.

## Decisions (the user, 2026-10-14)

These were the plan's five open questions. The user accepted the recommendation on each, after an explainer page set them out.

1. **Whom the marker binds: Claude Code sessions only.** Required everywhere, it would also refuse the user's own `git merge` or `git pull` on a protected branch typed in a terminal. Claude Code sets `CLAUDECODE=1` in its Bash commands (seen 2026-10-14), so the hook requires the marker only there, and a terminal outside Claude Code keeps today's rules.
   - So `git_gate.py` asks on any change to `CLAUDECODE`, not only its removal: `CLAUDECODE=0`, `env CLAUDECODE=x`, `export CLAUDECODE=`, `unset`, `env -i`, `env -`.
   - Measured on 2026-10-14: the user's `!` commands carry `CLAUDECODE=1` (`! echo "CLAUDECODE=$CLAUDECODE"` printed `1`). So an update of a protected branch typed as a `!` command needs the marker too. Only a terminal outside Claude Code keeps today's rules.
2. **The marker's form: an environment variable naming the branch.** It shows what is approved in the prompt itself, `PROTECT_BRANCHES_ALLOW=develop git merge --no-ff feature/x`, and it lives only for that command. A `-c` setting was the alternative. A setting can also be written into a config file, where it would approve every later update silently.
3. **Repositories outside the owner check get the marker, not the merge-only rules.** These are third-party clones such as mulmoterminal.
   - Design item 1 requires the marker there, since a command can steer the owner check.
   - The first draft offered `git_gate.py` asking on any git write in a repository with no remote under `Taka499` or `tia-tools` instead. That relied on reading the remotes, so it was dropped.
   - Without the merge-only rules, an approved `git pull` keeps following upstream's direct commits.
4. **Apple's git: `git_gate.py` asks on the routes in design item 2, and nothing more for now.** A route it does not know, such as one inside a script, reaches a git that runs no hook defined in config.
   - Plan 0020 kept a per-repository copy of the hook (`git-hooks/protect-branches.sh`) as a fallback, and Apple's git runs that copy too.
   - Its cost is a one-time sweep of the user's repositories and a step for each new one. It is paid only if Apple's git turns up in use.
5. **Push stays as it is:** `git_gate.py`'s push ask and the `Bash(git push *)` rule. Pushes also run outside the sandbox, which prompts anyway. Moving push into a `pre-push` hook is out of scope.

## Accepted gaps

- **Programs that change refs without git's hooks:** a process that writes ref files itself, or a tool built on a git library (libgit2) instead of the git program.
- **A script or program file, or a file sourced into the shell (`source`, `.`).** It can do anything git can, including switching the hook off (`GIT_CONFIG_GLOBAL`, an alias, Apple's git) or setting the marker. `git_gate.py` does not read files, now or after this plan, so the gap is the same as today. One thing changes: a script that merges into `develop` without meaning to is refused, not let through.

## Verification (when built)

- **Hook tests (`git-hooks`), with Homebrew git 2.56.** Without the marker, each of these is refused on a protected branch:
  - commit, merge, `merge --ff-only`, pull;
  - `update-ref`, `branch -f`, `checkout -B`;
  - `fetch` into `refs/heads/…`;
  - cherry-pick, reset.

  With the marker, a merge passes and a non-merge is still refused. Other branches are untouched, and creating a branch is allowed. Without `CLAUDECODE=1` (a terminal outside Claude Code, § Decisions, 1), today's rules apply unchanged: a merge passes with no marker. Each rule is broken deliberately and shown to fail tests.
- **Bypass tests.** Each bypass in design item 2, in each of its spellings, is shown to move a protected branch in a scratch repository. That keeps the list as evidence, not belief. Each measured non-bypass is shown to leave the hook running.
- **The alias rule.** In a scratch repository, an alias named like one of git's own commands is shown to be ignored.
- **`git_gate.py` tests:**
  - a replay set of every false ask recorded so far (the loop worker's twelve, engine-deviations' `hash-object`) is silent;
  - the marker and each bypass, in each spelling, ask;
  - an alias already defined, run by its bare name, asks;
  - a git or `git-<name>` program run by a path other than Homebrew's asks;
  - a non-literal setting, environment value or program path asks.
- **`/codex-review`** of each PR, in a snapshot clone.

## Decision Log

- **2026-10-14, the user: plan the redesign first.** No more one-off fixes to `git_gate.py`'s text parser meanwhile; occasional false asks are approved by hand. The `hash-object` / `update-index` false ask from engine-deviations is left unfixed.
- **2026-10-14, Codex's first review of this plan.** It ran in a snapshot clone; the real repository's refs were unchanged. Verdict: "CODEX VERDICT: CHANGES REQUESTED". Codex tested each bypass in a scratch repository with git 2.56. Eight findings, all accepted and now in the design:
  - **(high) `GIT_CONFIG_SYSTEM`** pointing at a file with `hook.<name>.enabled=false` let `update-ref` move `master`.
  - **(high) An alias** carrying `-c hook.<name>.enabled=false` moved `master` when run as `git bypass`. Today's gate asks on unknown subcommands, which covers this; a stripped gate must ask on `alias.*` in any spelling.
  - **(high) Apple's git can be reached without its path:**
    - `export PATH=/usr/bin` earlier in the command;
    - `command -p git`, which resolves to `/usr/bin/git` (2.50.1) on this machine.

    Today's gate still reads the branch in those commands; a stripped gate would not.
  - **(high) `CLAUDECODE`** can be changed, not only unset.
  - **(high) The script gap was understated.** A script can switch the hook off, not only set the marker.
  - **(medium) Repository scope.** Without the owner check settled, PR B leaves third-party clones unguarded. It is now a prerequisite of PR B.
  - **(medium) Other ways to give settings:** `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`/`KEY`/`VALUE` and `--config-env` each disabled the hook.
  - **(low) Non-bypasses.** Those Codex measured are now recorded as such.

  **Added by the agent:**
  - `integrate.sh` sets the marker before the hook changes, so no step leaves the coordinator unable to merge;
  - the first draft's claim that a plain text scan would be enough is withdrawn, because `git_gate.py` keeps reading git's settings, environment and path.
- **2026-10-14, Codex's second review of this plan.** It ran in a snapshot clone; the real repository's refs were unchanged. Verdict: "CODEX VERDICT: CHANGES REQUESTED". Round 1's fixes and the rollout order were confirmed. Four findings, all accepted:
  - **(high) Apple's git by full path.** Xcode's copy, `/Applications/Xcode.app/Contents/Developer/usr/bin/git` (2.50.1), moved `master`; Homebrew's git refused the same update. Design item 2 now asks on any git or `git-<name>` program run by a path other than Homebrew's.
  - **(high) An alias defined earlier** moved `master` when run as `git bypass`, a command with none of the listed words. Design item 2 now asks on any subcommand that is not one of git's own commands.
  - **(high) `-c url.<base>.insteadOf`** made the owner check read a `Taka499` repository as foreign, and the hook let `master` move. The marker is now required in every repository, and the owner check decides only the merge-only rules. That also settles the first half of open question 3: the owner check can no longer be relied on.
  - **(medium) Settings that make git run a program** were dropped without saying how code written inline in one is covered. Design item 2 now says it: inline code is command text the scan reads; a setting that names a file is the script gap.

  **Added by the agent:**
  - environment set from non-literal text (`export`, `env`, `declare`, `unset`, `eval`) asks, because it could set the marker or change `CLAUDECODE` with no visible word;
  - `git-<name>` programs from Apple's `git-core` are included with the git paths;
  - a sourced file joins the script gap.
- **2026-10-14, Codex's third review of this plan.** It ran in a snapshot clone; the real repository's refs were unchanged. Verdict: "CODEX VERDICT: CHANGES REQUESTED". All round-1 and round-2 findings were confirmed answered, and the rollout order closes both windows. Two findings, both accepted:
  - **(high) BSD `env -`** clears the whole environment, `CLAUDECODE` included. Under `env - /opt/homebrew/bin/git`, `update-ref` moved `master`; the same update without it was refused. Design item 2 now names the class: any clearing of the environment (`env -i`, `env -`, `env --ignore-environment`, `exec -c`).
  - **(low) The status line** still said one review.

  No fourth round. The fix adds members to a class item 2 already had (`env -i`), and changes no rule.
- **2026-10-14, the user: the five open questions settled as recommended.** This came after an explainer page on them: "I agree with the recommendation of five questions."
  - § Decisions records each answer. Design item 1 and item 2's `CLAUDECODE` ask now state decision 1.
  - PR #33 had merged the first draft (`a06ff80`). This revision and the decisions follow in a second PR.
  - Still to measure before PR A: whether `!` commands carry `CLAUDECODE`.
- **2026-10-14, the user: `!` commands carry `CLAUDECODE=1`.** The user ran `! echo "CLAUDECODE=$CLAUDECODE"` in a Claude Code cell, and it printed `1`.
  - Under decision 1, a protected-branch update typed as a `!` command therefore needs the marker; only a terminal outside Claude Code keeps today's rules.
  - The user had accepted decision 1 with this outcome stated in advance, so the decision stands. Design item 1 and decision 1 now say so.
