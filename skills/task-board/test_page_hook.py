"""Tests for page_hook.py. Run: python3 -m unittest discover -s skills/task-board"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import page_hook

NOW = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.state = self.root / ".git" / "task-board"
        self.state.mkdir(parents=True)
        (self.root / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": "o/r",
                                                                "page": "coord/board.md"}))
        self.page = self.root / "coord" / "board.md"
        self.page.parent.mkdir()

    def run_hook(self, mode, given=None, cwd=None, run=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = page_hook.main([mode], json.dumps(given or {}), cwd=cwd or self.root, now=NOW,
                                  paths=(self.root, self.state), run=run or (lambda *a, **k: None))
        self.assertEqual(code, 0)
        return out.getvalue()

    def drawn(self, text="Updated 12:00\n"):
        (self.state / "page.md").write_text(text)
        time.sleep(0.01)
        self.page.write_text(text)

    def test_session_start_watches_the_page(self):
        printed = json.loads(self.run_hook("session-start"))
        self.assertEqual(printed["hookSpecificOutput"]["watchPaths"], [str(self.page)])

    def test_the_page_watched_is_the_main_checkouts_not_a_worktrees(self):
        worktree = Path(tempfile.mkdtemp())
        (worktree / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": "o/r",
                                                               "page": "coord/branch.md"}))
        printed = json.loads(self.run_hook("session-start", cwd=worktree))
        self.assertEqual(printed["hookSpecificOutput"]["watchPaths"], [str(self.page)])

    def test_a_project_without_a_page_gets_nothing(self):
        (self.root / ".task-board.json").write_text(json.dumps({"owner": "o", "project": 1, "repo": "o/r"}))
        self.assertEqual(self.run_hook("session-start"), "")

    def test_a_hand_edit_is_put_back_logged_and_told_after_a_tool_call(self):
        self.drawn()
        time.sleep(0.01)
        self.page.write_text("Updated 12:00\nfaked line\n")
        printed = self.run_hook("restore", {"hook_event_name": "PostToolUse", "cwd": str(self.root)})
        self.assertEqual(self.page.read_text(), "Updated 12:00\n")
        self.assertIn("put back", json.loads(printed)["hookSpecificOutput"]["additionalContext"])
        self.assertIn("\tPostToolUse\t", (self.state / "restores.log").read_text())

    def test_file_changed_restores_quietly_and_ignores_other_files(self):
        self.drawn()
        time.sleep(0.01)
        self.page.write_text("edited\n")
        self.assertEqual(self.run_hook("restore", {"hook_event_name": "FileChanged",
                                                   "file_path": str(self.root / "other.md")}), "")
        self.assertEqual(self.page.read_text(), "edited\n")
        self.assertEqual(self.run_hook("restore", {"hook_event_name": "FileChanged", "file_path": str(self.page)}),
                         "")
        self.assertEqual(self.page.read_text(), "Updated 12:00\n")

    def test_a_removed_page_is_drawn_back(self):
        self.drawn()
        self.page.unlink()
        self.run_hook("restore", {"hook_event_name": "FileChanged", "file_path": str(self.page)})
        self.assertEqual(self.page.read_text(), "Updated 12:00\n")

    def test_an_unchanged_page_or_the_helpers_own_write_in_progress_is_left_alone(self):
        self.drawn()
        self.assertEqual(self.run_hook("restore", {"hook_event_name": "PostToolUse"}), "")
        self.assertFalse((self.state / "restores.log").exists())
        time.sleep(0.01)
        (self.state / "page.md").write_text("Updated 12:05\n")  # the copy is newer: the page is being written
        self.assertEqual(self.run_hook("restore", {"hook_event_name": "PostToolUse"}), "")
        self.assertEqual(self.page.read_text(), "Updated 12:00\n")

    def test_stop_stamps_the_last_typed_message_and_redraws_in_the_main_checkout_only(self):
        transcript = self.root / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(r) for r in (
            {"type": "user", "timestamp": "2026-11-01T01:00:00Z", "origin": {"kind": "human"},
             "message": {"content": "#9 A"}},
            {"type": "user", "timestamp": "2026-11-01T02:00:00Z", "origin": {"kind": "peer"},
             "message": {"content": "from a worker"}})) + "\n")
        calls = []
        self.run_hook("stop", {"transcript_path": str(transcript), "cwd": str(self.root)},
                      run=lambda *a, **k: calls.append((a, k)))
        self.assertEqual((self.state / "seen").read_text(), "2026-11-01T01:00:00+00:00")
        self.assertEqual(calls[0][0][0][-1], "page")
        worktree = Path(tempfile.mkdtemp())
        (worktree / ".task-board.json").write_text((self.root / ".task-board.json").read_text())
        calls.clear()
        self.run_hook("stop", {"transcript_path": str(transcript), "cwd": str(worktree)}, cwd=worktree,
                      run=lambda *a, **k: calls.append(a))
        self.assertEqual(calls, [])

    def test_bad_input_and_a_missing_transcript_still_exit_zero(self):
        self.assertEqual(page_hook.main(["restore"], "not json", cwd=self.root, now=NOW,
                                        paths=(self.root, self.state)), 0)
        self.run_hook("stop", {"transcript_path": "/no/such/file"})
        self.assertFalse((self.state / "seen").exists())

    def test_the_main_checkout_is_found_from_a_worktree(self):
        main_root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(main_root)], check=True)
        subprocess.run(["git", "-C", str(main_root), "commit", "-q", "--allow-empty", "-m", "x"], check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                                GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL="/dev/null"))
        worktree = Path(tempfile.mkdtemp()) / "wt"
        subprocess.run(["git", "-C", str(main_root), "worktree", "add", "-q", "--detach", str(worktree)], check=True,
                       env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null"))
        root, state = page_hook.board.checkout_paths(worktree)
        self.assertEqual(root.resolve(), main_root.resolve())
        self.assertEqual(state.resolve(), (main_root / ".git" / "task-board").resolve())


if __name__ == "__main__":
    unittest.main()
