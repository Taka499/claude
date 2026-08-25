# Plan: Close the gaps found auditing the deployed config

## Goal

An audit of this repo against the live `~/.claude` it claims to be found that the boundary between "governed by the repo" and "not governed at all" was undrawn, and that the ungoverned side contradicted the governed one. The worst case: `CLAUDE.md` § Git Operations says NEVER commit without permission while `~/.claude/settings.json` carried `Bash(git commit *)` in `permissions.allow` — the rule was prose only, and the layer that actually enforces it said the opposite. This change draws that boundary explicitly, brings the untracked side into line, and closes four smaller gaps found in the same pass.

## Changes

- **`~/.claude/settings.json` (untracked, edited in place, not part of this commit)** — `git commit *` and `git checkout *` moved from `allow` to `ask`; the blanket `Bash(git -C *)` deny replaced by read-only allows (`status`/`log`/`diff`/`branch`/`show`/`ls-files`) plus explicit denies for the mutating forms (`add`/`commit`/`push`/`merge`/`rebase`/`reset`/`checkout`/`clean`); both sound hooks rewritten to branch on `uname -s` (afplay / PowerShell `[console]::beep` / paplay) and end with `exit 0`.
- **`docs/adr/0002-settings-json-stays-untracked.md`** — records why that file is the one piece of `~/.claude` this repo does not deploy, and what was rejected (symlink, generate-by-merge).
- **`docs/PLANS.md`** — the ExecPlan methodology, vendored from `Taka499/project-template` and marked canonical, with a header explaining precedence against a project's own copy.
- **`commands/`** — newly tracked and deployed. `execplan.md` discovers `docs/PLANS.md` → `_docs/PLANS.md` → `~/.claude/docs/PLANS.md` instead of hardcoding `_docs/PLANS.md`; `commit.md` proposes a commit and drops its `Bash(git add:*)` grant instead of creating one; `read-docs.md` gains the milestone-listing requirement.
- **`skills/backlog/`** — ported back into the live config after `setup.sh` displaced it, generalized to discover the repo's backlog location.
- **`setup.sh` / `setup.ps1`** — link `commands/`; warn explicitly when a *directory* is backed up, since that silently removes its whole contents from the live config; a comment records why `settings.json` is absent.
- **`CLAUDE.md`** — PLANS.md fallback for repos with no copy; `/backlog` added to the skills index; a pointer that work *in this repo* follows README § Changing the harness rather than ExecPlan ceremony.
- **`README.md`** — `commands/` and `PLANS.md` in the Layout; the settings.json invariants; the directory-backup and third-party-writes consequences of symlinking whole directories; PLANS.md canonicity; an Attribution section; `pwsh ./setup.ps1`.

## Decision Log (session 2026-08-16)

- **`settings.json` stays untracked** — user decision. It is Claude Code's own file and the app rewrites it; symlinking risks a temp-file-and-rename write silently detaching the deployment, and generate-by-merge was judged more machinery than the problem deserves. → ADR 0002. The enforcement gap it leaves is mitigated documentarily, in README § The one file this repo does not deploy.
- **`git -C` denied by verb, not wholesale** — the blanket deny was blocking read-only inspection (it blocked this very audit twice) and therefore `/adopt-from-sibling`. Pattern-matched denies are bypassable by a determined command string; this is a friction control, not a security boundary, and the mutating-git rules in `CLAUDE.md` remain the real constraint.
- **`docs/PLANS.md` here is canonical, project-template's copy is downstream** — the alternative (leave it only in project-template) leaves `CLAUDE.md`'s ExecPlan MUST unactionable on any machine without that clone, and violates this repo's own documentation self-sufficiency rule. Two copies still exist because a checked-in plan must be followable from a fresh clone with no `~/.claude`; the drift risk is accepted and named in README.
- **Skill invocation asymmetry made intentional rather than uniform** — `grill-me` alone keeps `disable-model-invocation: true` because an unsolicited interview is disruptive in a way an unsolicited capture ritual is not. Documented in README instead of changed.
- **The old `commit` skill was not ported back** — `commands/commit.md` and the `commit-commands` plugin already cover it, and its "stage and commit each group separately" instruction contradicted the ask-first rule. `backlog` was ported; nothing else was in the displaced set.
- **project-template left untouched this round** — syncing its `PLANS.md` header and removing the now-duplicated methodology is a separate PR in that repo, not a silent cross-repo edit.

## Verification

- `python3 -c "import json; json.load(...)"` on `~/.claude/settings.json` parses; asserted no `git commit` in `allow`, present in `ask`, and no blanket `git -C` deny.
- The Stop hook command run through `sh -c` on this machine plays and exits 0; the `MINGW*`/`MSYS*`/`CYGWIN*`, `Linux`, and unknown-platform branches each select the expected arm, the last silently.
- `./setup.sh` re-run: reports `ok: … already linked` for the three existing links and creates `~/.claude/commands` fresh.
- Every path referenced from `CLAUDE.md` and `README.md` exists in the repo.
- Skill and command frontmatter is valid YAML; each skill's `name` matches its directory.
