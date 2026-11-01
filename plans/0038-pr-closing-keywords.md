# Plan: a PR closes only the issue it claims

## Goal

GitHub closes every issue that a closing keyword names in a pull request's description, on merge into the default branch, wherever the phrase stands. On 2026-11-01 a description that only *reported* an issue closed it.

**The project:** gkms-memomemo (public, `tia-tools/gkms-memomemo`). A session was testing a daily workflow that keeps one issue open and posts to Discord when cards need a screenshot.

**What happened:**
- **The bug's PR.** The fix's PR, `tia-tools/gkms-memomemo#23`, described the bug as "a run on `develop` did not close #20". Its one intended keyword closed the bug's own issue (`Closes #22`).
- **The merge.** Merging #23 closed #20 as well, two seconds after `mergedAt`, by the merging user.
  - `gh pr view 23 --json closingIssuesReferences` → `20,22`.
  - #20's events: `closed Taka499 2026-11-01T06:24:06Z`, against `mergedAt` `2026-11-01T06:24:04Z`.
- **The cost.** #20 was the issue the test needed open, to show that a rerun leaves it alone. Two more test runs and two more public issues followed, #24 and #25, each with a Discord post to the user.

**What GitHub documents** (https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue, read 2026-11-01):
- **The keywords:** `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved`.
- **Where they count:** only in a PR targeting the default branch; the page states no rule about where in the description they must stand.
- **Commit messages:** they count too, "when you merge the commit into the default branch".

## Change

`skills/task-board/SKILL.md` § Steps 6, *Through PRs*, gains a paragraph:
- **The rule:** no issue but the claimed one may follow a closing keyword, in the description or in a commit message headed for the default branch. Other issues are named without a keyword before the number.
- **The check:** right after opening the PR, `gh pr view <PR> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'` must print `[N]` alone. If not, the description is edited before the merge is asked for.

**Why a check and not only the rule:** global `CLAUDE.md` § Quality Gates prefers a tool that checks a value over a rule a session must remember. A wording rule slips exactly when the text is written in a hurry, as this one was. `closingIssuesReferences` is GitHub's own reading of the description, so it catches what any re-reading would miss.

**Where it goes:** the task-board skill is where a session writes `Closes #N` in a PR. A project without a board does not close issues through PR descriptions under this setup.

## Verification

- **The check's command,** run against the real PRs:
  - on `tia-tools/gkms-memomemo#23` it prints `[20,22]`;
  - on `#27`, opened after this lesson with only `Closes #26`, it prints `[26]`.
- **Additive:** the step's existing text is unchanged, and the paragraph adds a check after `gh pr create`. A project following the old text loses nothing, and the next PR it opens gets the check.
