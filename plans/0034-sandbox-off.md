# Plan: Turn the Bash sandbox off

## Goal

On 2026-10-30 the user asked to stop using Claude Code's Bash sandbox. Plan 0005 turned it on on 2026-08-25, and since then it had been in the way in many places. Measured across every session transcript on the machine (2026-06-13 to 2026-10-30; this repository's own transcripts before 2026-09-28 have already been deleted):

- 36,999 Bash calls, 1,462 of them run outside the sandbox, in 95 sessions. Each was a prompt, because `Bash(dangerouslyDisableSandbox:true)` sat in `permissions.ask`.
- The most frequent were `git fetch`, `push` and `merge`, `gh pr` and `gh run`, and gkms-contest-ai's worker scripts (`integrate.sh`, `spawn_worker.sh`).
- 255 tool results reported `Operation not permitted`.

Two options were offered. The user chose to turn the sandbox off. The other was to keep it and drop the ask rule, so that the auto-mode classifier would decide each unsandboxed retry.

## Changes

`~/.claude/settings.json` (untracked per ADR 0002):

- **`sandbox.enabled: false`.** The rest of the `sandbox` block stays, inert, so turning it back on means changing one key. Two projects have sandbox keys of their own (gkms-contest-ai, gkms-hif-final-stats), but neither sets `enabled`, so the user-level value applies everywhere.
- **`Bash(dangerouslyDisableSandbox:true)` removed from `permissions.ask`.** With no sandbox, no command is ever retried outside one.
- **`autoMode.allow`'s Codex entry rewritten.** It told the classifier that Claude Code's sandbox confines `codex exec --sandbox danger-full-access`. Left as it was, the classifier would have kept approving Codex with no sandbox around it at all. It now allows `--sandbox read-only` and says what that sandbox does and does not hold.

`skills/codex-review/SKILL.md`:

- Codex runs with its own `--sandbox read-only`. Seatbelt sandboxes cannot nest, which is why the skill used to turn Codex's sandbox off; with Claude Code's sandbox gone, Codex's can run.
- The snapshot and the step 4 write check stay. They do not depend on which sandbox is in force.
- The form this replaces, for the day Claude Code's sandbox comes back: `codex exec --sandbox danger-full-access`, run as an ordinary sandboxed command. It needed `chatgpt.com` and `auth.openai.com` in `sandbox.network.allowedDomains` and `~/.codex` in `sandbox.filesystem.allowWrite`, and `~/.codex/auth.json` must not be in `credentials.files`. The skill at commit `4c28f42` has the full section, with the probes that measured it.

`README.md`:

- § The one file this repo does not deploy opens with the sandbox being off.
- The bullets for entries that changed are corrected.
- § Git in this clone needs the sandbox turned off says it does not apply while the sandbox is off.

Global `CLAUDE.md` § Git Operations: the two bullets on working under the sandbox (`gh`; git commands) now apply only where the sandbox is on.

## What is lost

- **Secrets.** Bash can now read `~/.ssh`, `~/.aws`, `~/.config/gcloud`, `.env` files, `*.pem`, `*.key`, the token folders under `~/.config/gh-tokens` and the login keychain. The `Read(…)` deny rules still stop the Read tool. For Bash, the auto-mode classifier is the only check in auto mode; in any other mode it is a prompt.
- **Prompts outside auto mode.** `sandbox.autoAllowBashIfSandboxed` approved sandboxed commands with no prompt. In Manual mode, every Bash command not covered by `permissions.allow` now prompts.
- **Network.** There is no egress allowlist any more.
- **Writes.** Bash can write anywhere the user account can.
- **Codex's reads.** Whatever Codex reads can go to OpenAI, including the secrets above. Its own read-only mode refuses writes but confines no reads (plan 0008).
- **Per-project `gh` tokens.** Their isolation rested on the sandbox. Unsandboxed, `gh` uses the user's own keychain login, so the tokens are no longer used.

## Follow-ups, not done here

- **The two projects' `.claude/settings.local.json`.** In gkms-contest-ai and gkms-hif-final-stats, `GH_CONFIG_DIR`, `SSL_CERT_FILE` and the `sandbox.*` entries now buy nothing. `SSL_CERT_FILE` still costs something: it replaces the macOS trust store for every command run in those projects (README, the `SSL_CERT_FILE` bullet).
- **The tokens.** Revoke the ones under `~/.config/gh-tokens`, or keep them for the day the sandbox returns.
- **Docs not updated.** `docs/claude-code.md` and the skills that say "sandboxed" or "outside the sandbox" (`task-board`, `scaffold-project`, `explainer`) still describe working under the sandbox. Without one, they lead to no wrong action.

- **What still stops a secret read in Bash.** The permissions docs (read 2026-10-30) say `Read(…)` deny rules also apply to "file commands Claude Code recognizes in Bash, such as `cat`, `head`, `tail`, `sed`, and `tee`", and to redirection targets. Deny is evaluated before allow, so `Bash(cat:*)` in `permissions.allow` does not open `~/.ssh`. The rules do not reach "a Python or Node script that opens files itself", or `grep -r` run from the file's own folder. Whether `awk` counts as a recognised file command the docs do not say. Not measured: a decoy `.env` written for the test was refused before it ran.
- **`Bash(awk:*)` removed from `permissions.allow`,** by the user, the same day. awk reads any file (`awk 1 <file>`), writes any file (`print > "<path>"`) and runs any command (`system("…")`). The rule matches the start of the command, so any command wrapped in awk was approved with no prompt. In auto mode an allow rule resolves before the classifier. The docs do not say whether auto mode drops `Bash(awk:*)` as a "wildcarded interpreter". While the sandbox was on, it confined whatever awk ran. Now awk commands go to the classifier in auto mode and prompt in Manual mode. `Bash(sed -n:*)` stays: sed's `w` command writes files, but macOS sed cannot run commands, and the docs list sed among the commands the `Read(…)`/`Edit(…)` rules cover.

## Order of the settings edits

The deployed clone keeps the old skill until this branch is merged and the clone updated. So the `autoMode.allow` entry was narrowed first. A review run in the meantime with the old `--sandbox danger-full-access` is then judged by the classifier with no entry covering it, instead of being approved as confined. Then `sandbox.enabled` was set to `false`, then the ask rule removed.

## Verification

All on 2026-10-30, in the session that made the change; no restart was needed.

- **The setting took effect at once.** Inside the sandbox, `TMPDIR` is `/tmp/claude-501` and `ps` is refused (README, the `Bash(rm *)` bullet; `docs/claude-code.md` § Processes under the sandbox). Right after the change, `echo $TMPDIR` printed the login shell's `/var/folders/…/T/` and `ps -p $$` worked.
- **`settings.json` parses**, with `sandbox.enabled` false and no `Bash(dangerouslyDisableSandbox:true)` in `permissions.ask` (checked with `python3 -c 'json.load(…)'`).
- **Codex's read-only sandbox works unnested.** `codex exec --sandbox read-only -c 'approval_policy="never"'` (codex-cli 0.150.1), in a scratch git repository under `$TMPDIR`, ran three commands. `head -1 README.md` printed the line. `touch probe-write.txt` and `touch ~/codex-probe-write-outside.txt` both failed with `Operation not permitted`, and `ls` afterwards found neither file. In auto mode it ran with no prompt. Whether the new `autoMode.allow` entry or the classifier's own judgement passed it cannot be told from outside.
