# Plan: the attention page's Needs you as a table

## Goal

The user asked on 2026-11-02 for the attention page's Needs you list (plan 0036, D3) as a table. It was a bullet per job, with sub-bullets for the options, the recommendation and how to answer. On gkms-contest-ai's page, with 14 open jobs, the bullets were hard to scan.

## Decision

**D1. The line limit bounds fields, not rows.** The page's limit of `LINE_MAX` (120) characters applies to each field it shows: a title, an option's text or cost, a recommendation's why, a summary, a progress line. The helper checks each field when it is written. A table row joins several fields, so a row may run longer.
- Rejected: shortening the options cell to letters and a short label, with the full text on the issue. That sends the user to the issue to decide, which the page exists to prevent (plan 0036, D3).

## Changes

`skills/task-board/jobs.py`:
- **Needs you:** one Markdown table, one row per job, in the order the jobs come: oldest first, as `board.page_parts` sorts them. The columns are `#` (linked), kind, question, options, recommended, holds up, waiting, and answer with.
  - **decide:** its options share one cell, one per line (`<br>`), each with its cost, and its recommendation fills its own cell.
  - **approve:** the summary goes under the question, and the options cell reads `approve / decline`.
  - **capture and run:** the summary is the options cell.
  - **answer with** lists every declared answer, such as `` `#5 A` / `#5 B` ``.
  - **A malformed job** reads `malformed: …` with "fix it with the helper".
- **Cells:** each is flattened to one line, with every `|` escaped, so no field can break its row.
- **Around the table:** the warning for more than 7 jobs stays above it, and a blank line separates them, since Markdown needs one before a table. With no jobs there is no table, only "Nothing waits on you."
- **The module's docstring** states D1.

`skills/task-board/SKILL.md`: § The attention page describes the table.

## Verification

- **`python3 -m unittest discover -s skills/task-board`:** 187 tests.
  - **What they cover:**
    - a decision's row, cell by cell;
    - the approve, capture and run rows;
    - a `|` and a newline inside fields;
    - a malformed job;
    - the table under its warning, in the order given;
    - no table with no jobs.
  - **Shown to catch a break:** each of the 11 new rules was removed in turn, and each removal failed at least one test.
- **`/codex-review` on the branch's diff.**
- **In use:** gkms-contest-ai's page redraws as a table after the merge, on its next helper write or Stop hook.
