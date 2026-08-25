# Plan: Stop claiming a namespace we don't own — link skills individually

## Goal

During the previous session MulmoTerminal installed ten skills into `~/.claude/skills`, and because that path was a symlink to this repo, all ten appeared as untracked files in the working tree. More tools will ship skills over time, so this is structural, not an incident: linking the whole directory declares that this repo owns every skill on the machine. It never did. After this change `~/.claude/skills` is a real directory again, this repo links in only the skills it authored, and `git status` here means "changes I made" once more.

## Changes

- `setup.sh` / `setup.ps1` — `skills/` is no longer linked as a directory. `link_skills` / `Set-SkillLinks` create `~/.claude/skills` as a real directory and link each skill in individually, then prune links that point into this repo but no longer resolve (skill deleted, or absent on the branch now checked out). `refuse_old_skills_layout` / `Assert-NotOldSkillsLayout` detect the pre-0003 layout and exit with the migration steps instead of migrating automatically.
- `docs/adr/0003-skills-are-linked-per-skill.md` — the decision, the rejected `.gitignore` allowlist, and the two costs accepted.
- `docs/adr/0001-…` — one appended sentence recording that 0003 narrows it. Its status stays `accepted`: the deployment model is unchanged for `CLAUDE.md`, `docs/` and `commands/`, so neither `superseded-by` nor `rescinded` fits.
- `README.md` — the layout entry, the deployment section (the directory-backup warning now concerns `commands/`), and the two consequences of the new skills mechanism.
- **Migration performed once on this machine** (not part of the commit): `~/.claude/skills` replaced with a real directory and the ten `mulmoterminal-*` directories moved out of the repo into it. Their absolute path is unchanged from MulmoTerminal's perspective.

## Decision Log (session 2026-08-24)

- **Per-skill linking over a `.gitignore` allowlist** — decided on failure mode, not elegance. A forgotten allowlist entry leaves your own skill live but untracked, buried in a `git status` full of vendor noise, and lost on the next machine; a forgotten `./setup.sh` leaves it tracked but not live, which announces itself immediately. Full reasoning in ADR 0003.
- **Migration refuses rather than guesses** — the only mechanical way to tell "a skill an installer dropped here" from "a skill of mine I haven't committed yet" is git-tracked status, and being wrong moves the user's uncommitted work out of the repo. The script prints the steps and stops. This branch will realistically never fire again after today, and is kept for any other machine still on the old layout.
- **`docs/` and `commands/` stay whole-directory links** — nothing but this repo writes there today. Revisit per ADR 0003's closing line if that changes.
- **Verified the mechanism before building on it** — that Claude Code resolves a per-entry symlink inside `skills/` was an assumption, and the whole design rests on it. Checked empirically first (below) rather than after the fact.

## Verification

- **Per-entry symlink resolution**: a probe skill whose directory was a symlink to a path outside the repo loaded via the Skill tool, reporting base directory `~/.claude/skills/symlink-probe`, and appeared in the skills listing without a restart. Probe removed afterwards.
- **Refusal path**: `./setup.sh` against the old layout exits 1 and prints the four migration steps (observed before migrating).
- **Migration**: `git ls-files skills/` listed exactly the six skills this repo owns; `git status --porcelain --untracked-files=all skills/` listed exactly the ten `mulmoterminal-*` directories. Only the untracked ten were moved.
- **Deployment**: re-running `./setup.sh` links all six individually and reports the other three targets already linked. All six re-registered in the live skills listing, as did the ten external ones from their new home.
- **Prune**: a deliberately dangling `ghost -> skills/deleted-skill` link is removed on the next run (17 entries → 16), while `mulmoterminal-config` (a real directory) and `backlog` (our link) both survive.
- **Cleanliness**: `git status --porcelain skills/` is empty — no external skill remains in the working tree.
