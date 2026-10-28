# Plan: Let a project run `gh` sandboxed, with a token of its own

## Goal

Plan 0016 kept `gh` outside the Claude Code sandbox for two reasons:
- TLS: Go on macOS verifies certificates through the `com.apple.trustd.agent` service, which the sandbox blocks;
- the token: `credentials.files` denies `~/Library/Keychains`, where `gh` keeps the user's login.

So every `gh` call is an unsandboxed command, and each one asks. On 2026-10-28 the user decided to open `gh` inside the sandbox, because it "blocks in many places these weeks". The occasion was gkms-contest-ai: an assessment of its coordination recommended a structured task store, and GitHub Issues fits it once `gh` runs sandboxed.

This plan meets both reasons without what plan 0016 rejected:
- TLS is lifted by `SSL_CERT_FILE`, with `sandbox.enableWeakerNetworkIsolation` still off;
- the token is a narrow one per project, not the user's login.

The keychain deny stays.

## Design

- **TLS, for every project.** `SSL_CERT_FILE=/etc/ssl/cert.pem` makes Go check certificates against the file macOS ships, without trustd.
  - The user set it in `env` of `~/.claude/settings.json` on 2026-10-28, during this session.
  - On its own it gives no access: `gh` without a token still fails, now on authentication rather than TLS.
  - `enableWeakerNetworkIsolation` stays off: it opens trustd as an outbound channel the domain allowlist does not cover.
- **The token, per project and opt-in.** A project that wants `gh` sandboxed sets one variable in `env` of its own `.claude/settings.local.json`:

  ```json
  "env": {
    "GH_CONFIG_DIR": "/Users/<user>/.config/gh-<owner>"
  }
  ```

  The folder holds `gh`'s `hosts.yml` with a fine-grained token in plain text. Since v2.1.211 that settings file loads from the main checkout for worktree sessions too (`docs/claude-code.md` § Code that runs outside the sandbox), so a project's workers get the same setting.
- **The token's scope:**
  - one resource owner, and only that project's private repositories;
  - Issues write, Pull requests write, Contents read, Metadata read, nothing else;
  - an expiry.

  Without Contents write it can neither push nor merge: GitHub's permission table puts the merge endpoint under Contents write. With no public repository in scope, whatever a session posts stays private.
- **Outside every session's write area.** `gh` reads aliases from `config.yml` in that folder, and an alias can run a shell command. A session that could write the folder could plant one, and the next `gh` run outside the sandbox would execute it. `~/.config` is outside every `allowWrite` on this machine. The same rule as `docs/claude-code.md` § Code that runs outside the sandbox.
- **Inside an opted-in project, every `gh` call uses that token,** sandboxed or not, because a settings `env` applies to every command. Anything beyond it goes to the user, or runs as a single unsandboxed command with `GH_CONFIG_DIR=$HOME/.config/gh` before it, which asks. That covers repository settings, deploy keys, and a merge through `gh`.
- **Every other project is unchanged:** `gh` runs outside the sandbox with the keychain login, and each call asks.

## Changes

- Global `CLAUDE.md` § Git Operations, the `gh` bullet:
  - **Corrected in place.** It said `gh` "cannot work" sandboxed and that running it there "would take" `enableWeakerNetworkIsolation`. Both are wrong now, so this is a correction, not an alternative, per § Continuous Learning.
  - **Added beside it:** the opt-in. The default stays for every project that does not opt in.
- `README.md`:
  - § Git in this clone needs the sandbox turned off: the `gh` paragraph, corrected the same way;
  - § The one file this repo does not deploy: the counter-case sentence in the credential bullet, plus two new bullets, one for `SSL_CERT_FILE` in `env` and one for the per-project token.
- `plans/0016-gh-sandbox-tls.md`: a dated correction note, the way plan 0006 got one. The plan itself stays as written.
- Not in this repository:
  - the token, created by the user;
  - gkms-contest-ai's `.claude/settings.local.json`, a protected path the user edits;
  - that project's own texts and its move to Issues, which go through its own loop.

## Evidence (2026-10-28; gh 2.103.0, Claude Code 2.1.312, macOS 26.7.1)

All `gh` runs used a dummy token, so no credential was sent.

- **TLS, inside the sandbox:**
  - `GH_TOKEN=<dummy> gh api rate_limit` failed with `tls: failed to verify certificate: x509: OSStatus -26276`;
  - the same with `SSL_CERT_FILE=/etc/ssl/cert.pem` got `401 Bad credentials` from GitHub, so the certificate was verified.
- **A token file, inside the sandbox.** A temporary `GH_CONFIG_DIR` whose `hosts.yml` held a dummy `oauth_token` gave `401`. So `gh` reads the file there, with the keychain denied.
- **The file comes before the keychain, outside the sandbox too.** The same folder, one unsandboxed command:
  - `gh api user` gave `401`;
  - `gh auth status` named the file as the token's source ("The token in …/hosts.yml is invalid").

  The keychain holds a valid login for the same account, so `gh` takes a token from the file first. That rules out keeping the narrow token in the default `~/.config/gh`, or in a user-level `GH_CONFIG_DIR`: every `gh` call in every project would then use it. That would include this repository's PRs on the public `Taka499/claude`, which a token owned by `tia-tools` cannot reach. A fine-grained token has one resource owner, so one token could not cover both owners anyway.
- **Other tools with the variable set, inside the sandbox:**
  - `curl` to `api.github.com`: 200;
  - `git ls-remote` over HTTPS: works;
  - Python 3.14's `urllib`: 200;
  - `uv` 0.13.4 resolved a package.

  `/etc/ssl/cert.pem` holds 128 certificates, dated 2026-09-25, and macOS updates it.
- **GitHub's permission table for fine-grained tokens** (docs.github.com, § Permissions required for fine-grained personal access tokens, read 2026-10-28):
  - merging a PR (`PUT …/pulls/{n}/merge`) needs Contents write;
  - opening one (`POST …/pulls`) needs Pull requests write;
  - opening an issue (`POST …/issues`) needs Issues write.
- **Visibility,** checked with unauthenticated `curl`: `tia-tools/gkms-contest-ai` gives 404, so it is private; `Taka499/claude` gives 200, so it is public.
- **`gh` and the current settings.** `~/.claude/settings.json` holds no `Bash(gh …)` rule. `credentials.envVars` unsets `GITHUB_TOKEN` in sandboxed commands; `GH_TOKEN` and `GH_CONFIG_DIR` are not touched.
- **A settings `env` reaches both kinds of command.** After the user added `SSL_CERT_FILE` to `~/.claude/settings.json` (modified 19:49:55), a sandboxed command in this running session had it, and so did an unsandboxed one at 20:10. So a project's `GH_CONFIG_DIR` also applies to `gh` run outside the sandbox there.
- **Without a token, after the change.** Sandboxed, in this repository, with no `GH_CONFIG_DIR`:
  - `gh api user` gets `401 Requires authentication`;
  - `gh auth status` says "The token in default is invalid".

  TLS works, the login stays out of reach, and the rule for projects that have not opted in stands.

## Decision Log (session 2026-10-28)

- **Open `gh` in the sandbox, for gkms-contest-ai first.** The user's decision, after the assessment's recommendation of a structured task store.
- **`SSL_CERT_FILE`, not `enableWeakerNetworkIsolation`.** It lifts the TLS failure for `gh` without opening trustd to every sandboxed command.
- **`SSL_CERT_FILE` for every project, not per project.** The user set it user-wide. The tools measured still connect with it, and without a token it opens nothing.
- **Per project, not user-level,** because of the token-file order measured above.
- **Accepted:**
  - every sandboxed command in an opted-in project can read the token and use it within its scope, Codex included, and Codex may send what it reads to OpenAI;
  - in such a project, `gh` calls that run sandboxed stop asking.

  No `ask` rule is added. The token cannot push, merge or reach another repository, and edits to issues and PRs in a private repository are visible and can be undone.
- **The project token is not git's credential.** Pushes and private fetches keep their path outside the sandbox.
- **No ADR.** Deleting the token and two `env` lines reverses it, so it fails gate one (hard to reverse).

## Verification

- After the user's steps, sandboxed, with `GH_CONFIG_DIR` given on the command line:
  - `gh auth status` names the project folder;
  - `gh issue list -R tia-tools/gkms-contest-ai --limit 1` works;
  - a repository outside the token's scope is refused.
- In a fresh gkms-contest-ai session, sandboxed `gh issue list` works with no variables given.
- Elsewhere: in this repository, sandboxed `gh` still fails as before, and unsandboxed `gh auth status` still names the keychain.
