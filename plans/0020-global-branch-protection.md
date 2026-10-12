# Plan: Define the branch-protection hook once in ~/.gitconfig instead of installing it per repository

## Goal

Plan 0019 installs git's `reference-transaction` hook into each repository with `protect-branches.sh`. Run that way, every repository needs a step, 27 of the user's existing ones a one-time sweep, and every update of the hook a re-sweep. The user asked for the easier way to cover all repositories. Git can now define hooks in configuration. One `hook.<name>` entry in `~/.gitconfig` then runs in every repository, alongside each repository's own `.git/hooks` rather than instead of them. This plan switches to that, scoped to the user's own repositories.

## Changes

- **`git-hooks/reference-transaction`:**
  - **Owner check.** It now acts only where `origin` is under `github.com/Taka499` or `tia-tools`, or absent. Defined globally it runs in every repository, and a clone of someone else's project, whose `main` takes direct commits upstream, must still pull.
  - **Lazy git-directory lookup.** It asks for the common git directory only once a branch is involved, because git runs the hook while `git init` and `git clone` create `HEAD`, before the repository is complete.
- **`git-hooks/install-global.sh` (new):**
  - copies the hook to `~/.config/git/protect-branches`;
  - sets `hook.protect-branches.event` and `hook.protect-branches.command` in global config;
  - proves the hook runs, with a direct commit on `develop` in a scratch repository that must be refused, and fails loudly when the git on `PATH` does not run config-defined hooks.
- **`git-hooks/protect-branches.sh`** stays, as the per-repository fallback for a git that ignores config-defined hooks.
- **`hooks/git_gate.py`** asks when a command carries a `hook.*` setting (`-c hook.protect-branches.enabled=false`, `git config hook.…`), and before a non-read-only command run with Apple's `/usr/bin/git`, which ignores config-defined hooks.
- **Global `CLAUDE.md` § Git Operations:** the protection bullet now names the global install, the git it needs, the owner scope and what passes it.
- **`README.md` § Layout** describes `git-hooks/` the same way.
- **`skills/scaffold-project/SKILL.md`:** step 3 checks for the global hook instead of installing a copy; the per-repository script is the fallback.

## Evidence (session 2026-10-12; Homebrew git 2.56.0, Apple git 2.50.1, macOS 26.7.1)

- **Config-defined hooks** (`git help` in 2.56; `git-scm.com/docs/git-hook`, "last updated in 2.55.0"): `hook.<name>.command` and `hook.<name>.event`. "The default <hook-name> from the hookdir is run last", so config hooks run in addition to `.git/hooks`. `hook.<name>.enabled = false` disables one per repository. Apple's 2.50.1 documents none of this.
- **A scratch test of the hook defined in config:**
  - **Homebrew git 2.56:** `init` succeeded, the first commit created `develop`, a direct commit on `develop` was refused, a feature-branch commit and a `--no-ff` merge passed, the repository's own `post-commit` still ran, and `clone` succeeded.
  - **Apple git 2.50:** everything ran the same except that the direct commit on `develop` went through, because 2.50 ignores config-defined hooks.
- **The first run of that test found the init bug.** The hook's opening `git rev-parse --git-common-dir` failed while `git init` was still creating `HEAD`, the hook exited 1, and git reported "update aborted by the reference-transaction hook". A per-repository copy arriving through `init.templateDir` would have hit the same failure.
- **Git LFS keeps its hooks in `.git/hooks`.** `ss-assist` and `task-companion` have LFS `pre-push`, `post-checkout`, `post-commit` and `post-merge` hooks there. A global `core.hooksPath` would have bypassed them, and `git lfs install` in a later repository would have tried to write into the global folder. Config-defined hooks leave both alone.
- **An incident while testing.** The first test script ran `T=$(mktemp -d); cd "$T"`. On macOS, `mktemp -d` without a template uses the per-user system temp directory, not `$TMPDIR`, and the sandbox refused it. So `$T` was empty, `cd ""` stayed in this clone, and the script ran here. It made four empty commits on a new local branch, `feat/global-protection`, and left an untracked `gitconfig` file and an `r/` directory in the clone's root. `master` was untouched, and nothing was pushed. The user was asked to remove these, per the rule against deleting untracked files. The script was fixed: `mktemp -d "$TMPDIR/cfg.XXXXXX" || exit 1`, then `cd "$T" || exit 1`.

## Decision Log (session 2026-10-12)

- **Config-defined hooks, chosen by the user as the easier way.** Two global settings and one copy cover every repository, existing and future, with no sweep and one place to update.
- **A global `core.hooksPath` was rejected.** It replaces each repository's `.git/hooks`, which silences Git LFS hooks unless a forwarding script stands in for every hook name. A repository that sets its own `core.hooksPath` (husky) would silently drop out.
- **A global `init.templateDir` was rejected.** Existing repositories would still need the one-time install, and every update of the hook a re-sweep.
- **The owner check reads `remote.origin.url`.** A sandboxed session cannot change it, because `.git/config` is protected.
- **Apple's git is the accepted gap.** A process that runs `/usr/bin/git`, or that runs with a `PATH` without Homebrew's, gets no protection. Sessions here put `/opt/homebrew/bin` first, and `git_gate.py` asks before an explicit `/usr/bin/git` that writes.
- **The per-repository copy already installed in this clone stays.** It runs as well as the global hook, which does no harm.
- **No ADR.** The change is a hook and a setup script, easy to reverse.

## Verification

- **`python3 -m unittest discover -s git-hooks`:** 40 tests pass with Homebrew git 2.56. The config-hook tests skip on a git that does not run config-defined hooks; none were skipped here. New:
  - **Owner check:** someone else's repository is left alone; the user's account and organization are protected.
  - **The global hook:** `init` and `clone` work, a direct commit is refused, and the repository's own hooks still run.
  - **`install-global.sh`:** it sets up the hook and proves it runs.
- **Deliberate breakages, each run on a scratch copy, all failed tests:**
  - protecting every repository;
  - protecting only repositories with no remote;
  - restoring the early git-directory lookup;
  - the installer not setting the command.
- **`python3 -m unittest discover -s hooks`:** passes. Removing the `hook.*` check and removing the Apple-git check each failed tests.
- **After merge:** run `git-hooks/install-global.sh` outside the sandbox. It reports `active` only after its own probe is refused.
