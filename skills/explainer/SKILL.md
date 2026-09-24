---
name: explainer
description: Write a self-contained, multilingual HTML page that explains a concept the user is confused about — built up from zero, ending in how it applies to their actual situation, with a language switcher (default English / 日本語 / 中文). Use when the user asks for an explanation "as an HTML", "a page I can read", "explain this to me in Japanese/Chinese too", or is confused by tacit knowledge (who owns what, why a check flags something, how pieces connect) and a chat answer has not landed.
---

# Explainer

A chat answer assumes the reader already holds the surrounding vocabulary. When the user says they are confused, the missing piece is usually tacit knowledge several steps below the question — what a tag *is*, who *owns* a permission — so the page starts there and climbs. The page is a deliverable the user reads at their own pace, possibly several times and in another language; it is not a place to show off everything known about the topic.

`template.html` beside this file holds the styles, the language switcher, and one example of every building block below. Copy it; do not rewrite the scaffolding.

## 1. Find the real question

Before writing, name in one sentence what the user cannot yet connect. "Who owns `id-token: write`, and who can change which repository?" is a question; "OIDC" is a topic. If the user asked for a second page because the first did not land, their words say what the first page skipped — build the new page around exactly that gap, not around a better version of the old one.

## 2. Gather facts before prose

Every concrete claim about *their* situation comes from the machine, not memory: commit hashes, which repository pins what, which file says what, dates. Run the commands, read the files. Claims about the outside world (an incident, a platform feature) get checked or hedged. A page that explains correctly and then misstates the user's own setup teaches the wrong thing with authority.

## 3. Structure: climb from zero, land on their case

Numbered sections, each introducing one idea that the next one needs. The usual arc:

1. The primitive, defined plainly (a commit and its hash).
2. The thing built on it (a tag points at a commit).
3. The property that causes the trouble (tags can move).
4. Where it meets the user's world (`uses: …@ref` downloads whatever the ref points at, into *your* job).
5. The risk or behaviour, with one real-world case if one exists.
6. The remedy, and what it costs.
7. **Applied to the user's actual repositories/project** — always last-but-one, with their real names and values.
8. Glossary.

Building blocks, all in the template:

- **A cast** when the confusion is about ownership or trust: a made-up but concrete third party ("Alice") next to the user, GitHub, an attacker. Colour-code each owner and reuse the colours as badges everywhere.
- **A "who owns what / who can change it" table.** Ownership confusions dissolve when every row names one owner.
- **Step-by-step flows**: the normal run, then the same run with one thing changed, failing steps marked red. The contrast carries the lesson.
- **A one-sentence connection card** after the flows: the whole causal chain in one sentence.
- **A countermeasure table**: measure / who does it / which step of the flow it breaks.
- **Inline SVG diagrams** with English labels only (proper nouns, file names); the caption under the diagram is translated.
- **Cards** for key facts (blue), risks (red), and what holds today (green).

## 4. Languages

Default set: English, 日本語, 中文 (simplified) — ask only if the user wants a different set. Every translatable element carries `data-l="en|ja|zh"`; CSS shows only the selected language; the switcher remembers the choice in `localStorage` and otherwise follows the browser language.

- **Keep technical terms and proper nouns in English in every language** — commit, hash, tag, branch, job, step, workflow, action, repository, token, permission, pull request, release, fork, and the like. The user links these concepts by their English names; katakana or Chinese translations break that link. Ordinary words stay translated. Put a space between an English term and the surrounding CJK text.
- **Write each language directly.** Do not produce one language and convert it by find-and-replace: a mechanical pass once stripped the spaces around inline code and mangled a heading, and had to be redone from a backup.
- Code blocks and hashes are shared, not translated; comments inside code may be.

## 5. Verify, then hand over

- Parse the file and check that tags nest (a short `html.parser` script is enough) and that each language has the same number of `data-l` blocks — a mismatch means a section is missing in one language.
- Re-read the section that applies the concept to the user's situation against the facts gathered in step 2.
- Save outside the repository — the session's scratch or drop directory, or `$TMPDIR` — never as an untracked file in the project. The sandbox blocks `open`, so give the user `! open <absolute path>` to run.
- In the reply: the path, a one-line summary per section, and anything unverified (e.g. "not viewed in a browser").

When the user corrects the page (a term, a wrong premise), fix the page and apply the correction to anything else in flight that depends on it.
