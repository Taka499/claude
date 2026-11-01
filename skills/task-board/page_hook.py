#!/usr/bin/env python3
"""The attention page's hooks (plan 0036 D1, D12, D13 in the Taka499/claude repo), for a project whose
`.task-board.json` names a page to wire in its own `.claude/settings.json` (SKILL.md § The attention page):

    python3 -I ~/.claude/skills/task-board/page_hook.py session-start   (SessionStart: watch the page)
    python3 -I ~/.claude/skills/task-board/page_hook.py restore         (FileChanged and PostToolUse)
    python3 -I ~/.claude/skills/task-board/page_hook.py stop            (Stop)

- **session-start** prints the page's absolute path as `watchPaths`, so FileChanged fires on any write to it.
- **restore** compares the page with the copy the helper last drew, kept in the main checkout's .git/task-board.
  A page that differs, and is not older than the copy, was written by hand: it is put back, the catch is logged in
  .git/task-board/restores.log (`check` counts them), and after a tool call the session is told why. A page older
  than the copy is the helper's own write in progress, and is left alone.
- **stop** acts only in a session working in the main checkout, the coordinator's. It records when the user last
  typed there, which "Since you last looked" counts from, then draws the page again.
Each reads the hook's JSON on stdin and exits 0 whatever happens: a failing hook must not stop the session.
Tests: python3 -m unittest discover -s skills/task-board
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# -I leaves this file's folder off sys.path; board.py and jobs.py sit beside it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import board  # noqa: E402
import jobs  # noqa: E402

BOARD = Path(__file__).resolve().parent / "board.py"
REDRAW_TIMEOUT = 60
TOLD = ("{page} is drawn by the task-board helper from the board, and was just changed by hand, so it has been put"
        " back. Change the board through board.py instead. If no command does what you needed, say so: a missing"
        " command is what this catch is for.")


def locate(cwd: Path, paths=None):
    """(the page, the .git/task-board folder, the main checkout's root) for the project at `cwd`; None when it
    names no page or git cannot name its main checkout."""
    try:
        config = board.parse_config(board.find_config(cwd).read_text())
    except (board.BoardError, OSError):
        return None
    if not config.page:
        return None
    root, state = paths if paths is not None else board.checkout_paths(cwd)
    config = board.main_checkout_config(config, root)
    if root is None or not config.page:
        return None
    try:
        return board.page_target(root, config.page), state, root
    except OSError:
        return None  # a page that resolves outside the main checkout is neither watched nor written


def restore(page: Path, copy: Path) -> bool:
    """Put the drawn copy back over a page changed by hand. True when it did."""
    try:
        drawn = copy.read_text()
        copied_at = copy.stat().st_mtime_ns
    except OSError:
        return False  # never drawn: nothing to restore from
    try:
        if page.read_text() == drawn or page.stat().st_mtime_ns < copied_at:
            return False
    except OSError:
        pass  # the page was removed: draw it back
    board.write_atomically(page, drawn)
    return True


def last_typed(transcript: str):
    """The time of the user's last typed message in a transcript, or None."""
    try:
        with open(transcript, errors="replace") as lines:
            records = [json.loads(line) for line in lines if line.strip().startswith("{")]
    except (OSError, ValueError):
        return None
    times = [at for at, _ in jobs.human_messages(records)]
    return max(times) if times else None


def main(argv: list, stdin: str, cwd: Path | None = None, now: datetime | None = None, paths=None,
         run=subprocess.run) -> int:
    try:
        given = json.loads(stdin) if stdin.strip() else {}
    except ValueError:
        given = {}
    here = Path(given.get("cwd") or cwd or Path.cwd())
    found = locate(here, paths)
    if not argv or found is None:
        return 0
    page, state, root = found
    mode, now = argv[0], now or datetime.now(timezone.utc)
    if mode == "session-start":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "watchPaths": [str(page)]}}))
    elif mode == "restore":
        event = given.get("hook_event_name", "")
        if event == "FileChanged" and Path(given.get("file_path") or "").resolve() != page.resolve():
            return 0
        if restore(page, state / "page.md"):
            try:
                with open(state / "restores.log", "a") as log:
                    log.write(f"{now.isoformat()}\t{event or 'restore'}\t{page}\n")
            except OSError:
                pass
            if event == "PostToolUse":
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                         "additionalContext": TOLD.format(page=page)}}))
    elif mode == "stop":
        if here.resolve() != root.resolve():
            return 0  # a worker's session: the helper already redraws after each of its writes
        typed = last_typed(given.get("transcript_path") or "")
        if typed is not None:
            try:
                board.write_atomically(state / "seen", typed.isoformat())
            except OSError:
                pass
        try:
            run([sys.executable, "-I", str(BOARD), "page"], cwd=root, capture_output=True, text=True,
                timeout=REDRAW_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:], sys.stdin.read()))
    except Exception:  # noqa: BLE001  (a hook that fails must not stop the session)
        sys.exit(0)
