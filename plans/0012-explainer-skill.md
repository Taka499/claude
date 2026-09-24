# Plan: `explainer` skill, and one Bun stack-note entry — harvest from the nudge hash-pinning session

## Goal

In the nudge session of 2026-09-24 the user could not connect a security finding ("a third-party action on a movable tag rather than a full commit hash") to their own setup. Two chat answers did not land; two self-contained HTML pages did — one on what a tag is, one on who owns `id-token: write` and who can change which repository. The user asked for that way of explaining to become a global skill. The same session found one Bun trap worth a stack-note line.

## Changes

- `skills/explainer/SKILL.md` — when to write an explainer page, and how: name the one gap the user cannot connect; gather facts about their setup from the machine before writing; climb from the primitive to their own case; the building blocks (a concrete cast with colour-coded owners, a who-owns/who-can-change table, normal-vs-changed step flows, a one-sentence connection card, a countermeasure table, inline SVG with English labels); languages; verification; hand-over.
- `skills/explainer/template.html` — the styles, the language switcher, and one example of every building block, taken from the two pages that worked.
- `docs/typescript.md` § Bun install and tooling traps — `Bun.Glob#scan` skips hidden directories without `dot: true`; assert a scanned set is non-empty; match `.yml` and `.yaml`.
- `README.md` (the list of model-invocable skills) and `CLAUDE.md` § Skills — one pointer each.

## Decision Log (session 2026-09-24)

- **Technical terms stay in English in every language** — the user's correction, after the first page translated commit, job and tag into katakana and Chinese: "too hard to link with my knowledge". It is in the skill because the skill produces the multilingual text; the preference also applies outside HTML, so it is kept in file-based memory as well.
- **Write each language directly, never convert by find-and-replace** — the correction above was first applied with a regex pass, which stripped the spaces around inline code and mangled a heading; it was redone from a backup. Recorded in the skill as a rule because the shortcut is tempting and the damage is easy to miss.
- **Model-invocable, no `disable-model-invocation`** — the skill writes one file outside the repository and changes nothing else, so reaching for it on its own inference is safe; the description limits it to explicit requests and visible confusion.
- **A template file, not only prose** — the scaffolding (switcher, CSS, block markup) is identical every time and was the part that took longest to get right; copying it keeps attention on the content.
- **Default languages English / 日本語 / 中文** — the set the user asked for. The skill says to ask only if a different set is wanted.
- **Not captured**: a global rule to pin GitHub Actions by commit hash — the user struck it from this harvest; it lives in nudge's `docs/adr/0003` for that project only.
- **No ADR** — a skill and a note, trivially reversible. Fails gate one.

## Verification

- `template.html` parses with every tag closed (Python `html.parser` check) and has the same number of `data-l` blocks per language (26 each).
- The two pages the skill is drawn from were checked the same way in the session (64 and 75 blocks per language).
- The Bun entry is from measurement: without `dot: true` the scan returned no workflow files and the non-empty assertion failed; with it, the test found all three workflows. A temporary `action.yaml` probe with a nested `uses:` turned the `.{yml,yaml}` test red.
- After merge, `./setup.sh` links `skills/explainer` into `~/.claude/skills/` (per `docs/adr/0003-skills-are-linked-per-skill.md`).
