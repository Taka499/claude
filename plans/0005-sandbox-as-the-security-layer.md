# Plan: Move secret protection from `permissions.deny` to the sandbox

## Goal

`permissions.deny` carried `Bash(cat *)`, `Bash(head *)`, `Bash(tail *)`, `Bash(grep *)` and `Bash(find *)`, which read as a defence of the `Read(**/.env)` / `Read(~/.ssh/**)` rules — those bind the Read tool only, so `cat ~/.ssh/id_rsa` bypasses them entirely. But a `Bash(...)` rule can only match command strings, and `sed -n p`, `awk`, `python3 -c`, `rg`, `less`, `xxd` and `dd` all read files while matching none of them. The list implied a protection it could not deliver. Claude Code's sandbox enforces filesystem rules at the OS level for every Bash command and its child processes, which is the same job done in a layer that can actually do it.

## Changes

All in the untracked `~/.claude/settings.json` (per ADR 0002 it is not deployed from here; the invariants live in `README.md` § The one file this repo does not deploy, updated in this change):

- **Added `sandbox`** — `enabled: true`; `credentials.files` denying `~/.ssh`, `~/.aws`, `~/.config/gcloud` and `~/.claude/.credentials.json`; `filesystem.denyRead` covering `~/**/.env`, `~/**/.env.*`, `~/**/*.pem`, `~/**/*.key`, `~/**/secrets/**`.
- **Removed** `Bash(cat *)`, `Bash(head *)`, `Bash(tail *)` from `permissions.deny` — leaky as security, and they also caught `cat > file <<'EOF'`, which is a *write*; deny beats allow, so that false positive could not be carved back out with an allow rule.
- **Kept** `Bash(grep *)` and `Bash(find *)` as an explicit tooling preference, and the `Read(…)` secret denies, which cover the tool path the sandbox does not.
- **Added** `Bash(dangerouslyDisableSandbox:true)` to `permissions.ask`, so an unsandboxed retry is a decision rather than something the auto-mode classifier settles.

## Decision Log (session 2026-08-25)

- **Security in the enforcing layer, preferences in the nudging tier.** The split is the whole point: `deny` is the strongest tier available and was being spent on a control that leaked, while the leak-free control went unused. A future session tempted to re-add `cat` to `deny` should read this first — it buys nothing the sandbox does not already cover, and costs heredoc writes.
- **`grep`/`find` deliberately left at `deny` though they are only a preference.** Inconsistent with the paragraph above, and knowingly so: they are harmless to lose and the dedicated tools are better. Recorded rather than quietly rationalised — `ask` is the honest tier if the friction ever bites.
- **No ADR written.** The reasoning has one home in `README.md`; the repo's ADR convention warns against redundancy with rule text, and this is a settings-content decision rather than a harness-architecture one. Revisit if it starts getting re-litigated.
- **Native Windows has no sandbox** (macOS/Linux/WSL2 only). This config is therefore not portable as a security posture, and the README says so rather than leaving a Windows machine silently less protected than it looks.

## Verification

Run against a **decoy**, never a real secret: if a rule is not enforcing, a test against a real key prints key material into the transcript — the exact failure being tested for.

- **Control**: `sed -n 1p <repo>/LICENSE` → prints `MIT License`, proving `sed` works and any failure below is the rule, not the tool.
- **`filesystem.denyRead`**: a decoy `~/sandbox-check/.env` containing `SANDBOX_TEST=not-a-secret…`, written with the Write tool, then read with `sed` → `sed: …/.env: Operation not permitted`. A binary that was never in the Bash denylist, blocked.
- **`credentials.files`**: `~/.claude/.credentials.json` read via both `sed` and `python3`, output redirected to `/dev/null` so nothing could leak either way → both blocked.
- **Took effect without a restart**: all of the above ran in the session that enabled it.
- **Write isolation**: `rm -rf ~/sandbox-check` failed from inside the sandbox (outside the working directory) and succeeded only via `dangerouslyDisableSandbox`, confirming the boundary applies to writes as well as reads.
- **`cat` restored**: `cat <repo>/.git/HEAD` runs again.
