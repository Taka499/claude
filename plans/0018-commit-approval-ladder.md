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
- **`hooks/git_gate.py` (new) and `hooks/test_git_gate.py`:** a PreToolUse hook built on an allowlist of silent forms:
  - read-only and index-only subcommands;
  - listing or plainly creating a branch;
  - `switch` to a literal, unprotected name, remembered for the rest of the command;
  - `fetch` with no refspec (since 2026-10-13, also with refspecs that store only into `refs/remotes/…` or `refs/tags/…`; see the after-merge note on fetch below);
  - a current-branch write (`commit`, `merge`, `pull`, `cherry-pick`, `revert`, `am`) on a branch it can name as unprotected.

  Everything else asks, as README § The one file this repo does not deploy lists. The rule is a pure function, `decide(command, branch_of)`, with git reached only through the injected `branch_of`.
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
    - `Codex review: codex exec --sandbox danger-full-access with approvals off, run by the /codex-review skill to review the local diff, is allowed. It runs as an ordinary sandboxed Bash command, so Claude Code's OS sandbox confines it (writes only to the working directory, $TMPDIR, ~/Developer/claude and ~/.codex; network only to the allowlist; credential paths denied). Its prompt forbids changes but nothing enforces that, so the skill checks the repository's status and reflog afterwards. The user accepted sending the diff and the files Codex reads to OpenAI`

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

**Codex wrote to the repository during review round 2.** Despite "Do NOT modify anything" in its prompt, it made an empty commit, `0f0b81f` "init" authored `x <x>`, on the feature branch at 10:49:17. Nothing else changed: no other ref, no stash, no configuration. It also left `hooks/__pycache__/` from running the tests. Codex runs inside Claude Code's sandbox, which allows writes to this repository, so the prompt instruction is the only thing keeping a review read-only. No hook sees it either: Codex's git commands never pass through Claude Code. The branch was rebuilt without the commit, as `feat/commit-approval-ladder-2`, from `79adc43` with the two later commits cherry-picked; its tree is identical, and the old branch is kept for the user to delete. Round 3 ran against a snapshot clone under `$TMPDIR`, and the repository's reflog was checked afterwards.

**Interpreters.**
- `/usr/bin/python3` is 3.9.6 (Command Line Tools 27.0) and is not upgradable on its own.
- `/opt/homebrew/bin/python3` is 3.14.3 and comes first on the session `PATH`.
- Python exits 2 on a missing script file. Measured: the unguarded command exits 2; the guarded one exits 1 with its message.

## Decision Log (session 2026-10-12)

- **Standing permission comes per task, not per commit.** This is the reference practice, and it keeps a human decision where one exists: what to build, and whether to integrate it. A commit on an unshared feature branch can be undone until it merges.
- **Merges stay human in Phase 1.** Phase 2, automatic merging when every check passes and nothing waits on the user, is decided after a week of data: approvals per day, commits per day, time from DONE to merge, and reverts or fixes of merged work.
- **A hook, not an `ask` rule.** Only a hook can see the branch. It asks when it cannot tell, so an unparseable command or an unknown directory prompts rather than passing.
- **Conservative after review: ask about anything not fully modelled.** The first version listed five history-writing subcommands and parsed only direct `git` runs. The Codex review (round 1, CHANGES REQUESTED) and the background security review of the hook commit found protected-branch writes that passed with no ask. A probe of `decide()` reproduced all of them before any fix:
  - a branch switch earlier in the same command (`git switch develop && git commit`);
  - git inside another program: `bash -c`, `sh -c`, `eval`, `env`, `command`, `exec`, `time`, `xargs`, backticks, interpreter heredocs;
  - inline aliases (`git -c alias.ci=commit ci`);
  - `git pull`;
  - direct ref moves (`branch -f develop`, `update-ref refs/heads/develop`, `switch -C develop`, `fetch x:develop`);
  - environment redirects (`GIT_DIR=… git commit`, `export GIT_DIR=…`).

  A text gate can never enumerate every shape, so the rule was inverted: silence must be earned by a run the hook fully understands. The cost is accepted false positives, each one prompt:
  - `time git commit` on a feature branch;
  - `git branch new develop` (names `develop`);
  - `git worktree add -b feature/x ../wt develop`, which runs unsandboxed and prompts anyway;
  - a commit after `git switch feat/other` in the same command;
  - interpreter heredocs or `gh pr create` bodies whose text contains a branch-writing git command.
- **Then an allowlist: list the safe forms, not the dangerous ones.** Round 2 of the Codex review (CHANGES REQUESTED) confirmed every round-1 finding resolved, and found new gaps in the conservative version:
  - a branch target given as a variable (`git branch -f "$TARGET"`, `git update-ref "$REF"`, `update-ref --stdin`);
  - a short option attached to its value (`switch -Cdevelop`, `branch -fmain`);
  - an alias that moves another branch;
  - `filter-branch -- --all`;
  - fetch refspecs configured to write local branches;
  - non-string hook input.

  The security review of the first fix added git run through a variable (`G=git; $G commit`). Each was a shape the deny-list did not name. Isamu's own `pr-contract` documentation describes the pattern: by the third round, most findings are defects in fixes written during the review. So the rule was inverted again. Silence now needs one of a handful of forms whose effect is fully known, and every other subcommand asks, aliases included. This also removed the round-1 false positive on `git branch NEW develop`. The security review of the allowlist commit then found three silent forms with branch-moving options, now closed:
  - `git stash branch NAME`, which creates a branch and switches to it;
  - `git symbolic-ref -d`, and a second name setting `HEAD`;
  - `git pull` with a refspec, which writes a local branch other than the current one.
- **Round 3, on a snapshot clone, and the security reviews of the fixes.** Codex confirmed every round-2 finding resolved and found no false positive on ordinary feature-branch work. It found three more gaps, all closed:
  - an alias or `--stdin` run through a variable (`$G -c alias.x=push x origin HEAD:main`), which also slips past the textual `git push *` rule;
  - `git fetch --stdin`, whose refspecs never appear in the command;
  - `git clone`, filed as index-only although `--upload-pack` runs a program and `-c`/`--template` install hooks into the new repository.

  The security review of the escape fixes found two more bypass classes, also closed:
  - directory changes other than `cd` (`pushd`, `builtin cd`, `command cd`, `popd`);
  - git printed by `echo` into something that runs it (`| bash`, `<(…)`, `printf … > s.sh; sh s.sh`). The print-only exemption now holds only when nothing in the command can execute text.

  These were closed with a short list of options with hidden effects, which ask on any run, rather than by moving whole subcommands out of the allowlist. `--template` and `--config` count only for `clone` and `init`, because `commit --template` is a harmless message template; a breakage test guards that false positive.
- **Inside other programs' text, only branch-writing subcommands count.** There, an unknown word after `git` is not treated as a write, so prose such as "the git repo" stays silent; a direct git run is stricter, where an unknown subcommand counts. Programs that only print or read their arguments (`echo`, `printf`, `grep`, `cat`, …) are scanned only when a `$(…)` or backtick, which the shell does run, appears. Config-defined aliases inside other programs (`bash -c "git ci"`) are the residual this leaves; there are none defined on this machine, and a sandboxed session cannot define one (`.git/config` is protected, `~/.gitconfig` is outside the write allowlist).
- **Fail-open where it cannot be helped, and said so.** Unreadable input, including a `command` that is not a string, now asks. Configured fetch refspecs are not read: a sandboxed session cannot change `.git/config`, so only the user could have set one up. A missing interpreter, or a script that cannot import, still counts as no decision in Claude Code. That, and git run from a program file, is why a git-level guard is the next change.
- **The interpreter is named by absolute path, and the entry is guarded.** A crashed hook fails open, and an unguarded missing file blocks every Bash call. The code needs 3.10, and the user chose to require a modern Python rather than write for Apple's 3.9.
- **Python, not TypeScript, for the hook.** The parse needs a shell lexer, which Python has in `shlex`; a TypeScript version would need a package such as `shell-quote`, plus `tsc` for its types to be checked at all. This repo has no `package.json` or toolchain. Node here lives under `nvm`, at versioned paths a hook cannot rely on. Revisit if the harness grows enough scripts to justify a TypeScript toolchain with strict lint.
- **Push is unchanged.** It is not the bottleneck, and the keychain deny makes it run outside the sandbox anyway.
- **The rule is replaced in place.** It is a correction of the per-commit rule, made with the user's agreement (§ Continuous Learning). A project that restates the old rule, such as a coordinator's command file asking before every commit, should drop that restatement. Nothing else migrates.
- **`/codex-review`'s "read-only" is a request, not a guarantee.** Recorded here, and fixed separately in the skill: review a snapshot, and check `git status` and the reflog after every run. Shipping this plan does not wait on that fix.
- **`__pycache__/` is ignored.** `hooks/` brings Python into the repository, and running its tests leaves bytecode. The directory the review left behind is not deleted, per the user's rule on untracked files; ignored, it stops showing.
- **After merge (2026-10-13): git text is judged per program, not per command.** In the coordination worker of gkms-contest-ai, a `python3 - <<'EOF'` script rewriting its ExecPlan made the hook ask on 2026-10-12. The script's replacement strings were git commands written as prose, and the hook scanned the heredoc of any command containing a non-git program. That cost the user an approval for a markdown edit, the very kind of prompt this plan removes.
  - **The rule now:**
    - **Any program is looked through** to the first `git` or shell it starts, with no list of launchers (`env`, `time`, `xargs`, `find -exec`, `busybox`, `arch`, `setsid`, `cat <(…)`, …). Git found that way is judged as the git run it is: `env git commit` is silent on a feature branch and asks on `develop`. A `git` right after an option may be that option's value (`find -name git`, `sudo -u git`), so there it counts only when a known git subcommand follows.
    - **`echo` and `printf`, as the run's own program, print text:** `echo git commit` does not ask. A process substitution among their words still runs (`echo <(git commit)`) and is judged. Behind a launcher a printer is not exempt, because there `echo` may be an argument (`find echo -exec git commit`); `env echo git commit` therefore asks, which errs safe.
    - **A shell's own arguments, its own heredoc and everything piped into it,** however many stages back, are scanned for git.
    - **Every other program** has only `$(…)` and backticks scanned, which the shell itself runs.
    - **`-c` values and `GIT_*` variables** given for a git command are scanned for git they would run (`core.pager`, `GIT_PAGER`).
    - **Heredocs are read by the rules zsh and bash share.** Claude Code runs commands in the user's login shell, zsh here. Text taken for a body is never read as commands, and a quote left in a misread body can hide the commands after it, so the reading has to match the shell's:
      - a `<<WORD` counts only outside quotes (`'…'`, `"…"`, a fresh level inside each `$(…)`, which a `case` pattern's `)` does not close), outside comments and outside arithmetic, where `$((1 <<EOF))` is a shift;
      - every `<<WORD` on a line takes a body, in order, from the lines after it;
      - with an unquoted delimiter (`<<EOF`), the shell runs the body's `$(…)` and backticks as it reads it, so such a body holding git-write text asks, whatever program reads it;
      - each body ends at the first line exactly equal to its delimiter, with leading tabs removed for `<<-`. With an unquoted delimiter, a line ending in `\` runs on into the next, so `x\` followed by `EOF` ends nothing (checked with bash 3.2).

      The first version, a regular expression, misread all of these. It took a `<<EOF` in quotes, a comment or arithmetic for a heredoc. It read only the first of two heredocs on a line, and it ended a body at an indented `EOF`.
    - **A `#` hides only its own comment.** Comments are removed where bash sees them, at a word start, and Python's `shlex` no longer reads `#` at all. On master it did. With the command's newlines already joined, `shlex` took everything after a `#` as one comment, and it also started a comment mid-word, so `curl …/y#frag && git push origin develop` and a `git commit` on the line after a comment passed with no ask. The global git hook still refused a non-merge update of a protected branch, but a push or a merge passed with no ask.
  - **Accepted gaps, named in the README:**
    - code an interpreter runs (`python3 -c`, `node`, `awk`'s `system()`);
    - a script file a shell runs (`printf … > s.sh; sh s.sh`), which this change stops scanning;
    - git spelled out only at run time (`printf 'git com%s' mit | sh`, `g\it`, `$(printf %s git)`, `{git,commit}`), which master missed too;
    - shell names behind symlinks, and interactive escapes (`less` `!`);
    - an alias right after a launcher's option (`xargs -0 git co`).

    The global reference-transaction hook (plan 0020) refuses any non-merge update of a protected branch in all of these. `$'…'` quoting is not a gap either: a command using it outside quotes, in a heredoc's word too, takes the coarse whole-text scan, which asks whenever git-write text appears anywhere in it. The hook does not model its escapes, which shift where quotes close.
  - **Review history.** Codex reviewed the branch after each round of fixes, and the security-guidance plugin reviewed each commit.
    - **Round 1** rejected a first narrowing, which scanned text only when the command contained a listed shell-like program. It was command-wide, so `env python3 - <<EOF …` still asked, as did a Python edit followed by `time true`, and its fixed list missed `busybox sh -c`, `find … -exec` and `git -c core.pager=…`.
    - **Round 2** found that multi-stage pipes into a shell were missed, that unlisted launchers (`arch`, `setsid`) were not looked through, and that `find -name git` was taken for a git run.
    - **Round 3** found `printf 'git com%s' mit | sh` (accepted, above) and a false ask for `echo git commit` (fixed by the printer rule).
    - **The plugin's review of round 3** found that the printer rule had silenced `echo <(git commit)`. Fixed: a printer is looked through from its first `<(` or `>(`.
    - **Round 4** found a false ask for `env echo git commit`. A launched-printer rule fixed it.
    - **The plugin's review of round 4** found that the launched-printer rule hid `find echo -exec git commit`. It also found that a `<<EOF` in quotes or a comment hid the following lines; master had asked there, because it scanned every body. The launched-printer rule was removed, so round 4's false ask stays, and heredocs became quote- and comment-aware. Checking that fix found the `#` bug, which dates from before this branch.
    - **Round 5** found the launched-printer rule incomplete (`env -i echo …`), which was moot once the rule was removed.
    - **Round 6** found two shapes in which the regex heredoc reading hid a `git push` that the shell runs: a `<<EOF` inside `$((…))`, and a second heredoc on one line. The plugin's review of the same commit reported parser differentials too. The reading was rewritten to follow the shell's rules, above. Checking those rules against bash found three more misreads, all fixed: an indented delimiter line, `\`-newline joining, and a `)` of a subshell or `case` pattern closing a `$(…)`.
    - **Round 7** found that `cat <<$'EOF'` took `$EOF` for the delimiter and hid every later line, a `git push` included. The agent then built a line on which `$'\''` shifted the scanner's quote parity, so that a real `git push` was set aside as a heredoc body while `shlex` still tokenized the rest. The earlier removal of `$'…'` tracking had rested on the belief that `shlex` always fails there. Fixed: `$'…'` outside quotes makes the command unreadable, and the coarse scan applies. Its Low finding was answered, not fixed: `git fetch origin --filter blob:none` asks, because an option's value after the repository word reads as a refspec. The same options before the repository are silent, the ordering is rare, and the ask errs safe; modelling every value-taking option of `fetch` would add parsing for little gain.
    - **The plugin's review of round 7's fix** called it a parser downgrade, which was real. `$'…'` sent a command to the coarse scan, and that scan judged `git -C ../main merge` against the session's branch, and did not see `$G push`, `GIT_DIR=`, `pushd` or Apple's git. Adding a `$'…'` anywhere downgraded a command into those blind spots, as did nested quotes inside `$(…)`, which `shlex` cannot split. Fixed: the coarse scan asks whenever something could point a write elsewhere, and is otherwise judged like the full parse. Comparing the two paths afterwards, the agent found one more gap: the full parse asks on a `hooksPath` or `hook.*` setting, which can switch off the reference-transaction hook, but the coarse scan did not, so `git config core.hooksPath /dev/null` slipped through it. It now asks on hooks and include settings and on `git config`.
    - **Round 8** found that an unquoted heredoc's `$(…)` and backticks run as the shell reads the body, whatever program reads it then: `python3 - <<EOF` with `$(git push origin develop)` in it passed. Fixed: each body keeps whether its delimiter was quoted, and an unquoted body with a substitution and git-write text asks. Quoted bodies, the form used for Python edits and commit messages, stay unscanned.
    - **Round 9** confirmed round 8's fix and the coarse-scan hardening. It found one more High, also on master: zsh's `chdir`, and `builtin`/`command` in front of `pushd` or `popd`, were not taken for directory changes, so `chdir ../main && git merge topic` merged into `develop` silently, and the git hook allows merges. Fixed, and the agent added the moves whose target the command does not name: directory-stack entries (`cd -2`, `pushd +1`), `pushd` alone, and zsh's `cd old new`, which substitutes inside the current path. zsh's `AUTO_CD` is a named gap; it is off in this machine's startup files. While round 10 ran, the agent found two more moves of the same kind: `eval "cd ../main"` and an alias defined on one line and used on the next (`alias c='cd ../main'`). Both run text in the current shell, so the directory moves without a visible `cd`. Such a run whose text holds a directory change now leaves the directory unknown, and alias text is scanned like a shell's. Round 9's two Lows were fixed: the coarse scan asked on any `git -…` option, `--no-pager` included, and now asks only on those that pick the repository or settings; and the test counts in this plan were stale.
    - **Round 10** reviewed the tip before the `eval`/alias fix, so its same-command alias finding was already fixed. Its other findings:
      - **A reserved word hid a move (High, also on master).** `{ cd ../main; git merge topic; }` kept `{` attached to `cd`, so the move was missed, and `if`, `then`, `do` and the like hid a command the same way. Fixed: leading `{`, `!`, `if`, `then`, `else`, `elif`, `do`, `while` and `until` are stripped before a run is read, and a function header's `()` ends a run.
      - **`hash -d n=../main; cd ~n` (Medium).** Python would resolve `~n` as a user's home. Fixed: a `~name` target is unknown.
      - **A false ask for `deploy() { echo git push origin develop; }` (Low).** Fixed by the same stripping, for that body. Round 11 pointed out that a body with a real `git push` still asks; see there.
      - **Assigning zsh's `PWD` moves git (High), rejected.** In zsh 5.9 and bash, `PWD=../b && git symbolic-ref --short HEAD`, an exported `PWD`, and a `PWD=` prefix all still reported repo `a`'s branch, because git ignores a `PWD` that does not name the real current directory.
      - **A stale line in this plan (Low).** It said Codex ran five rounds; fixed.
    - **Round 11** confirmed round 10's fixes, and was asked to rank what remained by how plausibly an agent would write it.
      - **zsh's `noglob` and `nocorrect` (High, plausible).** In front of `cd`, they hid the move. Fixed: they are stripped like `builtin` and `command`.
      - **`CDPATH` (High, less plausible).** Set in the command, `CDPATH=..; cd protected` lands on `../protected`. Fixed: after a `CDPATH` or `cdpath` assignment, a `cd` to a bare name is unknown. An inherited `CDPATH` is a named gap; it is unset on this machine.
      - **zsh's `repeat 1 cd …` (contrived).** Fixed anyway: it was cheap.
      - **A function body with a real `git push` asks (Low), answered.** A definition is usually followed by a call, and the ask errs safe.
      - **The agent's own finding: operators written without spaces.** This was on master too, and checking round 11's `cdpath=(..)` case found it. shlex keeps a run of punctuation as one token, so in `true&&(cd ../main&&git merge topic)` or `(true);cd ../main && git merge topic`, `&&(` and `);` were plain words: the runs were mis-split, and the merge into `develop` passed. Fixed: punctuation-only tokens are split into the shell's operators, except that `<(` and `>(` stay whole, so a process substitution's text stays in the run it feeds.
    - **Round 12** confirmed round 11's fixes and found no plausible good-faith shape left that misses a push, a merge into `develop` or a protected write. Its one finding, a Low, was fixed: the operator splitting broke zsh's clobbering redirection `>|` into `>` and a pipe, so `echo … >| sh`, which writes a file named `sh`, asked. `>|`, `>&|` and `&>|` now stay whole.
    - **Two bugs of the agent's own were fixed along the way.** The heredoc pattern swallowed the rest of the `<<EOF` line, so `cat <<EOF | bash` lost its `| bash`. And `find .` matched the shell builtin `.`.
  - **A fetch into a remote-tracking ref asked (the user's report, 2026-10-13).** `/codex-review`'s snapshot step runs `git -C <snapshot> fetch -q <repository> "<base>:refs/remotes/origin/<base>"`, and the hook asked every round: `fetch` was silent only with no refspec at all. A fetch is now silent when each refspec after the repository word stores into `refs/remotes/…` or `refs/tags/…`, or has no destination; such a fetch writes no branch. Every word must still be literal, since a variable may expand to `x:develop`. The skill's step now fetches from `origin`, which a clone points at the repository it was cloned from, instead of naming the repository, which an agent tends to fill in with a variable.
  - **Stray objects during round 4, not an incident.** The post-review check found two unreachable commits in this clone's object store, written about a minute into the run: a `git stash create` pair ("WIP on …", "index on …") whose blobs matched the uncommitted working files. No ref moved. They came from the security-guidance plugin, which snapshots the working tree with `git stash create` and leaves `.git/sg-*` marker files. Codex ran in its snapshot clone, which has its own object store.
  - **Verification:** 70 test methods pass. Fifty deliberate breakages each failed tests:
    - no look-through;
    - a look-through that never accepts a `git` after an option;
    - one that always demands a known subcommand;
    - only the last pipeline stage fed to a shell;
    - no own heredoc;
    - the heredoc eating its line;
    - no `-c` scan;
    - builtins matching;
    - `gh pr merge` seen only first in a run;
    - `echo` and `printf` looked through;
    - a printer's process substitution ignored;
    - a launched printer exempt;
    - no quote tracking;
    - no `$(…)` level;
    - no comment removal;
    - `shlex` comments back;
    - no backslash escape;
    - no here-string guard;
    - no arithmetic skip;
    - only the first heredoc on a line given a body;
    - no `\`-newline joining;
    - joining under a quoted delimiter too;
    - a delimiter line compared loosely;
    - no `(` counting inside `$(…)`;
    - no `case` tracking;
    - `$'…'` read by the scanner;
    - `$'…'` read in a heredoc's word;
    - no check of unquoted bodies;
    - every body taken as quoted;
    - every body taken as unquoted;
    - no target check in the coarse scan;
    - no hooks-setting check in the coarse scan;
    - no `chdir`;
    - no `builtin`/`command` stripping;
    - directory-stack entries read as paths;
    - `cd old new` read as a path;
    - `pushd` alone read as home;
    - any `git -…` option asking in the coarse scan;
    - no directory change read from `eval`/`source`/alias text;
    - alias text not scanned;
    - no reserved-word stripping;
    - a function header kept in its body's run;
    - a `~name` target read as a path;
    - no operator splitting;
    - `<(` split too;
    - no `noglob`/`nocorrect`;
    - no `repeat`;
    - no `CDPATH` rule;
    - the `CDPATH` rule applied to `./` paths too;
    - `>|` split into a pipe.

    Some breakages at first passed every test. An alias behind a launcher (`env git sync`) and a wrapped `gh pr merge` had no test; both now do. Three parser branches survived and were removed as redundant: `$'…'` tracking (believed redundant because `shlex` fails on such commands; round 7 proved that wrong, see the review history), backtick levels (inside double quotes bash opens no new level for them), and a separate `<<<` check, twice (no delimiter word follows its `<<`). Several heredoc misreads were at first caught only by the coarse fallback, because the misread left an unbalanced quote; their tests now close the quote in a line the shell takes for a comment (`# '`), so each breakage shows.
- **After merge (2026-10-13): `git merge-tree` is read-only.** In gkms-contest-ai's Sense worker, a dry run of merging `develop` asked: `git merge-tree --write-tree --name-only HEAD develop`, the way to see a merge's conflicts without touching anything. `merge-tree` was not in the read-only list, so it asked as an unknown subcommand. Git's own merge-tree logic computes the merge in memory and at most writes tree objects; no ref, index or working tree changes. It is now read-only. Its `--stdin` batch mode still asks, through the hidden-effect option rule. A regression test uses the worker's command, and removing `merge-tree` from the list fails it.
  - **Codex review (CHANGES REQUESTED, High):** a custom merge driver selected by `.gitattributes` runs even under `merge-tree`, and `git -c merge.evil.driver=/path/prog merge-tree --write-tree …` ran a program that created a ref. This is not special to `merge-tree`. `diff` and `log` run configured diff commands and textconv, and `status` and `add` run filters, all already on the read-only list.
    - **Settings given in the command,** first fix: a list of program-naming settings asked, given with `-c` or `--config-env`. Codex's round 2 found one missing (`interactive.diffFilter`, run by `git add -p`), and the plugin's review called the list incomplete by nature. It also found a sibling path: `git config merge.x.driver /tmp/prog` passed silently, as on master, because `config` is index-only, and a later `merge-tree` then runs the driver. `git config --edit` passed too, and so did a program-naming environment variable such as `GIT_EDITOR=/tmp/prog`.
    - **Second fix: an allowlist, the hook's own principle** ("listing dangerous shapes cannot be completed; listing safe ones can").
      - A setting given with `-c` or `--config-env`, or written by `git config`, passes only if its key is known to name no program.
      - A pager or editor setting passes only with a no-op value (`cat`, `less`, `true`, `:`), so `-c core.pager=cat` and `-c core.editor=true` stay silent.
      - Program-naming environment variables follow the same rule, so `GIT_EDITOR=true git commit` stays silent.
      - `git config` reads, `--list` and `--unset` pass; `--edit` and `--rename-section` ask.
      - The coarse scan asks on those environment variables too.
    - **The plugin's review of the allowlist** found `protocol.*.allow`: `protocol.ext.allow=always` enables the `ext::` transport, which runs a command. It was removed.
    - **Codex round 3** found three more things, all fixed:
      - The wildcard `gc.*` admitted `gc.recentObjectsHook`, a command. Every family is now named key by key, except the display-only ones (`color`, `advice`, `i18n`, `column`, `pretty`).
      - `log.showSignature`, `commit.gpgSign` and `tag.gpgSign` run the signing program, so they now pass only when set to false.
      - `export GIT_EDITOR=/tmp/prog; git commit` passed, because only prefix assignments were checked. An exported (`export`, `typeset`, `declare`) or bare assignment of a program variable earlier in the command now makes every later git run ask, the way `GIT_DIR` already did.

      Its Low was answered: `P=cat git --config-env=core.pager=P log` asks, because the value lives in the environment. The form is rare and the ask errs safe.
    - **Programs configured in the repository** are the program-file case. The README now names them, and the global reference-transaction hook still refuses non-merge writes to protected branches. Deliberate breakages of the allowlist each failed tests:
      - every setting harmless;
      - a pager taking any value;
      - no pager exception;
      - no environment check;
      - `git config` always harmless;
      - `--edit` allowed;
      - `git config` reads asking;
      - the `set` word read as a key;
      - option values read as keys;
      - no environment check in the coarse scan.

      The last two had passed every test at first; tests now cover them. After round 3, seven more breakages each failed tests:
      - `gc.*` as a wildcard again;
      - signing with any value;
      - no signing exception;
      - no tracking of exported program variables;
      - only `export` read;
      - no bare assignment read;
      - `protocol.*.allow` back.
- **No ADR.** The rule is text and settings, easy to reverse, so it fails the first gate.

## Verification

- `python3 -m unittest discover -s hooks`: 50 test methods passed under Python 3.14.3 at merge (70 after the 2026-10-13 change below). Each review shape is a subtest:
  - 24 from round 1 in `BypassRegressions.SHAPES`;
  - 13 from round 2 and the security review;
  - 3 for creating a protected branch.

  End-to-end runs of the script cover a real throwaway repository on `develop` and on a feature branch, and three kinds of unreadable input.
- Deliberate breakages, each run on a scratch copy, failed tests in every round:
  - first version: 5 breakages;
  - the conservative version: 10;
  - the allowlist version: 22, among them the round-3 and security-review closures (hidden-effect options, the per-subcommand list, variable runs, `pushd`/`popd`/`builtin cd`, the print-only exemption) and the three escapes above, the final ask made silent (17 failures), switch targets unchecked, switches not remembered, any `branch` or `fetch` form allowed, the variable-program check removed, non-string input accepted, and the protected-name check on plain branch creation dropped.

  Two of these first passed every test, each exposing a hole the suite then closed:
  - **branch-switch tracking:** every switch test named `develop`, so the protected-name check caught them first; tests for `git switch -`, `"$TARGET"` and `@{-1}` closed it.
  - **plain branch creation:** no test created a protected branch; tests that `git branch develop feat/x` and `git switch -c main` ask closed it.
- The guarded hook command was run against a present and a missing script file.
- After the user applies the settings, check in a live session:
  - a commit on a feature branch runs with no prompt;
  - a commit on `develop` prompts with the hook's reason.
