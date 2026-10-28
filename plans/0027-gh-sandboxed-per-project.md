# Plan: Let a project run `gh` sandboxed, with a token of its own

## Goal

Plan 0016 kept `gh` outside the Claude Code sandbox for two reasons:
- TLS: Go on macOS verifies certificates through the `com.apple.trustd.agent` service, which the sandbox blocks;
- the token: `credentials.files` denies `~/Library/Keychains`, where `gh` keeps the user's login.

So every `gh` call is an unsandboxed command, and each one asks. On 2026-10-28 the user decided to open `gh` inside the sandbox, because it "blocks in many places these weeks". The occasion was gkms-contest-ai: an assessment of its coordination recommended a structured task store, and GitHub Issues fits it once `gh` runs sandboxed.

This plan meets both reasons without what plan 0016 rejected, and only in a project that opts in:
- TLS is lifted by `SSL_CERT_FILE`, with `sandbox.enableWeakerNetworkIsolation` still off;
- the token is a narrow one of the project's own, not the user's login.

The keychain deny stays.

## Design

- **Opt-in, per project.** A project that wants `gh` sandboxed sets two variables in `env` of its own `.claude/settings.local.json`:

  ```json
  "env": {
    "GH_CONFIG_DIR": "/Users/<user>/.config/gh-<owner>",
    "SSL_CERT_FILE": "/etc/ssl/cert.pem"
  }
  ```

  Since v2.1.211 that settings file loads from the main checkout for worktree sessions too (`docs/claude-code.md` § Code that runs outside the sandbox), so a project's workers get the same setting.
- **TLS.** `SSL_CERT_FILE` makes Go check certificates against the file macOS ships, without trustd.
  - **Why only in the opted-in project:** wherever the variable is set, every program that honours it uses that file instead of the macOS trust store, outside the sandbox too. That affects Go programs, OpenSSL-based tools, Python and `uv` among them. A root trusted only in the keychain is then refused, and Go skips the platform verifier's checks, revocation included. Only a project with a token gains anything from it.
  - `enableWeakerNetworkIsolation` stays off: it opens trustd as an outbound channel the domain allowlist does not cover.
- **The token.** `GH_CONFIG_DIR` names a folder holding `gh`'s `hosts.yml`, with a fine-grained token in plain text. Its scope:
  - one resource owner, and only that project's private repositories;
  - only the permissions the project's use needs. For an issue tracker: Issues read and write, and Metadata read, which GitHub always adds;
  - never Contents write: GitHub's permission table puts merging a PR under it, and git needs it to push;
  - an expiry.
- **What the token can do,** and what every sandboxed command in the project can therefore do. Per GitHub's permission table:
  - **Issues write:** open, edit, close, reopen and lock issues, and edit or delete comments. A deleted comment cannot be restored.
  - **Pull requests write, if a project adds it:** open PRs, submit, approve, dismiss or delete reviews, and update a PR's branch from its base (`PUT …/update-branch`). The last one writes a merge commit on a branch, despite Contents being read-only.
  - **Not:** push, merge, or write to a repository outside the token's scope. Public repositories it can read, as anyone can without a token.
- **The folder sits outside every session's write area.** `gh` reads aliases from `config.yml` in that folder, and an alias starting with `!` runs a shell command. A session that could write the folder could plant one, and the next `gh` run outside the sandbox would execute it. `~/.config` is outside every `allowWrite` on this machine, the user's and gkms-contest-ai's. The same rule as `docs/claude-code.md` § Code that runs outside the sandbox.
- **Inside an opted-in project, only sandboxed `gh` calls use that token.** A settings `env` applies to every command, so `GH_CONFIG_DIR` reaches unsandboxed `gh` too. But `gh auth login --insecure-storage` files the token under the account, and `gh` reads that after the keychain. So outside the sandbox `gh` still uses the user's login, as in every other project, and each call asks. That is where anything beyond the token goes: repository settings, deploy keys, a merge through `gh`. A token written at the top level of `hosts.yml` would come before the keychain instead (§ Evidence), so store it with the login command, not by hand.
- **Every other project is unchanged:** `gh` runs outside the sandbox with the keychain login, and each call asks.

## Changes

- Global `CLAUDE.md` § Git Operations, the `gh` bullet:
  - **Corrected in place.** It said `gh` "cannot work" sandboxed and that running it there "would take" `enableWeakerNetworkIsolation`. Both are wrong now, so this is a correction, not an alternative, per § Continuous Learning.
  - **Added beside it:** the opt-in. The default stays for every project that does not opt in.
- `README.md`:
  - § Git in this clone needs the sandbox turned off: the `gh` paragraph, corrected the same way;
  - § The one file this repo does not deploy:
    - the counter-case sentence in the credential bullet;
    - a new bullet keeping `SSL_CERT_FILE` out of `~/.claude/settings.json`;
    - a new bullet for the per-project token.
- `skills/scaffold-project/SKILL.md` step 7: "`gh` cannot run inside it" now says a new repository is in no project token's scope.
- `plans/0016-gh-sandbox-tls.md`: a dated correction note, the way plan 0006 got one. The plan itself stays as written.
- Not in this repository:
  - the token, created by the user;
  - the user's `~/.claude/settings.json`, which held `SSL_CERT_FILE` during this session;
  - gkms-contest-ai's `.claude/settings.local.json`, a protected path the user edits;
  - that project's own texts and its move to Issues, which go through its own loop.

## Evidence (2026-10-28; gh 2.103.0, Claude Code 2.1.312, macOS 26.7.1)

All `gh` runs used a dummy token, so no credential was sent.

- **TLS, inside the sandbox:**
  - `GH_TOKEN=<dummy> gh api rate_limit` failed with `tls: failed to verify certificate: x509: OSStatus -26276`;
  - the same with `SSL_CERT_FILE=/etc/ssl/cert.pem` got `401 Bad credentials` from GitHub, so the certificate was verified.
- **A token file, inside the sandbox.** A temporary `GH_CONFIG_DIR` whose `hosts.yml` held a dummy `oauth_token` gave `401`. So `gh` reads the file there, with the keychain denied.
- **A top-level token comes before the keychain, outside the sandbox too.** The dummy file held `oauth_token:` both at the top level under `github.com:` and under `users: Taka499:`. One unsandboxed command with that folder:
  - `gh api user` gave `401`;
  - `gh auth status` named the file as the token's source ("The token in …/hosts.yml is invalid").

  The keychain holds a valid login for the same account, so `gh` took the file's top-level token first. That rules out a token at the top level of the default `~/.config/gh`, or of a user-level `GH_CONFIG_DIR`: every `gh` call in every project would then use it. That would include this repository's PRs on the public `Taka499/claude`, which a token owned by `tia-tools` cannot write to. A fine-grained token has one resource owner, so one token could not cover both owners anyway.
- **A token under the account comes after the keychain.** `gh auth login --insecure-storage --with-token` (run by the user at 20:58) wrote the token only under `users: Taka499:`, with no top-level `oauth_token:`. With `GH_CONFIG_DIR` pointing there:
  - **Outside the sandbox:** `gh auth status` said "Logged in to github.com account Taka499 (keyring)", with the full login's scopes (`repo`, `gist`, `read:org`, `admin:public_key`), and `gh api user` returned the login.
  - **Inside the sandbox:** `gh auth status` named the file as the source.

  So in an opted-in project, the narrow token serves only sandboxed calls.
- **The first token stored was rejected by GitHub,** on every route: `401 Bad credentials` from `gh` inside the sandbox, and from `curl` both inside and outside it. `curl` got the token on stdin, so it never appeared in a process listing. Inside the sandbox, `curl` showed a `CONNECT` tunnel through the sandbox's proxy and GitHub's own certificate (`CN=*.github.com`, issued by Sectigo), so the proxy does not intercept or change the request. The stored value had a token's shape (93 characters, `github_pat_` prefix, no whitespace). The fault was the token, not the sandbox. The user had deleted it on GitHub right after pasting it into the shell by mistake: `--with-token` waits on stdin without a prompt. The replacement was stored with `pbpaste | … gh auth login …`, so it was never typed or pasted into a terminal.
- **Other tools with `SSL_CERT_FILE` set, inside the sandbox:**
  - `curl` to `api.github.com`: 200;
  - `git ls-remote` over HTTPS: works;
  - Python 3.14's `urllib`: 200;
  - `uv` 0.13.4 resolved a package.

  `/etc/ssl/cert.pem` holds 128 certificates, dated 2026-09-25, and macOS updates it.
- **This machine's trust store.** `/Library/Keychains/System.keychain` holds three items, all Apple's defaults (`com.apple.systemdefault`, `com.apple.kerberos.kdc`, Apple Worldwide Developer Relations Certification Authority), so no admin-installed root. `security dump-trust-settings`, admin and user, could not run inside the sandbox ("No keychain is available"), so user trust settings are unknown.
- **GitHub's permission table for fine-grained tokens** (docs.github.com, § Permissions required for fine-grained personal access tokens, read 2026-10-28):
  - **Contents write:** `PUT …/pulls/{n}/merge`;
  - **Pull requests write:** `POST …/pulls`, `PUT …/pulls/{n}/update-branch`, `POST …/pulls/{n}/reviews`, `DELETE …/pulls/{n}/reviews/{id}`, `PUT …/reviews/{id}/dismissals`;
  - **Issues write:** `POST …/issues`, `PATCH …/issues/{n}`, `PUT …/issues/{n}/lock`, `DELETE …/issues/comments/{id}`;
  - deleting an issue is listed under no permission.
- **Visibility,** checked with unauthenticated `curl`: `tia-tools/gkms-contest-ai` gives 404, so it is private; `Taka499/claude` gives 200, so it is public.
- **`gh` and the current settings.** `~/.claude/settings.json` holds no `Bash(gh …)` rule. `credentials.envVars` unsets `GITHUB_TOKEN` in sandboxed commands; `GH_TOKEN` and `GH_CONFIG_DIR` are not touched.
- **A settings `env` reaches both kinds of command.** The user added `SSL_CERT_FILE` to `~/.claude/settings.json` during this session (modified 19:49:55). After that, a sandboxed command in this running session had it, and so did an unsandboxed one at 20:10. So a project's `GH_CONFIG_DIR` also applies to `gh` run outside the sandbox there.
- **TLS lifted, no token.** Sandboxed, in this repository, with no `GH_CONFIG_DIR`:
  - `gh api user` gets `401 Requires authentication`;
  - `gh auth status` says "The token in default is invalid".

  The login stays out of reach.

- **The working setup, verified from the sandbox** with `GH_CONFIG_DIR` and `SSL_CERT_FILE` given on the command line, after the user replaced the first token (stored 21:10):
  - `gh auth status`: "Logged in to github.com account Taka499 (…/gh-tia-tools/hosts.yml)";
  - `gh api user`: `Taka499`;
  - `gh issue list -R tia-tools/gkms-contest-ai`: exit 0, and the repository reports `private: true`, `has_issues: true`;
  - reading `contents/README.md` there: 403, "Resource not accessible by personal access token";
  - a title-less `POST …/issues`, which creates nothing whatever the outcome: 422 "title wasn't supplied" in `tia-tools/gkms-contest-ai`, so the write permission holds, and 403 in the public `tia-tools/releases`, outside the token;
  - `gh repo list tia-tools` showed the selected private repository and the owner's two public ones, which any token can read;
  - in this repository, with both variables unset, `gh api user` fails on TLS as before.

  The settings ended as designed: `~/.claude/settings.json` `env` holds no `SSL_CERT_FILE`, and gkms-contest-ai's `.claude/settings.local.json` `env` holds both variables. A running session keeps a variable removed from the settings until it restarts: this one still had `SSL_CERT_FILE`.

## Decision Log (session 2026-10-28)

- **Open `gh` in the sandbox, for gkms-contest-ai first.** The user's decision, after the assessment's recommendation of a structured task store.
- **`SSL_CERT_FILE`, not `enableWeakerNetworkIsolation`.** It lifts the TLS failure for `gh` without opening trustd to every sandboxed command.
- **`SSL_CERT_FILE` per project, not user-wide.** The user set it in `~/.claude/settings.json`, following this session's first proposal. Codex's review then pointed out that it replaces the macOS trust store for every program that honours it, in every command. No admin-installed root was found, but only an opted-in project gains anything from it. So it moves into the project's settings, beside `GH_CONFIG_DIR`, and the user removes it from `~/.claude/settings.json`.
- **Per project, not user-level.**
  - A user-level `GH_CONFIG_DIR` would put the token within reach of every project's sandboxed commands, and a fine-grained token serves only one owner's repositories.
  - Stored at the top level, it would also replace the user's login in every `gh` call (§ Evidence).
- **Stored with `gh auth login --insecure-storage`, not written by hand.** The login command files the token under the account, after the keychain in `gh`'s order, so only sandboxed calls use it. This rests on `gh`'s current behaviour, measured with 2.103.0, not on documentation. If a later `gh` reorders it, unsandboxed calls in the project would use the narrow token: the token's scope would bound them, and calls beyond it would fail rather than do more.
  - **Not chosen:** giving the variable on each command (`GH_CONFIG_DIR=… gh …`) would also isolate the token. Every call would need the prefix, though, and an allow rule does not match past an unknown variable assignment.
- **Least privilege.** The first proposal gave Pull requests write and Contents read. gkms-contest-ai merges locally and needs only issues, so its token gets Issues and Metadata only. Pull requests write adds approving, dismissing and deleting reviews, and updating a PR's branch.
- **Accepted:**
  - every sandboxed command in an opted-in project can read the token and use it within its scope. That includes Codex, which may send what it reads to OpenAI;
  - with Issues write, a command can delete comments, and they cannot be restored;
  - in such a project, `gh` calls that run sandboxed stop asking.

  No `ask` rule is added. The token cannot push, merge, or write to another repository, so what it can change stays inside the project's private repositories.
- **The project token is not git's credential.** Pushes and private fetches keep their path outside the sandbox.
- **No ADR.** Deleting the token and two `env` lines reverses it, so it fails gate one (hard to reverse).
- **Codex review, one pass on `origin/master...HEAD` at e42d826: CHANGES REQUESTED.** All six findings were accepted:
  - **Medium:** the token's exposure was understated. Pull requests write allows approving, dismissing and deleting reviews, and updating a PR's branch; Issues write allows deleting comments. Checked against GitHub's table. The texts now name these, Pull requests write is no longer in the default scope, and "can be undone" is gone.
  - **Medium:** a user-wide `SSL_CERT_FILE` changes trust for every program that honours it, outside the sandbox too. Moved to per project; see above.
  - **Low:** "whatever a session posts stays private" was too absolute, since collaborators, integrations and GitHub can see it. The texts now say the token writes only to its selected repositories.
  - **Low:** `scaffold-project` said `gh` "cannot run inside" the sandbox. It now says why that applies there: a new repository is in no project token's scope.
  - **Low:** the push, merge and alias claims are sound, with update-branch as the exception. Covered by the first finding.
  - **Low:** "per project" is not the only safe design. The per-command alternative is now recorded above.

  These fixes alone would not have needed a second pass: each narrows a scope or a claim in the direction its finding asked. The token-order measurement that came later did, and it is the next entry. The repository check found no ref moved. `.git/index` changed only its metadata (change time 20:13:19, modification time still the commit's, 20:11:27), as in earlier passes, and Codex's log holds no command against the repository.

- **Codex review, second pass on `origin/master...HEAD` at c5b5912: CHANGES REQUESTED.** It ran because the token-order measurement changed what the texts say `gh` does outside the sandbox. It confirmed the first pass's findings resolved, and that no text still claims every `gh` call in an opted-in project uses the narrow token. Two Low findings, both accepted:
  - the global `CLAUDE.md` stated the token order as fact. It now says the order was measured with gh 2.103.0, is not documented, and should be re-checked with `gh auth status` outside the sandbox after an upgrade;
  - this log said "No second pass", which this pass made false. Reworded above.

  No third pass: both fixes are wording. The repository check found no ref moved, and `.git/index` changed only its metadata again.

## Verification

- After the user's steps, sandboxed, with both variables given on the command line:
  - `gh auth status` names the project folder;
  - `gh issue list -R tia-tools/gkms-contest-ai --limit 1` works;
  - a repository outside the token's scope is refused.
- In a fresh gkms-contest-ai session, sandboxed `gh issue list` works with no variables given.
- Elsewhere: in this repository, sandboxed `gh` fails on TLS again once `SSL_CERT_FILE` is out of `~/.claude/settings.json`, and unsandboxed `gh auth status` still names the keychain.
