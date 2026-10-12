#!/usr/bin/env python3
"""PreToolUse hook: ask before history lands on main, master or develop.

Global CLAUDE.md § Git Operations makes approving a task standing permission to commit on its
feature branch, while a commit on, or a merge into, main, master or develop still needs the
user's permission for that operation. A permission rule matches command text only, so
`Bash(git commit *)` cannot tell a feature-branch commit from a develop commit. This hook can:
it resolves the branch the command would write to and answers "ask" for a protected one.

Silence means "no opinion": the call continues through the normal permission flow (the
sandbox's auto-allow, the auto-mode classifier). When the hook cannot tell which branch a
history-writing command targets, it asks rather than staying silent.

Needs Python 3.10 or later; the settings entry names the interpreter by absolute path, because
macOS's /usr/bin/python3 is Apple's 3.9. Entry and reasons: README.md § The one file this repo
does not deploy.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

PROTECTED = frozenset({"main", "master", "develop"})

# Subcommands that write a commit to the current branch.
WRITES_HISTORY = frozenset({"commit", "merge", "cherry-pick", "revert", "am"})

# `--abort` / `--quit` leave the branch where it was; `--continue` still writes the commit.
LEAVES_BRANCH = frozenset({"--abort", "--quit"})

# git's global options that take a separate value (`git -C dir`, `git -c key=value`).
GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})

# Global options that point git at a repository other than the one in the working directory.
REDIRECTS_REPO = ("--git-dir", "--work-tree")

SEPARATORS = frozenset({"&&", "||", ";", "|", "|&", "&", ";;"})

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2[ \t]*(?=\n|$)", re.S)
FALLBACK_GIT = re.compile(r"\bgit\b[^\n;&|]*?\b(commit|merge|cherry-pick|revert|am)\b")
FALLBACK_GH_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
FALLBACK_CD = re.compile(r"(^|[;&|(]\s*)cd\s")

GH_MERGE_REASON = "gh pr merge puts a pull request into its base branch: that needs your approval"
UNKNOWN = object()  # a directory the hook cannot resolve

Decision = tuple[str, str]  # (permissionDecision, permissionDecisionReason)
BranchOf = Callable[[str | None], str | None]


@dataclass(frozen=True)
class Invocation:
    """One program run in the command: where it runs (None = the session's cwd) and its words."""

    directory: str | None | object
    words: tuple[str, ...]


def split_commands(command: str) -> list[Invocation] | None:
    """Split a shell command into the program runs it contains, tracking `cd` and subshells.

    Returns None when the text cannot be tokenized (unbalanced quotes), so the caller can fall
    back to a coarser scan instead of trusting a partial parse.
    """
    text = HEREDOC.sub("", command).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    runs: list[Invocation] = []
    directory: str | None | object = None
    saved: list[str | None | object] = []
    current: list[str] = []
    for token in tokens + [";"]:
        if token not in SEPARATORS and token not in ("(", ")"):
            current.append(token)
            continue
        words = _drop_env_assignments(current)
        if words[:1] == ["cd"]:
            directory = _join(directory, words[1] if len(words) > 1 else "~")
        elif words:
            runs.append(Invocation(directory, tuple(words)))
        current = []
        if token == "(":
            saved.append(directory)
        elif token == ")" and saved:
            directory = saved.pop()
    return runs


def _drop_env_assignments(words: list[str]) -> list[str]:
    index = 0
    while index < len(words) and ENV_ASSIGNMENT.match(words[index]):
        index += 1
    return words[index:]


def _join(base: str | None | object, target: str) -> str | None | object:
    if base is UNKNOWN or target == "-":
        return UNKNOWN
    if target.startswith(("/", "~")) or base is None:
        return target
    return f"{str(base).rstrip('/')}/{target}"


def git_subcommand(words: tuple[str, ...]) -> tuple[str | None | object, str, tuple[str, ...]] | None:
    """For a `git …` run, return (where -C points, or None / UNKNOWN; the subcommand; its arguments)."""
    if words[:1] != ("git",):
        return None
    directory: str | None | object = None
    index = 1
    while index < len(words) and words[index].startswith("-"):
        option = words[index]
        if option.startswith(REDIRECTS_REPO):
            directory = UNKNOWN
        if option in GIT_OPTS_WITH_VALUE and index + 1 < len(words):
            if option == "-C" and directory is not UNKNOWN:
                directory = _join(directory, words[index + 1])
            index += 2
        else:
            index += 1
    if index >= len(words):
        return None
    return directory, words[index], words[index + 1:]


def decide(command: str, branch_of: BranchOf) -> Decision | None:
    """The hook's whole rule. `branch_of(directory)` names the branch checked out there, or None."""
    runs = split_commands(command)
    if runs is None:
        return _decide_unparsed(command, branch_of)
    for run in runs:
        if run.words[:3] == ("gh", "pr", "merge"):
            return "ask", GH_MERGE_REASON
        parsed = git_subcommand(run.words)
        if parsed is None:
            continue
        git_dir, subcommand, args = parsed
        if subcommand not in WRITES_HISTORY or LEAVES_BRANCH & set(args):
            continue
        directory = _target(run.directory, git_dir)
        branch = None if directory is UNKNOWN else branch_of(directory)
        verdict = _decide_branch(subcommand, branch)
        if verdict:
            return verdict
    return None


def _target(run_directory: str | None | object, git_dir: str | None | object) -> str | None | object:
    """Where a git run writes: its `cd` directory, moved by `git -C`, or UNKNOWN."""
    if git_dir is UNKNOWN:
        return UNKNOWN
    if git_dir is None:
        return run_directory
    return _join(run_directory, str(git_dir))


def _decide_branch(subcommand: str, branch: str | None) -> Decision | None:
    if branch is None:
        return "ask", f"git {subcommand}: could not tell which branch it writes to, so asking"
    if branch in PROTECTED:
        return "ask", f"git {subcommand} on {branch}: history on main, master and develop needs your approval"
    return None


def _decide_unparsed(command: str, branch_of: BranchOf) -> Decision | None:
    if FALLBACK_GH_MERGE.search(command):
        return "ask", GH_MERGE_REASON
    found = FALLBACK_GIT.search(command)
    if not found:
        return None
    branch = None if FALLBACK_CD.search(command) else branch_of(None)
    return _decide_branch(found.group(1), branch)


def mentions_history_write(command: str) -> bool:
    return bool(FALLBACK_GIT.search(command) or FALLBACK_GH_MERGE.search(command))


def current_branch(cwd: str, directory: str | None) -> str | None:
    """The branch checked out in `directory` (relative to `cwd`), or None if detached or not a repo."""
    path = os.path.expanduser(directory) if directory else cwd
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    try:
        result = subprocess.run(
            ["git", "-C", path, "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    cwd = payload.get("cwd") or os.getcwd()
    try:
        verdict = decide(command, lambda directory: current_branch(cwd, directory))
    except Exception as error:
        # A gate that fails must ask about a history write, never wave it through.
        verdict = ("ask", f"git gate failed ({type(error).__name__}), so asking") if mentions_history_write(command) else None
    if verdict:
        decision, reason = verdict
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
