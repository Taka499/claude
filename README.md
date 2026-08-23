# claude — central Claude Code configuration

This repository **is** the live user-level Claude Code configuration (`~/.claude`) for this machine, versioned and developed like software. Merging a PR here changes the harness for every project.

The approach emulates [isamu/claude](https://github.com/isamu/claude) (see the article [「コードレビューをやめた」](https://zenn.dev/singularity/articles/stopped-reviewing-my-code)): the global config lives in a repo, every change is a PR, and the PR history records how the harness evolved. The content, however, follows this user's own system — ExecPlans as immutable narrative logs, ADRs with a three-gate filter and mandatory provenance, and `CLAUDE.md` as an auditable index — originally developed in `Taka499/project-template` and battle-tested in `gakumas-rehearsal-automation`.

## Layout

- `CLAUDE.md` — the global rules file, deployed as `~/.claude/CLAUDE.md`. Thin by design: always-on rules only; long reference material lives in `docs/` and is read on demand.
- `skills/` — user-level skills, deployed as `~/.claude/skills/`. General-purpose only; project-specific skills stay in their repos. Only `grill-me` sets `disable-model-invocation: true`, and deliberately: it opens an open-ended interview that must never start on its own inference. The rest (`close-out`, `harvest-session`, `codebase-design`, `adopt-from-sibling`, `backlog`) are safe for the model to reach for when the situation matches their description.
- `commands/` — user-level slash commands, deployed as `~/.claude/commands/`. Short prompt templates (`/execplan`, `/commit`, `/read-docs`); anything with real procedure belongs in `skills/` instead.
- `docs/` — read-on-demand references: the canonical ExecPlan methodology (`PLANS.md`), distilled stack notes (`rust.md`, `typescript.md`, `python.md`), the cross-stack testing doctrine (`testing.md`), and this repo's ADRs (`docs/adr/`).
- `plans/` — lightweight plan files (goal / changes / verification) committed alongside non-trivial PRs. Not full ExecPlans: harness changes are small and reversible, so the ceremony is scaled down deliberately (see `plans/0001-bootstrap-central-claude.md` § Decision Log).

## Deployment

Clone anywhere, then symlink the tracked pieces into `~/.claude` (the rest of `~/.claude` — sessions, todos, settings — is runtime state and stays untouched):

    ./setup.sh              # macOS / Linux / WSL / Git Bash
    pwsh ./setup.ps1        # Windows PowerShell (uses junctions for dirs; may need Developer Mode for the file symlink)

Both scripts are idempotent and back up anything pre-existing before linking. Note what that means for a *directory*: `~/.claude/skills` is replaced wholesale, so every skill previously living there leaves the live config and survives only inside the timestamped `skills.pre-central.*` backup. The scripts print a warning when this happens — port anything you still want into `skills/` here and re-run. After deployment, the working tree of this clone is live config: keep it on `master` except while developing a change.

Two consequences of linking whole directories are worth knowing before they surprise you. Anything that installs skills into `~/.claude/skills` (a desktop app, a plugin installer) now writes **into this repository's working tree**, where it shows up as untracked files in `git status` — decide per case whether to adopt it into the repo or leave it untracked. And because `git status` is no longer only about your own edits, a dirty tree here is not automatically something you introduced.

### The one file this repo does not deploy

`~/.claude/settings.json` stays untracked and hand-maintained, per [`docs/adr/0002-settings-json-stays-untracked.md`](docs/adr/0002-settings-json-stays-untracked.md): Claude Code owns that file and rewrites it at runtime, and there is no user-level local-override tier to split app-written preferences from hand-authored policy. The trade-off is that `permissions` — where the git rules are actually *enforced* — is unversioned, so the invariants live here instead and are worth re-checking whenever the file is touched:

- No history-mutating git command (`commit`, `push`, `merge`, `rebase`, `reset`) may sit in `permissions.allow`; they belong in `ask`, so the harness enforces `CLAUDE.md` § Git Operations rather than relying on the agent obeying prose. A stale `Bash(git commit *)` allow entry contradicted that rule undetected until an audit found it.
- `permissions.ask` also covers `git checkout *`: switching branches in the deployed clone silently swaps the live global config (the hazard in ADR 0001).
- Mutating `git -C <other-repo> …` forms are denied while the read-only ones are allowed — a blanket `Bash(git -C *)` deny breaks `/adopt-from-sibling`, whose whole job is reading a neighbouring checkout.
- Hook commands must be self-contained and portable. They run under `sh -c` on macOS/Linux and Git Bash on Windows, so a bare `afplay …` raises a non-blocking hook error on every Windows notification; branch on `uname -s` inline and end with `exit 0`.
- JSON admits no comments, so any non-obvious `deny` entry (the `grep`/`find`/`cat`/`head`/`tail` bans, which exist to push work onto the dedicated file tools) needs its reason recorded here rather than in the file.

## Changing the harness

1. Feature branch, following `CLAUDE.md` § Git Operations (yes, this repo obeys its own rules).
2. Non-trivial change → add a short plan file in `plans/` (goal, changes, verification — ~40 lines, isamu-style).
3. Harness-architecture decision that passes the three-gate test (hard to reverse, surprising without context, real trade-off) → ADR in `docs/adr/`. Expected to stay in the low single digits; most changes need none.
4. PR to `master` with the rationale in the description. Merge = deploy.

## Relationship to project-template

`Taka499/project-template` remains the per-project scaffold: `docs/adr/README.md` (ADR convention), `docs/plans/`, and the `CLAUDE.md` skeleton that new projects copy. Everything reusable across projects — rules, skills, stack notes — lives here instead and reaches projects through `~/.claude`.

The ExecPlan methodology is the one document both repos need. `docs/PLANS.md` here is the **canonical** copy: global `CLAUDE.md` mandates ExecPlans, so the definition has to be readable from any project, including one with no scaffold checked in. project-template still ships a copy — a plan must be followable from a fresh clone with no `~/.claude` — but that copy is a downstream sync target, not an independent document. When this file changes, propagating it to project-template is the follow-up PR.

## Attribution

- The delivery mechanism (repo-as-`~/.claude`, every change a PR) emulates [isamu/claude](https://github.com/isamu/claude); `adopt-from-sibling` and `harvest-session` are re-expressed from its skills and Continuous Learning loop. That repository states no license, so nothing is copied from it verbatim — the ideas are restated in this system's own terms and vocabulary.
- `grill-me`'s interview protocol is adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (`grilling`), MIT.
- `docs/testing.md` and the lint policy in `docs/typescript.md` are distilled from the article [「1日500コミットは、もう読めない ── だからコードレビューをやめた」](https://zenn.dev/singularity/articles/stopped-reviewing-my-code) and the reference configs it cites.
- `codebase-design` uses deep-module vocabulary after Ousterhout (*A Philosophy of Software Design*) and Feathers' notion of a seam, with the rejections recorded in the skill itself.
- Everything else is original to this repository and covered by [`LICENSE`](LICENSE) (MIT).
