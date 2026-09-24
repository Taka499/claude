# Global Claude Code Configuration

This is the user-level `~/.claude/CLAUDE.md`, applied to every project on this machine. It carries only cross-project rules; project specifics live in each repository's own `CLAUDE.md`. The file is versioned in the `Taka499/claude` repository and deployed by symlink (per `docs/adr/0001-claude-repo-is-the-live-user-config.md`) — change it there via PR, never by editing a deployed copy in place. When working inside that repository itself, follow its `README.md` § Changing the harness: harness changes use lightweight `plans/` files, not the ExecPlan machinery this file mandates for project work.

> Keywords: **MUST** / **NEVER** = mandatory. **SHOULD** = recommended unless there is a clear reason not to. **MAY** = optional.

## General

- MUST only make changes that were explicitly requested — NEVER autonomously add features, tools, packages, or content. If something additional seems needed, ask first.
- When today's date is needed, MUST run the `date` command — NEVER rely on internal knowledge.

## Git Operations

- NEVER run `git commit`, `git push`, `git merge`, `git rebase`, or any other history-mutating git command without explicit user permission for that operation. Read-only git (`status`, `diff`, `log`, `branch`) MAY run freely.
- Proposed commits MUST stay small and focused: propose a commit after each meaningful change (schema done → propose, helper done → propose) rather than batching. Frequent small commits with human sign-off, not silent ones and not giant ones.
- MUST check the current branch before making changes; if it differs from what the task implies, ask which branch to use.
- MUST branch from an up-to-date base: `git fetch` first and check the local base is not behind its remote before creating a feature branch.
- Before merging a feature branch, MUST re-check where the default branch is — other sessions and worktrees move it while you work. If it moved, merge it into the feature branch first, resolve and re-verify there (tests, type-check, build), and only then merge into the default branch, so the default branch never holds a half-resolved state.
- Follow Git-flow by default: feature branches, merge commits (no squash), the default branch receives only merges. A repository's own `CLAUDE.md` wins where it differs.
- NEVER use `git add .` or add whole directories — add affected files individually; leave untracked files as they are.
- NEVER delete untracked files.
- NEVER push directly to a default branch; NEVER force-push.
- Commit messages MUST use a type prefix (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `ci:`) and SHOULD follow the house pattern `type: summary — key detail` (e.g. `feat: central log lifecycle — launch-time rotation, exclusive session routing`).
- NEVER add coding-agent attribution to commits (no Co-Authored-By, no session trailers, no model IDs).

## Documentation

- Every document MUST be self-sufficient: the reader should never need to hunt for context. Explain concepts inline; when a concept is defined in another checked-in document, reference it precisely (`see docs/PLANS.md § Milestones`), never vaguely ("see the architecture doc").
- MUST verify the actual implementation before writing API or usage documentation — NEVER guess names, parameters, or behavior.
- After changes that alter behavior or commands, MUST check the repo's README/docs and update them in the same change.

## ExecPlans and ADRs (project layer)

Projects persist cross-session knowledge in two layers: **ExecPlans** (immutable narrative logs of how a feature was built — the persistence layer for cross-session development) and **ADRs** (durable cross-plan decisions passing the three-gate test: hard to reverse, surprising without context, a real trade-off), with the project `CLAUDE.md` as an auditable index citing both.

- For complex features or significant refactors, MUST use an ExecPlan as described in the project's `PLANS.md`. If the repository has none, the canonical methodology is [`docs/PLANS.md`](docs/PLANS.md), deployed at `~/.claude/docs/PLANS.md` and readable from any project — MUST read it in full before drafting, rather than improvising a plan format. Before implementing or summarizing an ExecPlan, MUST read the full plan document and confirm understanding by listing its milestones.
- Layouts differ per repo (`docs/` vs `_docs/`; some repos have no ADR dir). MUST discover the project's actual convention before writing; if the scaffold is missing, offer to add it from the `Taka499/project-template` repository rather than inventing a layout (the `scaffold-project` skill does this for a repository that does not exist yet; for an existing one, copy in only the missing files from the same template archive).
- Decisions crystallised in conversation MUST be captured into their durable home the moment they crystallise (plan Decision Log, ADR, or nowhere if they pass no gate) — chat is ephemeral. The `/grill-me` and `/close-out` skills implement this routing.

## Quality Gates

Let machines enforce what code review used to catch — size, complexity, and type discipline are lint *errors*, not review comments. Per-toolchain configurations live in the stack notes.

- NEVER silence lint or type errors inline (`eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `#[allow]`, `# noqa`) — fix the root cause. A genuinely justified exception goes in the config file as an allowlist entry with its reason and its removal condition ("delete the entry when the reason goes away"); inline suppressions hide the exception inventory and can never be audited.
- Introduce a new strict rule as a warning, drain the existing backlog to zero, then ratchet it to error. NEVER add findings to a warning list nobody reads — a rule is either green-and-enforced or being actively drained.
- Decide gate vs report deliberately. A check with expected false positives (dead-code scans, duplication scans) runs as a non-blocking report; blocking on day one trains reflexive ignore-comments. Promote to a gate only once it is trustworthy.
- Every CI gate SHOULD state, in a comment at the top of its workflow, what it actually guards. A gate whose purpose cannot be written down is either unnecessary or mis-aimed.

## Testing

- Design for testability first: extract rules into pure functions in their own files, keep I/O at the call site, and pass dependencies (clock, paths, platform, processes) as arguments. Apply this to EXISTING code too — testability is a property of the codebase to actively restore, not a rule binding only new lines.
- New tests MUST be shown to fail when their target is broken (invert, delete the guard, or revert — watch red — restore).
- Full pattern checklist and doctrine → [`docs/testing.md`](docs/testing.md). Read before writing or refactoring tests.

## Debugging

- MUST diagnose the root cause before attempting fixes — NEVER quick-fix by hardcoding values or papering over symptoms.
- MUST check git history/diffs when investigating regressions.
- NEVER trust an error string as the only evidence; reproduce deterministically where possible.
- When trimming a command's output (`grep`, `tail`, `head`), MUST keep every warning and error line whose cause is not already documented — above all for dry runs, previews and deploys. A dry run whose warning was filtered away protects nothing: the one line that mattered is the one the filter dropped. A *named* diagnostic written down as benign MAY be filtered — `failed to store: 100001` on push, per the `Taka499/claude` repo's `plans/0006-sandbox-vs-agent-config-paths.md` § Separately. Suppressing a whole severity is not that: `… | grep "^error"` drops every warning including the ones nobody has classified yet, and it reports the *filter's* status rather than the command's — a failing build matches and exits 0 while a clean one exits 1, so the check is inverted as well as blind. A filter MUST name what it drops, and MUST let the command's own exit status through — redirect to a file and filter *that*, so `$?` is still the command's (`${PIPESTATUS[0]}` is bash-only: zsh leaves `PIPESTATUS` empty and spells it `${pipestatus[1]}`, indexed from 1, so the portable move is not to pipe). Filtering what you have explained is hygiene; filtering what you have not is how a deploy warning dies.

## Skills

Prefer these user-level skills over doing the work by hand:

- **Stress-test a plan or design before building** → `/grill-me`
- **Start a repository for an idea that has none yet** → `scaffold-project` (copies the `Taka499/project-template` scaffold, inits git, fills the CLAUDE.md overview, proposes the first commit)
- **Close out a completed ExecPlan** → `/close-out` (retrospective, ADR sweep, snapshot sync)
- **Design or restructure a module** → `codebase-design` (deep-module vocabulary; loads automatically when relevant)
- **Port a proven setup from a neighboring local repo** → `/adopt-from-sibling`
- **End-of-task capture of session learnings** → `/harvest-session`
- **Park an idea without building it** → `/backlog`
- **Second opinion on a diff before committing** → `/codex-review` (Codex reviews it read-only; note the diff and its context leave the machine)

## Stack Notes

Distilled cross-project lessons, extracted from real projects. MUST read the relevant note before non-trivial work in that stack; treat entries there as rules unless the project's `CLAUDE.md` overrides them.

- Rust (incl. Windows apps, egui, cargo/test gotchas) → [`docs/rust.md`](docs/rust.md)
- TypeScript / React / web frontends → [`docs/typescript.md`](docs/typescript.md)
- Python (uv, pipelines, testing) → [`docs/python.md`](docs/python.md)

## Continuous Learning

When something worth remembering is learned, MUST first choose the right destination:

- **Cross-project rules / workflows** → this file (`CLAUDE.md` in the `Taka499/claude` repo, via PR)
- **Stack-specific lessons** → the matching `docs/*.md` stack note (via PR)
- **Project-scoped rules or facts** → that project's `CLAUDE.md` / ADRs / plan Decision Log
- **Repeatable executable workflows** → a skill in `skills/`
- **Facts about the user or preferences not derivable from code** → file-based memory

A capture that changes shared guidance (a stack note, a rule here) MUST be additive while existing projects still follow the current guidance: add the new approach beside the old one with a criterion for choosing between them, and replace the old one only once nothing depends on it. A projects-wide rewrite through a documentation edit is scope creep, and the projects that followed the old text are left contradicting their own harness. This binds *alternatives*, not *corrections*: where guidance is wrong, unsafe, or contradicted by another rule, propose replacing it in place instead of preserving it beside the new text — subject to the confirmation requirement below, like any other capture — and say in the fix what changed and what a project still on the old text should do.

MUST confirm with the user before persisting anything. After completing a task, SHOULD review the session for corrections, redirections, or repeated instructions and propose captures — the `/harvest-session` skill runs this ritual on demand.

## Automation Proposals

When the same instruction or pattern is given 2+ times in a session, MUST recognize the repetition and propose automating it (rule here, skill, or script), explain the trade-offs, and let the user decide.
