# Plan: Harvest from gakumas-supportcards — GitHub Actions built-in token and schedules, Cloudflare R2 stored Cache-Control

## Goal

Two lessons from the gakumas-supportcards project generalise beyond it and cost real time there. Both are platform behaviour that no test catches, and both fail silently:

- **GitHub Actions (2026-09-22).** A daily data-update job was designed to open a PR, let the checks run on it, merge it, and let the push to `main` deploy. With the built-in `GITHUB_TOKEN` none of that happens. A PR opened with that token starts no workflows, and neither does a merge made with it. Scheduled workflows also run only from the default branch, so a separate `prod` branch was not an option either.
- **Cloudflare R2 (2026-09-21).** Private master images had been uploaded with `wrangler r2 object put --cache-control "public, max-age=31536000, immutable"`, on the reasoning that they were never served to users, so caching did not matter. They were later overwritten with corrected versions. The Cloudflare dashboard kept showing the old images, because the stored Cache-Control is returned on dashboard downloads too, and the browser honoured `immutable`. The bucket looked stale. Comparing checksums of `wrangler r2 object get … --remote` against the local files showed it was correct.

## Changes

- `docs/github-actions.md` (new stack note), § Automated jobs: the built-in token and the schedule:
  - `GITHUB_TOKEN` starts no workflows; `workflow_dispatch` and `repository_dispatch` are the exceptions.
  - Schedules run only from the default branch.
  - The pattern that worked, with the rejected alternatives.
  - The default branch is production when a scheduled job publishes.
  - A comment in the workflow explains why the gates live in the job.
  - A weekly "still alive" notification against the 60-day disable.
- `docs/cloudflare.md` (new stack note), § R2 object storage:
  - The stored Cache-Control follows the object everywhere, including the dashboard.
  - Choose it by how the object may change: `private, no-cache` for anything overwritten, `immutable` only for keys that never get new content.
- Global `CLAUDE.md` § Debugging: when a symptom only shows up in a browser, compare checksums outside the browser before touching the data.
- Global `CLAUDE.md` § Stack Notes, and `README.md` § What lives here: list the two new notes.
- `docs/typescript.md` § GitHub Pages deployment via Actions: a caveat on the `peter-evans/create-pull-request` entry (no checks with `GITHUB_TOKEN`) and one on the `pull_request: closed` chaining entry (never fires when the merge used `GITHUB_TOKEN`), each pointing to the new note.
- `docs/python.md` § Scheduled bots on GitHub Actions: the 60-day disable rule is now limited to public repositories, and the entry on which branch the scheduled job checks out now notes that the workflow file also comes from the default branch.

## Decision Log (session 2026-09-28 to 2026-09-29)

- **New notes rather than an existing one.** The GitHub Actions lesson doesn't belong to any one language, and its neighbours were already split between `typescript.md` and `python.md`. The Cloudflare material was likewise split between `typescript.md` and `rust.md`. Existing entries stay where they are; moving them is out of scope.
- **Caveats are corrections, applied in place.** The two TypeScript entries and the Python entry are true only when the actor is not `GITHUB_TOKEN`, or when the production branch is the default branch. Under global `CLAUDE.md` § Continuous Learning, a missing condition is a correction, not an alternative. Each keeps its text and gains one sentence pointing at the new entry. A project that followed the old text and uses `GITHUB_TOKEN` should check whether its bot PRs ever ran checks.
- **The 60-day rule is limited to public repositories.** GitHub documents the automatic disable for public repositories. The capture prompt and `python.md` both stated it without that limit, and the user approved the in-place fix.
- **The debugging corollary goes in the global file.** It isn't specific to Cloudflare: a browser cache can make correct data look stale for any data source.
- **No ADR.** Prose notes, trivially reversible; fails gate one.

## Evidence (gakumas-supportcards)

- The update job runs every gate before creating the PR, merges the PR at once with a merge commit, and calls the deploy workflow through `workflow_call`. A branch-protection review rule, if enabled, leaves the PR open for a person. Two options were weighed and rejected there: a PAT or GitHub App so the bot's PR gets checks, and a `prod` branch. The conclusion drawn for branch models was that `main`, the default branch, should be production when a scheduled job publishes.
- The R2 incident: the bucket was proved correct by checksum comparison outside the browser, and the rule drawn was `private, no-cache` for overwritable objects and `immutable` only for keys that never get new content.

## Verification

- The platform facts come from the source project's sessions of 2026-09-21 and 2026-09-22, as relayed by the user in the capture request; they were not re-tested in this repository.
- The new notes cite only their own sections and paths inside this repository, and name the source project by bare name and date.
- Prose only; there is no test to run. After merge, read the two new notes once through `~/.claude/docs/` (symlinked) to confirm they deploy.
