# Plan: Protect main, master and develop in git itself and on GitHub, and give every repository a remote

## Goal

Plan 0018 made commits on a feature branch free and kept history on `main`, `master` and `develop` behind the user's approval. Its `git_gate.py` hook reads command text. Three Codex review rounds and five security reviews kept finding command shapes that text cannot classify, and git run from a program file is invisible to it altogether. A guarantee has to sit where git itself changes a branch. This plan adds that guard in two places:
- **Locally:** git's `reference-transaction` hook, which sees every branch update made through git, whatever program runs it.
- **On GitHub:** a ruleset, where the plan allows one.

It also makes a GitHub remote mandatory for every repository, so the protected record exists off the machine, and teaches `scaffold-project` to ask where the remote lives and whether it is public.

## Changes

- **`git-hooks/reference-transaction` (new, POSIX `sh`).** In the `prepared` state it refuses any update of `refs/heads/{main,master,develop}` that is not a merge:
  - deletion;
  - a new tip that does not contain the old one (reset, rewind, amend, force);
  - a first-parent chain from old to new that contains a commit with fewer than two parents (a direct commit, a revert, a cherry-pick, a fast-forward over plain commits).

  It allows creating the branch. An all-zero old value is resolved with `git rev-parse` first, since git uses it for forced updates as well as creation.
- **`git-hooks/protect-branches.sh` (new).** Copies the hook into `git rev-parse --git-common-dir`/hooks, which covers every worktree. It refuses when `core.hooksPath` redirects git, and it refuses to overwrite a hook it did not install, recognised by a marker line. Re-running it updates its own copy.
- **`git-hooks/protect-github.sh` (new).** Creates or updates, by name, one ruleset named "protect main, master and develop" with only `deletion` and `non_fast_forward` rules, no bypass actors, and enforcement active.
- **`git-hooks/test_protection.py` (new).** Tests with real git in throwaway repositories, isolated from the machine's configuration, plus the GitHub script against a stub `gh`.
- **`hooks/git_gate.py`.** It now asks whenever a command carries `core.hooksPath`, which would switch the git hook off. Its docstring names the new backstop.
- **Global `CLAUDE.md` § Git Operations.** One new bullet:
  - every repository has a GitHub remote under `Taka499` or `tia-tools`, public or private as the user decides;
  - its protected branches change only by merges, enforced locally and on GitHub;
  - reverts go through a branch and a merge;
  - a push request goes with each merge request;
  - only the user bypasses the hook.
- **`skills/scaffold-project/SKILL.md`:**
  - a fourth confirmation: GitHub owner and visibility;
  - the hook is installed right after `git init`, before the first commit;
  - a new step 7 creates the repository, pushes `main` and, for a public repository, applies the ruleset, all on the user's go.
- **`README.md`.** § Layout gains `git-hooks/`; the `git_gate.py` bullet now names the backstop as in place.

## Evidence (session 2026-10-12; git 2.50.1, gh, macOS 26.7.1)

**GitHub plans.**
- Every private repository of the `Taka499` account answered `403 Upgrade to GitHub Pro or make this repository public to enable this feature` on the rulesets and branch-protection endpoints.
- `tia-tools` is an organization on the free plan, and the user is its admin. Its private `feedback` gave the same 403. Its public `gakumas-supportcards` and `releases` answered `[]`, as did `Taka499/claude`: rulesets are available there, and none is set.
- GitHub's billing documentation: "Upgrading your personal account does not affect any organizations you may manage or repositories owned by those organizations."
- The pricing page lists GitHub Team at $4 per user per month for organizations, and no individual Pro plan.
- A community thread of 2026-09-30 (`github.com/orgs/community/discussions/209198`) quotes the settings form on a private personal repository: rules "will not be enforced until the repository is moved to a GitHub Team organization account". The thread is unresolved.
- The user decided to stay on the free plans and to host gkms-contest-ai privately under `tia-tools`.

**Existing automation that the GitHub rules must not break.** `tia-tools/gakumas-supportcards`' `update-data.yml` merges its pull request with `gh pr merge --merge`, then pushes a merge of `main` into `develop` directly (`git push origin develop`). A pull-request requirement would break that; `deletion` and `non_fast_forward` do not, because the push is a fast-forward. `releases` has no workflows.

**git's hook interface** (`git help githooks`, § reference-transaction):
- the hook runs for every reference update, and "In the 'prepared' state, a non-zero exit status will cause the transaction to be aborted";
- the old value is "the all-zeroes object name" both for a new reference and when "force updating the reference regardless of its current value".

## Decision Log (session 2026-10-12)

- **The boundary is git's hook, not text.** `git_gate.py` stays as the early, explaining prompt for the common forms. The hook is what holds: it sees the update, not the command. A deliberate bypass needs `core.hooksPath`, which `git_gate.py` asks about, or a program file run by the user's approval.
- **A copy, not a link.** A sandboxed session cannot write `.git/hooks`, so a copy there cannot be altered by one. A symlink would point into this repository, which sandboxed sessions can write. The cost is that an updated hook needs `protect-branches.sh` re-run in each repository.
- **Merge-only, including fast-forwards over merges.** Pulling a branch that took pull-request merges on GitHub is a fast-forward over merge commits, and it must work. A fast-forward over plain commits is a direct commit by another route, so it is refused.
- **Reverts go through a branch.** A revert made on `develop` is a plain commit and is refused. Rolling back a merge is `git revert -m 1` on a branch, merged with `--no-ff`. That keeps the integration branch's first-parent history merges only, which is what lets `git revert -m 1` undo any one of them.
- **GitHub rules: `deletion` and `non_fast_forward` only, no pull-request requirement.** They make the remote record impossible to rewrite or delete, which is the guarantee. A pull-request requirement would break `gakumas-supportcards`' data workflow and the local-merge flow gkms uses. No bypass actors, so admins, the user and the agents using the user's token are bound too.
- **Private repositories get the local hook only.** On the free plans GitHub enforces nothing on them. What GitHub would add there is narrow: every push already asks, force pushes are denied in settings and blocked by the classifier, and deleting a remote branch is a push.
- **gkms-contest-ai is not changed by this PR.** Installing the hook there changes its coordinator's options. The answer the user is about to give to its loop plan's Q2 committed a new branch's STATUS § 3 row directly on `develop`, and the hook would refuse that commit. The row has to come in through a short branch merged with `--no-ff`. Creating the private `tia-tools` remote and installing the hook are the next step there, with the coordinator told first.
- **Ref names are compared case-insensitively.** The security review of this PR found it, and a probe confirmed it: on macOS's case-insensitive APFS, `git update-ref refs/heads/DEVELOP <feature>` moved `develop` straight past a case-sensitive match, because both names are the same file. The test for it runs only on a case-insensitive filesystem; on Linux, `DEVELOP` is a separate branch.
- **Which ref is protected is decided by the filesystem, not the name.** The security review of the case fix found `refs/heads/maſter` (long s), which APFS's Unicode case folding stores as `master`; a probe confirmed it moved `master`. Instead of chasing name normalization, the hook asks the filesystem. In the prepared state git holds a lock file for every ref in the transaction, and a ref counts as protected when its lock is the same file (`test -ef`) as a protected branch's lock. The lower-case name comparison stays for updates without a loose lock.
- **Codex review of PR B (round 1, CHANGES REQUESTED), all fixed:**
  - replacement objects (`git replace --graft`) could dress a plain commit as a merge; the hook now runs with `GIT_NO_REPLACE_OBJECTS=1`;
  - an empty `core.hooksPath` also makes git ignore the hooks directory; the installer now refuses when the key is set at all;
  - a merge taking the old tip only as its second parent passed, replacing the branch's first-parent history; the old tip must now be the first parent of the oldest added first-parent commit;
  - the installer treated any file containing the marker as its own; the marker must now be the hook's second line.

  The documentation's "however git is run" was narrowed to "made through git", naming the two things that pass it. A breakage test that only emptied `GIT_NO_REPLACE_OBJECTS` passed every test, because git treats the variable as set even when empty; removing the variable failed the replacement test, as it should.
- **Codex review of PR B, round 2 (CHANGES REQUESTED).** It confirmed all four round-1 findings resolved, and found no bypass in the ordinary operations it tried: forced and multi-ref `update-ref`, symbolic refs, renames, fetch, local push and receive-pack, worktrees, octopus merges. Its new findings, fixed:
  - **An alias of a packed branch looked new.** Once `master` was packed (after `git gc`), `update-ref refs/heads/maſter` found no loose `master` and read as creating a new branch. The hook now reads the old value under the protected branch's canonical name.
  - **The hook refused `git pack-refs --prune`, and so `git gc`.** A logging hook showed what packing passes: it writes `packed-refs`, then deletes each loose copy in its own transaction with no `packed-refs.lock` held. A real `git branch -D` holds that lock, with new content lacking the branch. So a "deletion" passes only when no lock is held and `packed-refs` already has the same ref at the same commit.
  - **"Enforced twice" overstated GitHub's part.** The ruleset stops rewriting and deletion; it does not make the remote merge-only. `CLAUDE.md` now says which guard does what.
- **`git_gate.py` asks when `git config` includes or writes another file** (`include.path`, `includeIf`, `--file`, `--blob`). That follows the security review's point that `core.hooksPath` can be set indirectly. A sandboxed session cannot write `.git/config` or `~/.gitconfig` anyway, so this only covers the forms that still reach config.
- **What the hook cannot stop: `core.hooksPath` set by a program.** Hooks are found through configuration, so a command run with `-c core.hooksPath=/dev/null`, or the `GIT_CONFIG_*` variables, runs without them. That is the user's documented bypass, but any program the agent runs can use it too: a script it wrote, for example, which `git_gate.py` cannot read into. A later security review of this PR flagged it, and it is the same class as the direct ref-file write below.
- **What the hook cannot see: writes that bypass git.** A process writing `.git/refs/heads/develop`, or editing `.git/packed-refs`, changes the branch without a reference transaction. The sandbox allows writes under `.git/refs`, so it does not stop this either. That is deliberate tampering rather than a mistake. The auto-mode classifier and the GitHub ruleset on public repositories are the remaining guards. Closing it locally would take `sandbox.filesystem.denyWrite` entries for those files. Those entries would also make every sandboxed git command that updates the three branches fail, and they need testing against partial failures like the ones `.git/config` causes (plan 0006). They are left to the user's decision. The same entries would also close the `core.hooksPath`-from-a-program bypass above. With the protected ref files unwritable inside the sandbox, no sandboxed process could move those branches, hooks or no hooks; only an unsandboxed command, which needs the user's approval, could. That is exactly the policy. The question is the cost:
  - every merge into `develop` and every pull of `master` would have to run unsandboxed;
  - `.git/packed-refs` holds every ref, so denying it risks partial failures in routine sandboxed operations (deleting a packed feature branch, `gc`); not denying it leaves a packed `develop` editable.
- **After merge (2026-10-12): the legacy graft file.** A security review of the merged hook found that grafts rewrite parents just as replacement objects do, and `GIT_NO_REPLACE_OBJECTS` does not cover them. A probe confirmed both forms moved `develop` onto a plain commit: `.git/info/grafts`, which the sandbox lets a session write, and `GIT_GRAFT_FILE`. The hook now also sets `GIT_GRAFT_FILE=/dev/null`. A test covers both forms, and it failed against the hook without the setting.
- **No ADR.** Every piece is a small script or a rule that can be removed again, so this fails the "hard to reverse" gate.

## Verification

- `python3 -m unittest discover -s git-hooks`: 32 tests pass on this macOS machine. The three filesystem-folding tests (`DEVELOP`, `maſter`, `maſter` of a packed branch) run only on a case-insensitive filesystem. Further breakages, each failing tests:
  - the case-sensitive match restored;
  - the lock-identity check removed;
  - replacement objects honoured;
  - the first-parent lineage check removed;
  - an empty `core.hooksPath` ignored;
  - the marker accepted anywhere in the file;
  - the old value read under the alias name;
  - the packing exemption removed;
  - the packing exemption ignoring `packed-refs.lock`.
  - **Refused:** a direct commit, a fast-forward over plain commits, a reset, a force move, an amend, a revert on the branch, deletion, `main` and `master` alike, and a force move from a linked worktree.
  - **Allowed:** a merge, a fast-forward over merges, a revert brought in by a merge, creating a protected branch, a repository's first commit, anything on other branches, switching branches, and the user's bypass.
  - **Installer:** it updates its own copy, refuses a foreign hook, refuses under `core.hooksPath`, and refuses outside a repository.
  - **GitHub script:** it posts the ruleset when none exists and updates it by id when one does.
- Ten deliberate breakages, each run on a scratch copy, all failed tests:
  - `develop` unprotected;
  - the hook disabled;
  - the deletion check removed;
  - the ancestor check removed;
  - the merge check removed;
  - forced updates treated as new branches;
  - the installer overwriting a foreign hook;
  - the installer ignoring `core.hooksPath`;
  - the GitHub script always posting;
  - the force-push rule dropped.
- `python3 -m unittest discover -s hooks`: `git_gate.py`'s suite still passes. A breakage removing its new `core.hooksPath` check failed 4 tests.
- After merge:
  - install the hook in this clone with `git-hooks/protect-branches.sh` and confirm a direct commit on `master` is refused;
  - apply the ruleset to `Taka499/claude`, `tia-tools/gakumas-supportcards` and `tia-tools/releases`, and read each back with `gh api repos/<repo>/rulesets`.
