---
name: backlog
description: Append a feature idea or todo to the project's backlog without implementing it — the backlog file, or the Triage column of the project's GitHub board where it keeps its tasks on one. Use when the user wants to park an idea for later — "add this to the backlog", "note this down for later", "don't build it now, just record it".
---

# Backlog

Record an idea where the project already keeps them, and stop there. The value of this skill is that it never turns into implementation: parking an idea has to be cheaper than building it, or it won't happen.

## Steps

0. If the repository root has a `.task-board.json`, the project keeps its tasks on a GitHub board, so file the idea there instead of in a file. Run `python3 -I ~/.claude/skills/task-board/board.py file --triage --title "<the idea>" --body "<context, in the user's framing>"`, sandboxed. Triage means recorded, not queued: parking is not a request to build it. Confirm with the issue number the helper prints, and stop; steps 1–3 do not apply. The `task-board` skill describes the board.
1. Find the backlog file. Use the first that exists: `docs/BACKLOG.md`, `_docs/BACKLOG.md`, or whatever file the repo's `CLAUDE.md` names. If none exists, ask where it should live rather than assuming a layout — repos differ (`docs/` vs `_docs/`), and a backlog created in the wrong place is one nobody reads.
2. Append the item as a checkbox line: `- [ ] <description> (YYYY-MM-DD)`. Run `date` for the date rather than relying on memory, per global `CLAUDE.md` § General.
3. Confirm to the user what was added, quoting the line.

## Rules

- Do NOT implement the idea, start a plan for it, or open files to assess feasibility. Just record it.
- Keep the user's own framing of the idea; sharpen only what is ambiguous out of context (an idea recorded as "fix the thing" is worthless in three months).
- If the idea is large enough to need design work, say so in one sentence and suggest `/grill-me` later — but still just record it now.
