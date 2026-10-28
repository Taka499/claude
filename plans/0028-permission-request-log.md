# Plan: Log every permission prompt, so the user's approval load can be counted

## Goal

The user's approvals are the scarcest resource in a multi-session setup, and nothing records them. Claude Code's session logs hold the messages the user types, but not the permission dialogs the user answers.

So gkms-contest-ai's process metric could not reproduce the external assessment's count of 352 prompts. Its lean-loop report on 2026-10-30 can measure only typed messages. That project now runs up to five sessions at once, the coordinator and four workers (raised on 2026-10-28), so the approvals each worker costs matter more than before.

On 2026-10-28 the user chose a counter at user level. That counts every project, this harness included, and a project can be read from the log's folder field. A review session then reads the log for its window.

## Design

- **The event: `PermissionRequest`, not `Notification`.** The hooks documentation says `PermissionRequest` "runs when Claude Code is about to ask you for permission to use a tool". `Notification` with `permission_prompt` fires only after a dialog has waited about six seconds, and every keystroke delays it, so quick approvals would go uncounted. The docs recommend `PermissionRequest` "if you need a signal the moment Claude asks for permission".
- **An observer, never a decider.** A `PermissionRequest` hook can allow or deny a call by printing a decision object on stdout. This one prints nothing: its only output goes to its log, and it exits 0. The docs say a hook that returns no decision "leaves the permission flow unchanged", so the dialog appears as before. If `jq` is missing or fails, the exit status is non-zero, not 2, which is a non-blocking error: the dialog still appears, and that request goes unlogged.
- **One line in the settings file, no script.** The command is written into `~/.claude/settings.json` itself. That file is a protected path no session can write, so there is no script file a session could change. That meets `docs/claude-code.md` § Code that runs outside the sandbox. It is the one hook that writes, and it writes only by appending to its own log. That is an exception to the same section's "a hook should only read", accepted because nothing else can carry the count.
- **What it logs:** one JSON line per request, in `~/.claude/permission-requests.jsonl`:
  - `t`: UTC time, from `jq`'s clock;
  - `session_id` and `cwd`;
  - `mode`: the permission mode, if the input carries it;
  - `tool`: the tool's name;
  - `input`: the first 200 characters of the command, file path or URL.

  The session logs already hold the same commands in full, so the log adds no new exposure. Sandboxed sessions cannot write `~/.claude` itself, since it is not in `sandbox.filesystem.allowWrite`, so they cannot add or remove lines.
- **Minutes waited** need no second hook. The time of a request in the log, paired with the result's time in the session's transcript, gives how long the dialog waited.
- **The entry**, beside the existing `Notification` and `Stop` sound hooks, under `hooks`:

  ```json
  "PermissionRequest": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "/opt/homebrew/bin/jq -c '{t: (now|todate), session_id, cwd, mode: .permission_mode, tool: .tool_name, input: ((.tool_input.command // .tool_input.file_path // .tool_input.url // \"\") | tostring | .[0:200])}' >> \"$HOME/.claude/permission-requests.jsonl\""
        }
      ]
    }
  ]
  ```

  `jq` is named by its absolute path, so the command does not depend on the hook's `PATH`.

## Changes

- `README.md` § The one file this repo does not deploy: a bullet for the entry. It says why the event is `PermissionRequest`, that the hook must print nothing, and where the log lives.
- `~/.claude/settings.json`: the user pastes the entry above (hand-kept, ADR 0002).
- Not here: reading the log in gkms-contest-ai's `tools/process_metrics.py`. That is that project's change, through its own loop. Until then the review session reads the log directly.

## Evidence (2026-10-28; Claude Code 2.1.312, jq at `/opt/homebrew/bin/jq`)

- **Hooks documentation** (code.claude.com/docs/en/hooks, read 2026-10-28):
  - `permission_prompt` notifications fire "only after the prompt has waited about six seconds", and "each keystroke defers it";
  - `PermissionRequest` runs "only when Claude Code is about to ask you for permission, or when it would otherwise auto-deny a call that can't prompt";
  - its input carries `tool_name` and `tool_input`;
  - a hook that returns no decision "leaves the permission flow unchanged".

  Not stated there: whether it runs in auto mode for calls the classifier then approves.
- **The command, tested on sample input** (the docs' Bash example, plus an Edit). Run through `sh -c` with `HOME` pointed at a scratch folder and `PATH=/usr/bin:/bin`, it exited 0 with nothing on stdout or stderr, and appended one line per input. A field the input lacks came out as `null`.
- **The user's current hooks:** `Notification` (a sound, every notification), `Stop` (a sound), and an empty `PreToolUse`.

## Decision Log (session 2026-10-28)

- **User level** (the user's choice). It counts every project; the `cwd` field separates them.
- **`PermissionRequest` over `Notification`,** for the six-second delay above.
- **An inline command over a script.** A script would be a file to protect. An inline command lives in a file no session can write.
- **A writing hook, by exception.** It appends to its own log and returns no decision. Pinning its read-only use with a test, as `docs/claude-code.md` asks of hook scripts, does not apply: there is no script.
- **No ADR.** Removing the entry reverses it, so it fails gate one (hard to reverse).

## Verification

After the user pastes the entry:
- **A dialog in this session.** Trigger one with a harmless command outside the sandbox (an `ask` rule), answer it, and find exactly one new line with this session's id and the command.
- **No dialog, no line.** Run a command the permission rules allow, and find no new line.
- **Auto mode.** Run a command that no rule allows and that the classifier is likely to approve. A line with no dialog would mean the hook fires before the classifier, and the count would need the transcripts to tell shown dialogs from silent approvals.
- **Other projects.** A line from a gkms-contest-ai session carries that project's folder.
