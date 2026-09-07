# Plan: Make "scaffold it from project-template" an executable step, and teach grill-me the greenfield case

## Goal

Both the global `CLAUDE.md` (§ ExecPlans and ADRs) and `grill-me` say "offer to scaffold from `Taka499/project-template`", and nothing executes it. On 2026-09-05 a `/grill-me` session started from `~/Developer` with a product idea and no repository: the skill's first step ("locate the capture homes") had nowhere to route, the interview ran with the Decision Log held in chat, and the scaffold was done by hand at the end — four files copied, two failed sandboxed `git init` attempts, `CLAUDE.md` filled, first commit proposed. That sequence will recur every time an idea precedes its repo. After this change it is a skill, and `grill-me` knows what to do when the repo does not exist yet.

## Changes

- `skills/scaffold-project/SKILL.md` — new. Settles name and parent directory with the user before creating anything; copies exactly `git ls-files` of the template rather than a hardcoded list; runs `git init -b main` outside the sandbox with the observed reason; fills the `CLAUDE.md` overview and ADR index from what the session knows and leaves the code-dependent sections as template comments; proposes but never runs the first commit.
- `skills/grill-me/SKILL.md` — "Locate the capture homes first" now names `scaffold-project` for the missing-scaffold case and gains a greenfield paragraph: run the interview first, make name and home the closing question, number decisions in chat so the final transfer is a copy.
- `CLAUDE.md` — one bullet under § Skills pointing at `/scaffold-project`; § ExecPlans and ADRs names the skill where it already said "offer to add it from project-template".
- `README.md` — `scaffold-project` added to the list of model-invocable skills in the layout section.

## Decision Log (session 2026-09-07)

- **Copy `git ls-files` of the template, not a fixed list** — the template will grow (it already gained `.gitkeep` in its last commit), and a skill carrying its own list would ship a stale scaffold without anyone noticing until a plan failed to find `docs/PLANS.md`.
- **`git init` runs unsandboxed, and the skill says why** — two sandboxed attempts failed: copying Xcode's sample hooks into `.git/hooks`, then writing `.git/config` after `--template=` had dodged the hooks. Plain `cp` and `python3` writes into the same new directory succeeded, so the failure is specific to git's lock-and-rename writes into a directory that is a *sibling* of the sandbox's writable ".", not a child. Recording the evidence in the skill stops the next session from re-deriving it or, worse, "fixing" it with a permission rule.
- **Name and home are the last question, not the first** — in the session they were asked last by accident (the skill assumed a repo) and it worked well: the design had a shape, so the name had something to name. The greenfield paragraph makes this deliberate.
- **Name candidates in more than one register** — the first candidate set was all short Japanese words, matching the neighbouring directories, and the user rejected all of them and asked for English. A neighbourhood is not a preference; the skill offers both and lets the user pick.
- **Model invocation stays enabled** — unlike `grill-me`, this skill cannot start an open-ended process on its own inference: it confirms name and path before creating anything and never commits. The check-before-create rule is what makes automatic invocation safe, so it is stated as the skill's first section.
- **No ADR** — the change is a skill and two paragraphs, all trivially reversible. Fails gate one.

## Verification

- `./setup.sh` run unsandboxed on this branch links `skills/scaffold-project` into `~/.claude/skills` (a new link, so the sandbox-off requirement from the README applies) and the skill appears in the session's skill listing.
- `grill-me` still loads and its "Locate the capture homes first" section reads correctly with the new paragraph in place.
- Switching back to `master` before merge leaves a dangling `scaffold-project` link that the next `./setup.sh` run prunes, per ADR 0003; after merge the link resolves again.
- The dry run of the procedure is the `~/Developer/redline` repository itself, created by hand on 2026-09-05 with exactly these steps; its first commit lists the four template files plus the ADRs and plan, which is the file list the skill's step 6 produces.
