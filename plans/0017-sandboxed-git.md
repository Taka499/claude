# Plan: Say which git writes run sandboxed, and that approval comes from `ask` rules, not from leaving the sandbox

## Goal

A session that believes "the sandbox blocks writes to `.git`" runs every git write with `dangerouslyDisableSandbox: true`. Here that retry is in `permissions.ask` (per `plans/0005-sandbox-as-the-security-layer.md`), so each `git add` becomes an approval prompt for the user, even though staging changes nothing in history. The belief is wrong for `add` and `commit`, which write only inside `.git`, where the sandbox denies just `hooks/` and `config`. It is right for some other git commands: those that write `.git/config`, and those that rewrite a protected working-tree path. One rule in the global `CLAUDE.md` says which is which.

Moving git into the sandbox has a cost the rule must name. Some commands were prompting only because they ran unsandboxed. Once they run sandboxed, any history-mutating command without its own `ask` rule runs with no prompt at all. `git merge` is one: `permissions.ask` has `git commit *` and `git push *`, but nothing for merge.

## Changes

- Global `CLAUDE.md` § Git Operations: one new bullet after the `gh` bullet. It covers four things:
  - **Sandboxed:** run `git add` and `git commit` inside the sandbox, and why that works (what the sandbox denies inside `.git` and in the working tree).
  - **Unsandboxed:** run these outside it, each on its own:
    - writes to `.git/config`;
    - `merge`, `checkout`, `switch`, `pull`, `stash` and `restore` when the change touches a protected path;
    - `git worktree add` to a directory outside the working directory.
  - **Prompts:** a content-scoped `ask` rule still prompts for a sandboxed command, and a git command without one does not.
  - **Source:** the project it came from, named bare with the date and Claude Code version, as § Continuous Learning requires.
- `README.md`: no change. § Deployment › Git in this clone needs the sandbox turned off already says the same for this clone. Here `CLAUDE.md` and `commands/` are what `~/.claude` links to, so they are protected paths.
- `~/.claude/settings.json` (untracked, the user's to edit; ADR 0002): recommended, not part of this change:
  - **`"Bash(git merge *)"` in `permissions.ask`**, so merges keep a prompt when they run sandboxed. That already happens for merges in a linked worktree that touch no protected path.
  - **Optionally, `"Bash(git branch -D *)"`.** The allow rule `Bash(git branch *)` also approves force-deleting a branch, and an `ask` rule takes precedence over it.

## Evidence (session 2026-10-12; Claude Code 2.1.296, git 2.50.1, macOS 26.7.1)

**The belief and its cost (gkms-contest-ai).**
- The project's `/coordinate` command says: "`.git` writes (branch, commit, merge, worktree) and writes outside this checkout are blocked by the sandbox: run each such git command on its own with the sandbox disabled" (`.claude/commands/coordinate.md:38`).
- Across the coordinating session's transcript (2026-10-07 to 2026-10-11), all 9 Bash commands that staged files with `git add` ran unsandboxed. Most were chained to a `git commit`. One, at 2026-10-11 13:58 JST, was `git add CLAUDE.md && git status --short`: an approval prompt only to stage one file.

**Sandboxed git works in linked worktrees.** The same project's worker sessions staged and committed with the sandbox on, using `git add <files> && git commit`:
- 93683ad, 8f486ed and d960aca on `feature/b11-per-turn-charge`;
- 40dfa44 on `feature/sense-anomaly-engine`.

**Sandboxed git works in a main checkout.** Probe in this clone, with the sandbox on:
- Opening each file for append without writing anything succeeded for `.git/index`, `.git/HEAD`, `.git/refs/heads/master` and `.git/logs/HEAD`.
- `.git/config` failed with `PermissionError: Operation not permitted`.
- `.git/hooks` reported not writable.
- Then the real case: ade8d11 (PR #22) was staged and committed with the sandbox on, with `git add CLAUDE.md README.md && git commit`. `CLAUDE.md` is a protected path in this clone, but `add` and `commit` only read it.

**The Claude Code documentation** (https://code.claude.com/docs/en/sandboxing, read 2026-10-12):
- § Protected paths lists, "in your working directory and the directories above it", the `.claude` settings files, `.claude/skills`, `agents`, `commands` and `hooks`, `.mcp.json` and the files Claude Code runs on its own. It lists, "in your working directory only", the shell startup files, `.gitconfig`, `.vscode`, `.idea`, "and `hooks` and `config` inside `.git`".
- § Protected paths also says: "If a symlink appears at a protected settings file's path during the session, the sandbox also denies writes to the file it points to".
- § Filesystem isolation, Git worktrees: "the sandbox also allows writes to the main repository's shared `.git` directory so commands such as `git commit` can update refs and the index. Writes to `hooks/` and `config` inside that directory remain denied."
- § Sandbox modes, Auto-allow mode: "Content-scoped ask rules like `Bash(git push *)` still force a prompt even for sandboxed commands". And: "An allow rule that matches a command also approves an unsandboxed retry of it".
- § Protected paths points to a troubleshooting entry for "`git merge` or `git checkout` fails with `unable to unlink old` on one of these paths".

**Partial failures (this repo, earlier).** Both are recorded in `plans/0006-sandbox-vs-agent-config-paths.md` and README § Git in this clone:
- A sandboxed `git branch -d` deletes the ref, fails to remove its `[branch "…"]` section and still reports `Deleted branch`.
- A sandboxed `git checkout` that had to rewrite a protected file left `docs/PLANS.md` at zero bytes.

## Decision Log (session 2026-10-12)

- **A global rule, beside the `gh` bullet.** The wrong belief appeared in one project, but the sandbox and its protected paths are the same in every project on this machine, and a session about to commit is reading § Git Operations.
- **Name the unsandboxed cases, not only "add and commit are fine".** A session told just "git works sandboxed" would also move merges and branch deletions into the sandbox, where they fail halfway. Those are the two failure modes this repo has already paid for.
- **Approval belongs to `ask` rules.** Running unsandboxed was giving a prompt as a side effect. The user's rule "NEVER run `git commit`, `git push`, `git merge`, `git rebase` … without explicit user permission" needs the settings to enforce it directly, whether or not the command is sandboxed.
- **Settings are left to the user.** `settings.json` is untracked (ADR 0002), and the sandbox denies sessions writing it.
- **No ADR.** It is prose guidance and easy to reverse, so it fails the first gate.

## Verification

- The probe and commit ade8d11 above were made in this session.
- Not re-run here: a sandboxed merge that touches a protected path, and a sandboxed `git branch -d`. Both rest on the documentation and on plan 0006's measurements.
- The gkms main checkout was not probed, because this session's sandbox cannot write there. The claim for it rests on the documentation and on this clone, which has the same settings.
- Prose only: there is no test to run. After merge, read § Git Operations once through `~/.claude` (symlinked) to confirm the bullet deploys.
