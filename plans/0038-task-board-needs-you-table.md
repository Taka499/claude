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
- **Cells:** each field is flattened to one line and shown as written. Backslash, `&`, `<`, `>` and `|` are encoded, the last as `&#124;`, which no table parser splits on, so a backslash before it cannot unescape it. The helper's own `<br>` is added after the encoding.
- **Links:** a link whose URL holds a space, `|`, a parenthesis, an angle bracket or a backslash shows as a plain `#N`.
- **Around the table:** the warning for more than 7 jobs stays above it, and a blank line separates them, since Markdown needs one before a table. With no jobs there is no table, only "Nothing waits on you."
- **The module's docstring** states D1.

`skills/task-board/SKILL.md`: § The attention page describes the table.

## Verification

- **`python3 -m unittest discover -s skills/task-board`:** 189 tests.
  - **What they cover:**
    - a decision's row, cell by cell;
    - the approve, capture and run rows;
    - a `|` and a newline inside fields;
    - a backslash before a `|`, HTML and `&` in a field;
    - a URL that could end its link;
    - a malformed job;
    - the table under its warning, in the order given;
    - no table with no jobs.
  - **Shown to catch a break:** each of the 11 table rules, and then each of the 7 encoding and link rules, was removed in turn, and each removal failed at least one test.
- **`/codex-review` on the branch's diff.**
- **In use:** gkms-contest-ai's page redraws as a table after the merge, on its next helper write or Stop hook.

## Codex review (2026-11-02)

**First pass: CHANGES REQUESTED.** Every finding was accepted.
- **HIGH, a backslash before a `|`:** `x\|y` became `x\\|y`, where the first backslash escapes the second, and the pipe splits the cell.
- **HIGH, links skipped the escaping:** a URL could carry a `|`, a newline or a `)`.
- **MEDIUM, raw HTML in a title rendered as HTML.**

**The fix:** each cell's text is made literal, with `|` as `&#124;`, and an unsafe URL loses its link (§ Changes). Codex also confirmed that the table's framing is valid GFM, and that D1 contradicts nothing in the skill.

**Second pass: CHANGES REQUESTED, one MEDIUM, accepted as a trade-off and not changed.**
- **The finding:** Markdown does not decode entities inside a code span, so a field holding `` `R&D` `` shows `R&amp;D`. The same goes for `|`, `<`, `>` or a backslash inside backticks.
- **Why it stays:** the page's fields are plain-words lines by design (plan 0036, D19), and a code span holding one of those five characters is rare. The cost is a visible entity in that case; reopening code spans would give back the structural safety the first pass asked for.
- **Confirmed:** the pass found the first three findings resolved, and the encoding order right.
