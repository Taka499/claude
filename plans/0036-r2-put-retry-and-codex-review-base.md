# Plan: an R2 bulk upload retries a failed put; codex-review takes its base from the remote

Two lessons from the gakumas-supportcards plan that published skill card icons and sprite sheets for gkms-memomemo (2026-10-31). The user chose both for capture at the plan's close-out.

## Goal

1. **R2.** A bulk upload through `wrangler r2 object put` stopped on one transient API error, and the stack note on R2 had nothing about it.
2. **codex-review.** The skill's snapshot step took the review's base from the repository's local base branch. When that branch is behind its remote, the reviewed diff holds commits the base already has.

## Changes

- **`docs/cloudflare.md` § R2 object storage:** a new entry, added beside the two existing ones.
  - **What:** a single put can fail with `500`, code 10500 "Internal authentication error", among good puts with the same login; it is not a login problem.
  - **What to do:** retry the same put after short waits, which is safe because the put is idempotent and synchronous, and keep the upload order that makes a stop harmless.
- **`skills/codex-review/SKILL.md`:**
  - **§ 2:** the snapshot fetches the repository first and then copies its `refs/remotes/origin/<base>`, instead of its local `refs/heads/<base>`. A paragraph says why, gives the measured case, and gives the fallback for a repository with no remote.
  - **§ 1:** scoping a branch's diff now says `git fetch`, then `git diff origin/<base>...HEAD`.

  This is a correction, not an alternative: the old form is wrong whenever the local base is behind, so it is replaced in place. A session following the old text gets the new form the next time it loads the skill. A review already run with a stale base should be checked by comparing its `git diff --stat` with the pull request's.

## Evidence

- **R2,** in gakumas-supportcards, `docs/plans/EXECPLAN_SKILLCARD_DATA_AND_ICONS.md`:
  - § Surprises & Discoveries: the failure and the consistent bucket.
  - Decision K20: the retry, now in `scripts/images/r2.py`, PR #72 there.
  - Progress, 2026-10-31 17:21Z: the rerun with the retry finished all about 3,400 puts and the 39 sheets.
- **codex-review,** in the same session: the snapshot for the second pull request's final review was made with `"develop:refs/remotes/origin/develop"`. Its `git diff --stat origin/develop...HEAD` covered 37 files (+2,781). The repository's local `develop` had not moved since the branch was cut, and the first pull request had been merged into the remote `develop` since. Fetching `+refs/remotes/origin/develop:refs/remotes/origin/develop` into the same snapshot gave 25 files (+1,059), the pull request's own. It was caught before Codex ran, by the size of the stat.

## Verification

- A scratch reproduction with a base named `trunk`, since a scratch repository without a GitHub remote is guarded by the merge-only hook, which refused a branch named `develop`:
  - a bare remote whose `trunk` gained a merge of `feature-1` after the working clone last moved its local `trunk`, which is then 2 behind;
  - `feature-2` from `origin/trunk`, adding `c`.
  - **Result:** the old fetch gives `git diff --name-only origin/trunk...HEAD` = `b c`, with `b` already in the base. The new fetch gives `c`.
- `grep -n 'refs/remotes/origin/<base>' skills/codex-review/SKILL.md` finds the new fetch line and the paragraph.
- No rule in `~/.claude/settings.json` denies `git -C * fetch*`, so the added `git -C <repository> fetch` is not refused (the deny list covers add, commit, push, merge, rebase, reset, checkout and clean).
