# Plan: The commit gate's interpreter path — `/opt/homebrew/bin/python3` vanished in a Homebrew upgrade, and the gate failed open

## Goal

On 2026-10-22 every Bash call in Claude Code began printing a non-blocking hook error:

    PreToolUse:Bash hook error
      Failed with non-blocking status code: /bin/sh: /opt/homebrew/bin/python3: No such file or directory

The `hooks.PreToolUse` entry in `~/.claude/settings.json` starts `hooks/git_gate.py` with `/opt/homebrew/bin/python3`, and that file no longer existed. A hook that fails to start counts as no decision (`README.md` § The one file this repo does not deploy), so the gate was silent on every call: a commit or a local merge on `main`, `master` or `develop` went ahead without being asked. The README said this path "follows Homebrew's current Python across upgrades". That is what stopped being true.

## Cause

The user ran `brew upgrade` that morning, prompted by security issues in php and node and a CA contamination reported the day before. It moved `python@3.14` from 3.14.3_1 to 3.14.9 at 09:39.

- The old keg's `bin` held unversioned names (`python3`, `pip3`, `python3-config`, …) beside the versioned ones. The 3.14.9 keg's `bin` holds only versioned ones (`python3.14`, `pip3.14`, …). When the upgrade relinked, `/opt/homebrew/bin/python3` was removed and not replaced. Nothing was left dangling; the formula changed.
- The new caveat (`brew info python@3.14`) says the unversioned names are now in `/opt/homebrew/opt/python@3.14/libexec/bin`, and that Homebrew's `python3` on PATH now comes from a separate `python3` formula.
- With the Homebrew name gone, a bare `python3` on PATH resolves to Apple's `/usr/bin/python3`, 3.9.6. `git_gate.py` needs 3.10, so `python3 -m unittest discover -s hooks` now fails to import the module (`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`).

## What still held while it was broken

- git's own `reference-transaction` hook (`~/.config/git/protect-branches`) is plain `sh` with no Python. The `git` on PATH is Homebrew's 2.56, which runs config-defined hooks. So any non-merge update of a protected branch was still refused.
- `git push` stays in `permissions.ask`, and `gh` runs only outside the sandbox, where `Bash(dangerouslyDisableSandbox:true)` asks.
- Not covered: the asking layer itself. In particular a local `git merge` into a protected branch, which the git hook allows, plus the gate's checks for Apple's git and for `core.hooksPath` bypasses. No such command ran during the outage in the session that found it.

## Changes

- `~/.claude/settings.json` (untracked, edited by the user): the entry now names `/opt/homebrew/opt/python@3.14/libexec/bin/python3`.
- `README.md` § The one file this repo does not deploy: the quoted entry updated to match. The sentence about `/opt/homebrew/bin/python3` is replaced with the reason for the new path, the two rejected ones, and what to do when `python@3.14` is retired.
- `README.md` § Layout (`hooks/`) and the docstring of `hooks/test_git_gate.py`: the test command names a 3.10+ interpreter instead of bare `python3`. The `git-hooks` test command stays bare, because those 49 tests pass on Apple's 3.9.

## Decision Log (session 2026-10-22)

- **The version's own `libexec` link, not `brew install python3`.** Both would restore a working entry. Installing a formula means a fresh download during a supply-chain and CA incident; the `libexec` link reuses the keg the upgrade already installed. The gate does no network I/O (it imports `json`, `os`, `re`, `shlex`, `subprocess`, `sys` and nothing that opens a connection), so a CA problem does not affect how it works. Every viable option runs the same Homebrew keg, since Apple's 3.9 is too old.
- **`python@3.14`, not the `python@3` alias link.** Both currently resolve to the same binary (`Cellar/python@3.14/3.14.9/Frameworks/Python.framework/Versions/3.14/bin/python3.14`). The alias link follows whichever 3.x the alias names. The signed API already lists `python@3.15` among the versioned formulae, so a move of the alias can leave that link dangling and fail the gate open again. `python@3.14` is installed on request and still gets 3.14.x patch fixes in place.
- **Not the exact keg path** (`Cellar/python@3.14/3.14.9/…`). The next patch upgrade plus `brew cleanup` deletes it, which is the same failure again. The old 3.14.3_1 keg still has a `python3` for the same reason, and is rejected for the same reason.
- **The failure stays non-blocking.** Making a missing interpreter exit 2 would block every Bash call in every session, including the ones needed to repair it. The README already rejects this for a missing script file. The error is printed on every call, which is how this outage was noticed.
- **No ADR.** One path in an untracked file plus documentation; trivially reversible. Fails gate one.

## Evidence

- Current entry against the input `{"tool_input":{"command":"git commit -m x"},"cwd":"…/claude"}` on `master`: `sh: /opt/homebrew/bin/python3: No such file or directory`, exit 127, no decision. The same input with the new path: `"permissionDecision": "ask"`, reason `git commit on master: history on main, master and develop needs your approval`.
- `hooks/` tests: 74 OK on `/opt/homebrew/opt/python@3/libexec/bin/python3`, which is the same binary as the `python@3.14` link (both `realpath`s identical). Bare `python3` (Apple 3.9.6): import failure. `git-hooks/` tests: 49 OK on Apple 3.9.
- Integrity of the upgraded Python, checked with Apple's `/usr/bin/shasum` and `/usr/bin/python3` rather than the interpreter under test:
  - The cached bottle `python@3.14--3.14.9.arm64_tahoe.bottle.tar.gz` has SHA-256 `797bc39ad48b63f0d245f3f2ac9103a44355f86a29d1f148da596c253931a859`.
  - That value appears exactly once in `~/Library/Caches/Homebrew/api/internal/packages.arm64_tahoe.jws.json`, as `python@3.14`'s `bottle_checksum`.
  - brew verifies that file's JWS signature on download and deletes the file on failure (`Library/Homebrew/api.rb`, `verify_and_parse_jws`). It uses the key `Library/Homebrew/api/homebrew-1.pem` in brew's own checkout, last changed 2023-02-19 (`b7d6d00c34 api: use signed endpoint`) and unmodified on disk. brew itself is 7.0.10, HEAD dated 2026-10-19, before the incident.
  - So a forged TLS certificate alone could not have substituted the bottle.
  - Not established: that Homebrew's own build and signing were uncompromised (build attestations, `gh attestation verify`, were not checked), that the poured files are unchanged since, or anything about the php and node bottles.

## Verification

- The quoted entry in `README.md` is parsed as JSON and compared with the live `settings.json` entry: identical.
- No mention of `/opt/homebrew/bin/python3` remains outside `plans/` except the new sentence that warns against it.
- `hooks/` tests run with the interpreter the README now names.
- After merge: the hook error is gone from every Bash call (already true in the session that made the change).
