# Plan: Protect main, master and develop in git itself and on GitHub, and give every repository a remote

## Goal

Plan 0018 made commits on a feature branch free and kept history on `main`, `master` and `develop` behind the user's approval. Its `git_gate.py` hook reads command text. Three Codex review rounds and five security reviews kept finding command shapes that text cannot classify, and git run from a program file is invisible to it altogether. A guarantee has to sit where git itself changes a branch. This plan adds that guard in two places:
- **Locally:** git's `reference-transaction` hook, which sees every branch update, however git was run.
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
- **No ADR.** Every piece is a small script or a rule that can be removed again, so this fails the "hard to reverse" gate.

## Verification

- `python3 -m unittest discover -s git-hooks`: 23 tests pass.
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
