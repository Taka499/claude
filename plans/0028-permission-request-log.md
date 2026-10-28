# Plan: Log every permission request, so the user's approval load can be counted

## Goal

The user's approvals are the scarcest resource in a multi-session setup, and nothing records them. Claude Code's session logs hold the messages the user types, but not the permission dialogs the user answers.

So gkms-contest-ai's process metric could not reproduce the external assessment's count of 352 prompts. Its lean-loop report on 2026-10-30 can measure only typed messages. Its coordinator confirmed on 2026-10-28 that the rule that report must decide (#167: "merges still cost 3 or more prompts") counts approval dialogs. That project now runs up to five sessions at once, the coordinator and four workers (raised on 2026-10-28), so the approvals each worker costs matter more than before.

On 2026-10-28 the user chose a counter at user level. That counts every project, this harness included, and a project can be read from the log's folder field. A review session then reads the log for its window.

## Design

- **The event: `PermissionRequest`, not `Notification`.** The hooks documentation says `PermissionRequest` "runs when Claude Code is about to ask you for permission to use a tool". `Notification` with `permission_prompt` fires only after a dialog has waited about six seconds, and every keystroke delays it, so quick approvals would go uncounted. The docs recommend `PermissionRequest` "if you need a signal the moment Claude asks for permission".
- **It counts permission requests, which are not exactly dialogs shown.** Per the docs, the event also runs where Claude Code "would otherwise auto-deny a call that can't prompt", such as a background subagent or a non-interactive run. Three things are not documented:
  - whether it runs in auto mode for a call the classifier then approves;
  - whether a sandbox network-permission dialog (allowing a new host) counts as a tool permission request at all;
  - whether `AskUserQuestion` or other interactive tools pass through it.

  So the log records the fields that tell these cases apart: tool name, subagent id and permission mode. The review that reads it counts dialogs by filtering on them, and checks doubtful lines against the session's transcript. The Verification section measures the open cases.
- **Asynchronous, so it neither waits nor decides.** The hook runs with `"async": true`. The docs say async hooks "can't block or control Claude's behavior: response fields like `decision`, `permissionDecision`, and `continue` have no effect", and that Claude Code "starts the hook process and immediately continues without waiting for it to finish". `async` is "only available on `type: "command"` hooks", with no event excluded.
  - **Synchronous, it could delay a dialog:** a hung `jq` would hold it until the hook's timeout (600 s by default for a command hook). It could still never change the outcome.
  - **The command prints nothing on stdout anyway:** `>>` sends all of `jq`'s output to the log, so even decision-shaped input never reaches Claude Code.
  - **On failure** (`jq` missing, malformed input, a failed write), the hook exits non-zero and logs nothing. Measured: malformed input exits 5.
- **One line in the settings file, no script.** The command is written into `~/.claude/settings.json` itself. That file is a protected path no session can write, so there is no script file a session could change. That meets `docs/claude-code.md` § Code that runs outside the sandbox. It is the one hook that writes, and it writes only by appending to its own log. That is an exception to the same section's "a hook should only read", accepted because nothing else can carry the count.
- **What it logs:** one JSON line per request, in `~/.claude/permission-requests.jsonl`:
  - `t`: UTC time, from `jq`'s clock;
  - `session_id` and `agent`, the subagent id, `null` in a main session;
  - `cwd`;
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
          "command": "/opt/homebrew/bin/jq -c '{t: (now|todate), session_id, agent: .agent_id, cwd, mode: .permission_mode, tool: .tool_name, input: ((.tool_input.command // .tool_input.file_path // .tool_input.url // \"\") | tostring | .[0:200])}' >> \"$HOME/.claude/permission-requests.jsonl\"",
          "async": true
        }
      ]
    }
  ]
  ```

  `jq` is named by its absolute path, so the command does not depend on the hook's `PATH`.

## Changes

- `README.md` § The one file this repo does not deploy: a bullet for the entry. It says why the event is `PermissionRequest`, that the hook runs asynchronously and prints nothing, what the log counts, and where it lives.
- `~/.claude/settings.json`: the user pastes the entry above (hand-kept, ADR 0002).
- Not here: reading the log in gkms-contest-ai's `tools/process_metrics.py`. That is that project's change, through its own loop. Until then the review session reads the log directly.

## Evidence (2026-10-28; Claude Code 2.1.312, jq at `/opt/homebrew/bin/jq`)

- **Hooks documentation** (code.claude.com/docs/en/hooks, read 2026-10-28):
  - `permission_prompt` notifications fire "only after the prompt has waited about six seconds", and "each keystroke defers it";
  - `PermissionRequest` runs "only when Claude Code is about to ask you for permission, or when it would otherwise auto-deny a call that can't prompt";
  - its input carries `tool_name` and `tool_input`, and the common fields include `agent_id` for a subagent;
  - a hook that returns no decision "leaves the permission flow unchanged";
  - § Run hooks in the background, as quoted above;
  - a command hook's `timeout` defaults to 600 s, and a hook that times out "renders no decision".
- **The command, tested on sample input.** Three inputs, each run through `sh -c` from the JSON-parsed entry, with `HOME` pointed at a scratch folder and `PATH=/usr/bin:/bin`:
  - the docs' Bash example and a WebFetch call from a subagent in auto mode: each exited 0 with nothing on stdout or stderr, and appended one line, with `agent` and `mode` filled where present and `null` where not;
  - malformed input: exit 5, nothing appended, nothing on stdout.
- **The user's current hooks:** `Notification` (a sound, every notification), `Stop` (a sound), and `PreToolUse` as an empty list, with no entry since plan 0025.

## Decision Log (session 2026-10-28)

- **User level** (the user's choice). It counts every project; the `cwd` field separates them.
- **`PermissionRequest` over `Notification`,** for the six-second delay above.
- **`async: true` over a `timeout`.** A timeout of a few seconds would bound how long a hung hook delays a dialog. `async` removes the delay, and with it any way for the hook to decide.
- **An inline command over a script.** A script would be a file to protect. An inline command lives in a file no session can write.
- **A writing hook, by exception.** It appends to its own log and returns no decision. Pinning its read-only use with a test, as `docs/claude-code.md` asks of hook scripts, does not apply: there is no script.
- **No ADR.** Removing the entry reverses it, so it fails gate one (hard to reverse).
- **Codex review, one pass on `origin/master...HEAD` at 9328d3c: CHANGES REQUESTED.** It confirmed the command is correctly quoted and that nothing from the tool input executes. Findings:
  - **Medium, accepted:** the log counts permission requests, not dialogs shown. Calls auto-denied because they can't prompt, host callbacks, and undocumented cases (auto mode, network dialogs, interactive tools) differ. Now stated, `agent` added to the log, and the open cases put under Verification.
  - **Medium, accepted:** "never blocks" needed qualifying, since a synchronous hook that hangs delays the dialog. Now asynchronous.
  - **Low, accepted:** "an empty `PreToolUse`" read as contradicting the README. It now says an empty list, no entry.
  - **Low, no change:** the quoting, `$HOME` expansion, `now|todate` and the 200-character cut are correct.
  - **Low, no change:** the exception to "a hook should only read" is deliberate and documented.

  No second pass. `async` only removes the hook's ability to wait or decide, as the docs quoted above state, and the added field is logged data. The repository check found no ref moved, and `.git/index` changed only its metadata, as in earlier reviews.

## Verification

After the user pastes the entry:
- **A dialog in this session.** Trigger one with a harmless command outside the sandbox (an `ask` rule), answer it, and find exactly one new line with this session's id and the command.
- **No dialog, no line.** Run a command the permission rules allow, and find no new line.
- **Auto mode.** Run a command that no rule allows and that the classifier is likely to approve. A line with no dialog would mean the hook fires before the classifier, and the count would need the transcripts to tell shown dialogs from silent approvals.
- **Interactive tools.** Ask the user a question with `AskUserQuestion`, and see whether it logs a line.
- **Other projects.** A line from a gkms-contest-ai session carries that project's folder.
