# Plan: Two lessons about Python hooks, from the git gate's removal

## Goal

Plan 0025 removed `hooks/git_gate.py`. Two lessons from it had lived only in that hook's README bullet or had not been written down at all. The user asked on 2026-10-28 to record them in the Claude Code stack note:
- a Python hook imports from its own directory before the standard library;
- a hook that cannot run fails open, and one whose script is missing blocks every call.

## Changes

- `docs/claude-code.md`:
  - § Code that runs outside the sandbox gets a paragraph: protect a Python hook's whole directory and run it with `-I`;
  - a new § A hook that cannot run, before § Permission rules:
    - name the interpreter by a version's own link;
    - guard the script's existence so a missing file exits 1, not 2.
- `CLAUDE.md` § Stack Notes: the `claude-code.md` line names "hooks that cannot run".

## Evidence

- **Import order.** Plan 0025 § Evidence, measured 2026-10-28 with `/opt/homebrew/opt/python@3.14/libexec/bin/python3` (3.14.9). A `json.py` beside a script that imports `json` ran in place of the standard library's. With `-I` it did not.
- **Interpreter path.** Plan 0023, 2026-10-22:
  - `brew upgrade` moved Homebrew's default Python to `python@3.15` and removed `/opt/homebrew/bin/python3`;
  - a bare `python3` then resolved to Apple's 3.9.6;
  - the hook failed open on every Bash call.
- **Missing script.** Measured 2026-10-28:
  - `python3 <missing file>` exits 2, with and without `-I`;
  - Apple's `/usr/bin/python3 --version` printed 3.9.6;
  - `/opt/homebrew/bin/python3` does not exist.
- **Exit codes.** That exit 2 from a PreToolUse hook blocks the call, and that other non-zero codes are non-blocking errors, comes from Claude Code's hooks documentation. The removed README bullet relied on the same behaviour for its `[ -f ]` guard.

## Decision Log (session 2026-10-28)

- **The stack note, not `CLAUDE.md`.** These are reference facts for anyone writing a hook, read before that work, and that is what stack notes are for.
- **Additive.** Nothing existing is replaced.
- **The example command uses `-I`.** It shows both lessons in one line.
- **No ADR.** Prose, trivially reversible.

## Verification

- Read the two passages through `~/.claude/docs/claude-code.md` after the merge.
- No path inside another project appears in the shared text; only this repository's plans are cited.
