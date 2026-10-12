"""Tests for git_gate.py. Run: python3 -m unittest discover -s hooks"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import git_gate
from git_gate import decide

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git_gate.py")


def on(branch, elsewhere=None):
    """A branch_of that reports `branch` for the session's cwd and `elsewhere[dir]` for a `cd` target."""
    elsewhere = elsewhere or {}
    return lambda directory: branch if directory is None else elsewhere.get(directory)


def asks(verdict):
    return verdict is not None and verdict[0] == "ask"


class FeatureBranchWork(unittest.TestCase):
    """Happy path: the standing permission covers a feature branch."""

    def test_commit_on_feature_branch_is_left_alone(self):
        self.assertIsNone(decide('git commit -m "feat: x"', on("feat/x")))

    def test_staging_then_committing_on_feature_branch(self):
        self.assertIsNone(decide("git add a.py b.py && git commit -m 'fix: y'", on("feat/x")))

    def test_merging_develop_into_feature_branch_updates_it(self):
        self.assertIsNone(decide("git merge develop", on("feat/x")))

    def test_read_only_git_on_develop(self):
        self.assertIsNone(decide("git status && git log --oneline -3 && git diff develop", on("develop")))

    def test_pull_on_master_is_not_a_history_write_here(self):
        self.assertIsNone(decide("git pull --ff-only origin master", on("master")))


class ProtectedBranches(unittest.TestCase):
    """The rule: history written to main, master or develop asks."""

    def test_commit_on_each_protected_branch_asks(self):
        for branch in ("main", "master", "develop"):
            with self.subTest(branch=branch):
                verdict = decide('git commit -m "x"', on(branch))
                self.assertTrue(asks(verdict))
                self.assertIn(branch, verdict[1])

    def test_merge_into_develop_asks(self):
        self.assertTrue(asks(decide("git merge --no-ff feature/b11", on("develop"))))

    def test_other_history_writers_ask(self):
        for command in ("git revert -m 1 abc123", "git cherry-pick abc123", "git am < p.patch"):
            with self.subTest(command=command):
                self.assertTrue(asks(decide(command, on("develop"))))

    def test_merge_continue_still_writes_the_merge_commit(self):
        self.assertTrue(asks(decide("git merge --continue", on("main"))))

    def test_gh_pr_merge_always_asks(self):
        self.assertTrue(asks(decide("gh pr merge 23 --merge", on("feat/x"))))


class EdgesAndCorners(unittest.TestCase):

    def test_abort_leaves_the_branch_alone(self):
        self.assertIsNone(decide("git merge --abort", on("develop")))
        self.assertIsNone(decide("git cherry-pick --abort", on("develop")))

    def test_env_assignment_before_git(self):
        self.assertTrue(asks(decide("GIT_EDITOR=true git merge --continue", on("develop"))))

    def test_global_options_before_subcommand(self):
        self.assertTrue(asks(decide("git -c user.name=x --no-pager commit -m y", on("develop"))))
        self.assertIsNone(decide("git --no-pager log -1", on("develop")))

    def test_cd_into_a_worktree_uses_that_branch(self):
        branch_of = on("develop", {"../wt": "feat/wt"})
        self.assertIsNone(decide("cd ../wt && git commit -m x", branch_of))

    def test_cd_into_the_main_checkout_from_a_worktree_asks(self):
        branch_of = on("feat/wt", {"../main": "develop"})
        self.assertTrue(asks(decide("cd ../main && git merge --no-ff feat/wt", branch_of)))

    def test_cd_inside_a_subshell_does_not_leak_out(self):
        branch_of = on("develop", {"../wt": "feat/wt"})
        self.assertTrue(asks(decide("(cd ../wt && make) && git commit -m x", branch_of)))

    def test_git_dash_C_is_resolved(self):
        branch_of = on("feat/x", {"../main": "develop"})
        self.assertTrue(asks(decide("git -C ../main commit -m x", branch_of)))

    def test_newline_separated_commands(self):
        self.assertTrue(asks(decide("git add a\ngit commit -m x", on("master"))))

    def test_heredoc_message_with_apostrophe(self):
        command = "git commit -F - <<'EOF'\nfix: it's done\nEOF"
        self.assertTrue(asks(decide(command, on("develop"))))
        self.assertIsNone(decide(command, on("feat/x")))


class UnknownTargetsAsk(unittest.TestCase):
    """When the branch cannot be named, a history write asks instead of passing silently."""

    def test_detached_head_or_not_a_repo(self):
        self.assertTrue(asks(decide("git commit -m x", on(None))))

    def test_git_dir_override(self):
        self.assertTrue(asks(decide("git --git-dir=/elsewhere/.git commit -m x", on("feat/x"))))

    def test_cd_minus(self):
        self.assertTrue(asks(decide("cd - && git commit -m x", on("feat/x"))))

    def test_unbalanced_quotes_fall_back_to_a_scan(self):
        self.assertTrue(asks(decide("git commit -m \"unterminated", on("develop"))))
        self.assertIsNone(decide("git commit -m \"unterminated", on("feat/x")))

    def test_unbalanced_quotes_with_cd_ask_even_on_a_feature_branch(self):
        self.assertTrue(asks(decide("cd ../wt && git commit -m \"unterminated", on("feat/x"))))


class Negative(unittest.TestCase):
    """Things that must NOT trigger a prompt."""

    def test_empty_command(self):
        self.assertIsNone(decide("", on("develop")))

    def test_git_commit_inside_quoted_text(self):
        self.assertIsNone(decide('echo "next: git commit on develop"', on("develop")))

    def test_merge_base_is_not_merge(self):
        self.assertIsNone(decide("git merge-base --is-ancestor a b", on("develop")))

    def test_non_git_command(self):
        self.assertIsNone(decide("python3 -m unittest", on("main")))

    def test_branch_merely_containing_a_protected_name(self):
        self.assertIsNone(decide("git commit -m x", on("feature/main-menu")))


class HookEndToEnd(unittest.TestCase):
    """The script as Claude Code runs it: JSON on stdin, a decision (or nothing) on stdout."""

    def run_hook(self, payload):
        result = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, timeout=30, check=True)
        return result.stdout

    def test_real_repository(self):
        with tempfile.TemporaryDirectory() as repo:
            git = ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run(git + ["init", "-q", "-b", "develop"], check=True)
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "root"], check=True)
            payload = {"tool_name": "Bash", "cwd": repo, "tool_input": {"command": "git commit -m x"}}
            output = json.loads(self.run_hook(payload))["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "PreToolUse")
            self.assertEqual(output["permissionDecision"], "ask")
            subprocess.run(git + ["switch", "-q", "-c", "feat/x"], check=True)
            self.assertEqual(self.run_hook(payload), "")

    def test_other_tools_are_ignored(self):
        payload = {"tool_name": "Read", "cwd": "/", "tool_input": {"file_path": "/x"}}
        self.assertEqual(self.run_hook(payload), "")

    def test_a_failing_gate_asks_about_history_writes_only(self):
        def boom(command, branch_of):
            raise RuntimeError("boom")

        for command, expect_ask in (("git commit -m x", True), ("ls -la", False)):
            with self.subTest(command=command):
                payload = {"tool_name": "Bash", "cwd": "/", "tool_input": {"command": command}}
                out = io.StringIO()
                with mock.patch.object(git_gate, "decide", boom), \
                        mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                        contextlib.redirect_stdout(out):
                    git_gate.main()
                if expect_ask:
                    self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "ask")
                else:
                    self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
