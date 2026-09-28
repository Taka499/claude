# GitHub Actions — distilled cross-project lessons

Lessons about GitHub Actions itself, independent of the project's language. Language-specific workflow advice stays in that language's stack note (`docs/typescript.md` § GitHub Pages deployment via Actions, `docs/python.md` § Scheduled bots on GitHub Actions); where an entry here limits one of those, the entry there says so.

## Automated jobs: the built-in token and the schedule

**Anything done with the built-in `GITHUB_TOKEN` starts no workflows.** A pull request opened with it runs no `pull_request` checks; a merge made with it fires no `push` to the default branch and no `pull_request: closed`. GitHub does this deliberately to prevent loops; `workflow_dispatch` and `repository_dispatch` are the only exceptions. So "the checks run on the bot's PR" and "deploy on push to main" both silently never happen for an automated job that uses `GITHUB_TOKEN` — no red run, simply no run (gakumas-supportcards, 2026-09-22).

**Scheduled (`cron`) workflows run only from the default branch.** They use the workflow file as it is on that branch and check out that branch's code. There is no pointing a schedule at another branch's code while keeping its own workflow version.

**For a scheduled job that updates data and publishes, run the gates in the job and start the deploy explicitly.** What worked for a daily data-update job:

1. Run every gate — tests, type check, lint, domain checks — inside the update job, before any PR exists.
2. Open the PR only as an audit trail and merge it immediately with a merge commit. If a branch-protection review rule blocks that merge, the PR is left for a person — the intended fallback.
3. Start the deploy by calling the deploy workflow with `workflow_call`, not by relying on the push event.

Rejected: a personal access token or GitHub App just so the bot's PR gets checks — a long-lived credential for no extra safety, since the same gates already ran; and a separate `prod` branch — the schedule would run the default branch's workflow against `prod`'s code (gakumas-supportcards, 2026-09-22).

**If a scheduled job must publish, make the default branch production.** Then the scheduled workflow and the code it runs are always the same version. A `develop`-as-default, `main`-as-production model splits them.

**State in the workflow file why the gates live in the job.** Anyone who later "simplifies" it by moving the gates onto the PR, or by dropping the explicit deploy call, silently turns them off — nothing fails, the checks and the deploy just stop happening. A comment at the top of the workflow is the only guard.

**Make a dead schedule visible.** In a public repository GitHub disables scheduled workflows after 60 days without repository activity. A periodic "still alive" notification — e.g. one message per week even when nothing changed — turns silence into a signal that the schedule stopped, not that nothing happened (gakumas-supportcards, 2026-09-22). A job that commits back to its own repository also keeps the schedule alive (`docs/python.md` § Scheduled bots on GitHub Actions).
