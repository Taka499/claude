# Plan: Record why git breaks in this repo under the sandbox

## Goal

After PR #2 merged, a routine `git checkout master` in this clone half-completed: it moved `HEAD`, failed to unlink `CLAUDE.md` and `commands/*.md` with `Operation not permitted`, and left `docs/PLANS.md` truncated to the empty blob (`e69de29`). An ordinary command silently destroyed a tracked file's contents. This records the cause, because the next person to hit it will be a session with no memory of this one, mid-checkout, looking at a corrupted file.

## The cause

Claude Code hard-protects **agent-configuration paths** from writes by sandboxed Bash commands, and it resolves symlinks when doing so. Because ADR 0001 deploys `~/.claude/CLAUDE.md` and `~/.claude/commands` as symlinks into this repository, the protection lands on this repository's real paths. Measured in the working tree:

| Path | Sandboxed write | Why |
| --- | --- | --- |
| `CLAUDE.md` | **blocked** | `~/.claude/CLAUDE.md` resolves here |
| `commands/` | **blocked** | `~/.claude/commands` resolves here |
| `README.md`, `setup.sh`, `docs/`, `plans/` | writable | not agent-config paths |
| `skills/` | writable | `~/.claude/skills` is a real directory since ADR 0003, so it resolves to itself |

That last row is an accident of good fortune: before ADR 0003, `~/.claude/skills` was a symlink to `skills/`, so the whole directory would have been blocked too. Linking per skill removed a breakage nobody had noticed yet.

Git is not special-cased. When a checkout needs to rewrite `CLAUDE.md`, it gets `EPERM` mid-operation, and git's partial-failure behaviour is what corrupts files.

## What does not fix it

Both were tried, applied to `~/.claude/settings.json`, and re-tested after a full restart with `/sandbox` confirming they were loaded:

- **`sandbox.filesystem.allowWrite: ["~/Developer/claude"]`** — does not lift it. The protection behaves like a narrow deny inside a wider allow: the deny holds. Keep the entry anyway, since it is what makes this repo writable when the working directory is a *different* project (which `harvest-session` explicitly asks for), but do not expect it to help here.
- **`sandbox.excludedCommands: ["git", "gh"]`** — does not lift it either. Present in the resolved `/sandbox` config and still ineffective, which is the evidence that this guard is not configured by user sandbox settings at all.

Neither is a settings bug. The guard exists precisely so that a sandboxed command cannot rewrite the configuration that governs the next command, and this repo *is* that configuration.

## The operating rule

**Git operations in this clone that touch `CLAUDE.md` or `commands/` must run outside the sandbox** — `dangerouslyDisableSandbox: true` on the Bash call. That covers `checkout`, `switch`, `merge`, `pull`, `stash` and `restore`. Operations that touch only `docs/`, `plans/`, `skills/`, `README.md` or the setup scripts are fine sandboxed.

> Narrowed on 2026-08-29 by `plans/0007-codex-second-opinion.md`: that sentence is about *editing* those paths. **Running** `./setup.sh` is a separate case — it writes into `~/.claude/skills`, which is itself an agent-config path, so a run with a link to add or prune needs the sandbox off. A run where every link already exists succeeds sandboxed, which is why this stayed hidden until a skill was added.

If a checkout has already failed halfway, do not re-run it. Establish what the working tree actually holds first — compare with `git hash-object <file>` against `git rev-parse <ref>:<file>`, which needs no pipes, no temp files and no `diff` (all three are themselves restricted under the sandbox). The empty blob `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` means a file was truncated, not merely modified.

## Separately: `gh` cannot verify TLS under the sandbox

`gh` fails every API call with `x509: OSStatus -26276`. It is a Go binary that verifies certificates through the macOS keychain, which the sandbox blocks; `sandbox.network.allowedDomains` cannot fix a trust-store problem. Proven by contrast: `python3` reached `api.github.com` with HTTP 200 and `git ls-remote` succeeded over the same network in the same session. Run `gh` with `dangerouslyDisableSandbox: true`. The related `failed to store: 100001` on push is the same keychain block and is cosmetic — the push authenticates and completes.

## Verification

- Path map above produced by probing each path with a sandboxed write.
- `allowWrite` and `excludedCommands` re-tested after restart, with `/sandbox` Config confirming both were loaded; `CLAUDE.md` remained unwritable and `gh` still failed.
- Recovery from the corrupted state: stranded files moved aside rather than deleted, all four confirmed byte-identical to `origin/master` by object hash, then `git merge --ff-only` outside the sandbox. `docs/PLANS.md` restored to 159 lines; `./setup.sh` reports every link healthy; the repo checker passes with 0 failures.
