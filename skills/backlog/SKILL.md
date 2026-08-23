---
name: backlog
description: Append a feature idea or todo to the project's backlog file without implementing it. Use when the user wants to park an idea for later — "add this to the backlog", "note this down for later", "don't build it now, just record it".
---

# Backlog

Record an idea where the project already keeps them, and stop there. The value of this skill is that it never turns into implementation: parking an idea has to be cheaper than building it, or it won't happen.

## Steps

1. Find the backlog file. Use the first that exists: `docs/BACKLOG.md`, `_docs/BACKLOG.md`, or whatever file the repo's `CLAUDE.md` names. If none exists, ask where it should live rather than assuming a layout — repos differ (`docs/` vs `_docs/`), and a backlog created in the wrong place is one nobody reads.
2. Append the item as a checkbox line: `- [ ] <description> (YYYY-MM-DD)`. Run `date` for the date rather than relying on memory, per global `CLAUDE.md` § General.
3. Confirm to the user what was added, quoting the line.

## Rules

- Do NOT implement the idea, start a plan for it, or open files to assess feasibility. Just record it.
- Keep the user's own framing of the idea; sharpen only what is ambiguous out of context (an idea recorded as "fix the thing" is worthless in three months).
- If the idea is large enough to need design work, say so in one sentence and suggest `/grill-me` later — but still just record it now.
