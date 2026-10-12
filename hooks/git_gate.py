#!/usr/bin/env python3
"""PreToolUse hook: ask before history lands on main, master or develop.

Global CLAUDE.md § Git Operations makes approving a task standing permission to commit on its
feature branch, while history written to main, master or develop, and any push, still needs the
user's permission for that operation. A permission rule matches command text only, so
`Bash(git commit *)` cannot tell a feature-branch commit from a develop commit. This hook can:
it resolves the branch each git run would write to and answers "ask" for a protected one.

It is conservative by design. It stays silent only for git runs it fully understands and that
write to a branch it can name as unprotected; everything else asks: git inside another program
(`bash -c`, `eval`, `env`, `xargs`, `$(…)`, backticks, interpreter heredocs), environment or
alias redirects, a branch switch earlier in the same command, unknown subcommands, and ref moves
that name a protected branch. Silence means "no opinion": the normal permission flow decides.

What it cannot see: git run by a script or program file (`python3 tool.py`), and a hook process
that fails to start, which Claude Code treats as no decision. A backstop for both has to sit in
git itself: a reference-transaction hook refusing non-merge updates of protected branches.

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

# Never move a branch, wherever they run.
READ_ONLY = frozenset({
    "status", "log", "diff", "show", "ls-files", "ls-tree", "ls-remote", "rev-parse", "rev-list",
    "describe", "blame", "grep", "shortlog", "cat-file", "for-each-ref", "merge-base", "name-rev",
    "show-ref", "var", "help", "version", "whatchanged", "count-objects", "check-ignore",
    "check-attr", "diff-tree", "diff-index", "diff-files", "cherry", "range-diff", "format-patch",
})

# Change the index, the working tree, tags, remotes or configuration, but never move a branch.
NO_BRANCH_WRITE = frozenset({
    "add", "rm", "mv", "restore", "stash", "fetch", "tag", "notes", "apply", "init", "clone",
    "remote", "gc", "prune", "clean", "config", "sparse-checkout", "branch", "worktree",
})

# Change what is checked out, so later writes in the same command cannot be resolved beforehand.
MOVES_HEAD = frozenset({"switch", "checkout", "bisect", "symbolic-ref"})

# Name refs they may create, move or delete: asking when one of those names is protected.
REF_MOVERS = frozenset({"branch", "update-ref", "switch", "checkout", "worktree", "symbolic-ref", "reset", "fetch"})

# What counts as a branch write when git is found inside another program's text (`bash -c`, a heredoc, `$(…)`).
# Unknown words are NOT treated as writes there, so prose such as "update the git repo" stays silent;
# a direct git run is stricter (an unknown subcommand, e.g. an alias, counts as a write).
TEXT_WRITES = frozenset({
    "commit", "merge", "cherry-pick", "revert", "am", "pull", "rebase", "reset", "push", "update-ref",
    "branch", "switch", "checkout", "worktree", "symbolic-ref", "fetch", "filter-branch", "replace", "bisect",
})

# `--abort` / `--quit` leave the branch where it was; `--continue` still writes the commit.
LEAVES_BRANCH = frozenset({"--abort", "--quit"})

# git's global options that take a separate value (`git -C dir`, `git -c key=value`).
GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})

SEPARATORS = frozenset({"&&", "||", ";", "|", "|&", "&", ";;"})

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Point git at another repository or configuration: the target can no longer be named.
GIT_REDIRECT_ENV = re.compile(r"^GIT_(?:DIR|WORK_TREE|COMMON_DIR|NAMESPACE|CONFIG\w*)=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\s*\2[ \t]*(?=\n|$)", re.S)
# A git run inside free text: the subcommand after any global options.
GIT_IN_TEXT = re.compile(
    r"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|exec-path)(?:=\S+|\s+\S+)|-\S+))*\s+(?!git\b)([a-z][a-z-]*)"
)
GH_MERGE_IN_TEXT = re.compile(r"\bgh\s+pr\s+merge\b")
# Print or read their arguments and never run them: only a `$(…)` or backtick inside is executed.
NON_EXECUTING = frozenset({"echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "wc", "ls", "test", "["})
CD_IN_TEXT = re.compile(r"(^|[;&|(]\s*)cd\s")

GH_MERGE_REASON = "gh pr merge puts a pull request into its base branch: that needs your approval"
NESTED_REASON = ("git runs inside another command here (bash -c, eval, env, xargs, $( ), a heredoc …), "
                 "so its branch cannot be checked: asking")
UNPARSED_REASON = "could not parse this command around a git write, so asking"
UNKNOWN = object()  # a directory or target the hook cannot resolve

Decision = tuple[str, str]  # (permissionDecision, permissionDecisionReason)
BranchOf = Callable[[str | None], str | None]


@dataclass(frozen=True)
class Invocation:
    """One program run in the command: where it runs (None = the session's cwd), its env prefix, its words."""

    directory: str | None | object
    env: tuple[str, ...]
    words: tuple[str, ...]


def split_commands(command: str) -> tuple[list[Invocation], list[str]] | None:
    """Split a shell command into its program runs (tracking `cd` and subshells) and its heredoc bodies.

    Returns None when the text cannot be tokenized (unbalanced quotes), so the caller falls back
    to a coarser scan instead of trusting a partial parse.
    """
    bodies = [match.group(3) for match in HEREDOC.finditer(command)]
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
        split = _env_prefix_length(current)
        env, words = tuple(current[:split]), tuple(current[split:])
        if words[:1] == ("cd",):
            directory = _join(directory, words[1] if len(words) > 1 else "~")
        elif words or env:
            runs.append(Invocation(directory, env, words))
        current = []
        if token == "(":
            saved.append(directory)
        elif token == ")" and saved:
            directory = saved.pop()
    return runs, bodies


def _env_prefix_length(words: list[str]) -> int:
    index = 0
    while index < len(words) and ENV_ASSIGNMENT.match(words[index]):
        index += 1
    return index


def _join(base: str | None | object, target: str) -> str | None | object:
    if base is UNKNOWN or target == "-":
        return UNKNOWN
    if target.startswith(("/", "~")) or base is None:
        return target
    return f"{str(base).rstrip('/')}/{target}"


def is_git(word: str) -> bool:
    return os.path.basename(word) == "git"


def git_subcommand(words: tuple[str, ...]) -> tuple[str | None | object, str, tuple[str, ...]] | None:
    """For a `git …` run: (where it writes: None, a `-C` path or UNKNOWN; the subcommand; its arguments)."""
    directory: str | None | object = None
    index = 1
    while index < len(words) and words[index].startswith("-"):
        option = words[index]
        takes_value = option in GIT_OPTS_WITH_VALUE
        value = words[index + 1] if takes_value and index + 1 < len(words) else ""
        if option.startswith(("--git-dir", "--work-tree")) or (option == "-c" and value.lower().startswith("alias.")):
            directory = UNKNOWN
        elif option == "-C" and directory is not UNKNOWN:
            directory = _join(directory, value)
        index += 2 if takes_value else 1
    if index >= len(words):
        return None
    return directory, words[index], words[index + 1:]


def text_writes(text: str) -> list[str]:
    """The branch-writing git subcommands found in free text (an inline `-c alias.` counts as one)."""
    return [found.group(1) for found in GIT_IN_TEXT.finditer(text)
            if found.group(1) in TEXT_WRITES or "alias." in found.group(0)]


def writes_in_text(text: str) -> bool:
    """Whether free text contains a branch-writing git run, or a `gh pr merge`."""
    return bool(GH_MERGE_IN_TEXT.search(text) or text_writes(text))


def names_protected(subcommand: str, args: tuple[str, ...]) -> bool:
    """Whether a ref-moving subcommand names a protected branch among its arguments."""
    if subcommand not in REF_MOVERS:
        return False
    for arg in args:
        if subcommand == "fetch":  # only a refspec's destination moves a local branch
            if ":" in arg and _is_protected_ref(arg.rsplit(":", 1)[1]):
                return True
        elif _is_protected_ref(arg.rsplit(":", 1)[-1]):
            return True
    return False


def _is_protected_ref(name: str) -> bool:
    name = name.lstrip("+")
    if name.startswith("refs/heads/"):
        name = name[len("refs/heads/"):]
    return name in PROTECTED


def decide(command: str, branch_of: BranchOf) -> Decision | None:
    """The hook's whole rule. `branch_of(directory)` names the branch checked out there, or None."""
    parsed = split_commands(command)
    if parsed is None:
        return _decide_unparsed(command, branch_of)
    runs, bodies = parsed
    if any(writes_in_text(body) for body in bodies) and any(run.words and not is_git(run.words[0]) for run in runs):
        return "ask", NESTED_REASON
    drifted = False  # an earlier run may have changed what is checked out, or where git points
    for run in runs:
        exported = run.words[1:] if run.words[:1] == ("export",) else ()
        if any(GIT_REDIRECT_ENV.match(word) for word in exported) or (
                not run.words and any(GIT_REDIRECT_ENV.match(word) for word in run.env)):
            drifted = True  # GIT_DIR and the like now apply to every later git run
        if not run.words:
            continue
        if run.words[:3] == ("gh", "pr", "merge"):
            return "ask", GH_MERGE_REASON
        if not is_git(run.words[0]):
            scanned = _substitutions(run.words) if run.words[0] in NON_EXECUTING else run.words
            if writes_in_text(" ".join(scanned)):
                return "ask", NESTED_REASON
            continue
        verdict, moves_head = _decide_git_run(run, branch_of, drifted)
        if verdict:
            return verdict
        drifted = drifted or moves_head
    return None


def _decide_git_run(run: Invocation, branch_of: BranchOf, drifted: bool) -> tuple[Decision | None, bool]:
    """(the verdict for one direct git run, whether it may change what is checked out)."""
    parsed = git_subcommand(run.words)
    if parsed is None:
        return None, False
    git_dir, subcommand, args = parsed
    substituted = _substitutions(args)
    if substituted and writes_in_text(" ".join(substituted)):
        return ("ask", NESTED_REASON), False
    if subcommand in READ_ONLY:
        return None, False
    if subcommand == "push":
        return ("ask", "git push publishes history: that needs your approval"), False
    if names_protected(subcommand, args):
        return ("ask", f"git {subcommand} names a protected branch (main, master or develop): asking"), False
    if subcommand in MOVES_HEAD:
        return None, True
    if subcommand in NO_BRANCH_WRITE or LEAVES_BRANCH & set(args):
        return None, False
    redirected = git_dir is UNKNOWN or any(GIT_REDIRECT_ENV.match(word) for word in run.env)
    if drifted or redirected:
        return _decide_branch(subcommand, None), False
    return _decide_branch(subcommand, branch_of(_target(run.directory, git_dir))), False


def _substitutions(words: tuple[str, ...]) -> tuple[str, ...]:
    """All the words when any holds a command substitution, which the shell runs before the command itself.

    All, not only the marked ones: unquoted, `echo `git commit -m x`` tokenizes as "`git", "commit", …
    """
    return words if any("$(" in word or "`" in word for word in words) else ()


def _target(run_directory: str | None | object, git_dir: str | None | object) -> str | None | object:
    """Where a git run writes: its `cd` directory, moved by `git -C`."""
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
    if not writes_in_text(command):
        return None
    found = text_writes(command)
    if GH_MERGE_IN_TEXT.search(command) or CD_IN_TEXT.search(command) or any(
            sub in MOVES_HEAD or sub == "push" for sub in found):
        return "ask", UNPARSED_REASON
    return _decide_branch(found[0] if found else "write", branch_of(None))


def current_branch(cwd: str, directory: str | None | object) -> str | None:
    """The branch checked out in `directory` (relative to `cwd`), or None if detached, not a repo, or unknown."""
    if directory is UNKNOWN:
        return None
    path = os.path.expanduser(str(directory)) if directory else cwd
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


def emit(decision: str, reason: str) -> None:
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, sys.stdout)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") != "Bash":
            return 0
        command = payload.get("tool_input", {}).get("command", "")
        cwd = payload.get("cwd") or os.getcwd()
    except (ValueError, AttributeError) as error:
        # Without the command there is no telling whether it writes history.
        emit("ask", f"git gate could not read the hook input ({type(error).__name__}), so asking")
        return 0
    try:
        verdict = decide(command, lambda directory: current_branch(cwd, directory))
    except Exception as error:
        # A gate that fails must ask about a history write, never wave it through.
        verdict = ("ask", f"git gate failed ({type(error).__name__}), so asking") if writes_in_text(command) else None
    if verdict:
        emit(*verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
