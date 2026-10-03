# Plan: Say up front that `gh` cannot run under the sandbox, and close the keychain read it exposed

## Goal

Under the Claude Code sandbox on macOS, every `gh` API call fails. Sessions keep finding this out the slow way: they try `gh` sandboxed, hit the failure, diagnose it (sometimes wrongly), and then retry with `dangerouslyDisableSandbox: true`. That retry is in `permissions.ask` (per `plans/0005-sandbox-as-the-security-layer.md`), so each wasted attempt ends in an approval prompt for the user. The only existing record, `plans/0006-sandbox-vs-agent-config-paths.md` § Separately, is a plan file, so sessions never load it, and it names the wrong cause. One rule in the global `CLAUDE.md` saves those wasted attempts, and a correction note fixes the record.

Proving that the keychain was not the cause showed something more serious. The login keychain was readable from inside the sandbox, and it holds Claude Code's own login plus two GitHub credentials. The existing denies on `GITHUB_TOKEN` and `~/.claude/.credentials.json` therefore protected nothing on macOS. That gap is now closed in `~/.claude/settings.json`, and the README records the entry as an invariant.

## Changes

- Global `CLAUDE.md` § Git Operations: one new bullet. Never try `gh` sandboxed first. It names the error, explains the misleading "token in keyring is invalid" message, says which setting would fix it and why that setting stays off, and gives the routes that do work: `git` / unauthenticated `curl` for reads, and single unsandboxed `gh` commands (announced) or hand-off to the user for writes. It also says that pushes and private HTTPS fetches go outside the sandbox where the keychain is denied.
- `~/.claude/settings.json` (untracked; edited by the user): `{"path": "~/Library/Keychains", "mode": "deny"}` added to `sandbox.credentials.files`.
- `README.md` § Deployment › The one file this repo does not deploy: a new invariant bullet for that entry, giving the reason, the measurement and the cost.
- `README.md` § Deployment › Git in this clone needs the sandbox turned off: the `gh` sentence said the cause was the keychain and grouped `gh` under "no `settings.json` change lifts either constraint". Both claims were wrong. The README is current documentation, not history, so the sentence is replaced in place with a short paragraph of its own.
- `plans/0006-sandbox-vs-agent-config-paths.md` § Separately: a dated correction note. The plan text itself is left unchanged, as `plans/0005` does for its own correction.

## Evidence (session 2026-10-03; gh 2.101.0, Claude Code 2.1.284, macOS 26.7.1)

Measured inside the sandbox:

- `gh api rate_limit` → `tls: failed to verify certificate: x509: OSStatus -26276`.
- `gh auth status` → `Failed to log in to github.com account … (keyring)`, `The token in keyring is invalid`.
- `gh auth token` → exit 0 and a 40-character token, so the keychain read works. (The token was captured into a variable and only its length printed.) The "invalid" verdict therefore comes from the API check that `auth status` makes, which fails on TLS like every other call.
- An earlier session the same day found that `curl` to `api.github.com` returns 200 and `git ls-remote` works, so the network allowlist is not the problem.

From the installed Claude Code binary, the settings schema for `sandbox.enableWeakerNetworkIsolation` reads: "macOS only: Allow access to com.apple.trustd.agent in the sandbox. Needed for Go-based CLI tools (gh, gcloud, terraform, etc.) to verify TLS certificates … **Reduces security** — opens a potential data exfiltration vector through the trustd service. Default: false".

### The keychain

Three credentials live in `~/Library/Keychains/login.keychain-db`, and before the fix a sandboxed command could read all of them:

| Item | Reader | How |
|---|---|---|
| `gh:github.com` | `gh` (zalando/go-keyring) | `/usr/bin/security` |
| `Claude Code-credentials` | Claude Code (binary: `security find-generic-password -a "$USER" -w -s "Claude Code-credentials"`) | `/usr/bin/security` |
| internet password `github.com` | git (`credential.helper osxkeychain`, from Xcode's system gitconfig) | `git-credential-osxkeychain` |

Measured values are lengths only. Each secret was captured into a variable or piped to `wc -c`, and its value was never printed.

| Check (inside the Claude sandbox) | Before the deny | After the deny |
|---|---|---|
| `gh auth token` | exit 0, 40 characters | exit 1, `no oauth token found for github.com` |
| `security … -s "Claude Code-credentials" -w` | exit 0, 523 characters | exit 44, `The specified item could not be found` |
| `git credential-osxkeychain get` for github.com | 114 bytes | 0 bytes |
| `curl https://api.github.com/zen` | 200 | 200 |
| `git ls-remote` of a public repository | works | works |

Before the user changed the settings, the same deny was tried in a standalone `sandbox-exec` profile (`(allow default)` plus `(deny file-read* (subpath "~/Library/Keychains"))`), run once outside the Claude sandbox because Seatbelt does not nest. It gave the same three failures and the same working `curl`. This shows the Security framework opens the keychain file inside the calling process, so a filesystem rule is enough to block it. Not measured: a sandboxed `git push` or private fetch failing. That is inferred from the helper returning nothing.

## Decision Log (session 2026-10-03)

- **Keep the sandbox strict and write a rule, rather than enabling the setting.** The user chose this. Enabling the setting would make `gh` work and the rule unnecessary, but it would also give sandboxed commands a channel out through trustd that `allowedDomains` does not control. The rule only costs one approval per real `gh` write.
- **Rule location: § Git Operations.** `gh` is the GitHub half of the same workflow, and a session about to open a PR is reading that section. Global rather than per project, because the sandbox settings are user-level (`~/.claude/settings.json`) and apply to every project on this machine.
- **The rule names its own off switch.** "If `gh` does work sandboxed, that setting is on and this rule does not apply" keeps the rule from going stale on a machine configured differently.
- **Correct plan 0006 with a note, don't rewrite it.** Plans are history; the correction-note pattern comes from plan 0005.
- **No ADR.** Prose guidance plus a settings choice that is easy to reverse, so it fails the first gate.
- **Close the keychain gap: `credentials.files` denies `~/Library/Keychains`.** The user added this to `~/.claude/settings.json`. Before the change, the login keychain was readable from inside the sandbox, so `sandbox.credentials.envVars` denying `GITHUB_TOKEN` and `credentials.files` denying `~/.claude/.credentials.json` protected nothing on macOS. See Evidence § The keychain. The cost is that git over HTTPS loses its credential inside the sandbox, so pushes and fetches from private repositories run outside it. That is accepted because the alternative exposes Claude Code's own login. The new README bullet records this entry as the deliberate exception to "do not deny a credential belonging to a tool you run sandboxed".

## Verification

- The three measurements above were made in this session. TLS was not re-tested with `enableWeakerNetworkIsolation` turned on, because the setting stays off. The trustd attribution rests on the schema text and on the keychain read succeeding.
- Prose only: no test to run. After merge, read § Git Operations once through `~/.claude` (symlinked) to confirm the bullet deploys.
