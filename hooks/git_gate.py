#!/usr/bin/env python3
"""PreToolUse hook: ask before history lands on main, master or develop.

Global CLAUDE.md § Git Operations makes approving a task standing permission to commit on its
feature branch, while history written to main, master or develop, and any push, still needs the
user's permission for that operation. A permission rule matches command text only, so
`Bash(git commit *)` cannot tell a feature-branch commit from a develop commit. This hook can.

It works from an allowlist. It stays silent only for git runs whose effect it can state exactly:
read-only and index-only subcommands, listing or plainly creating a branch, switching to a named
unprotected branch, fetching without a refspec, and writes to the current branch when that branch
can be named and is unprotected. Everything else asks — every other subcommand (aliases,
`update-ref`, `filter-branch`, `checkout`, …), a branch name that is a variable or an attached
option, a refspec destination, git found inside another program's text, a program that is itself
a variable, a `GIT_DIR`-style redirect, a `push`, a `gh pr merge`, unreadable hook input.
Two rounds of review showed that listing dangerous shapes cannot be completed; listing safe ones can.

What it cannot see: git run by a program file (`python3 tool.py`), fetch refspecs configured to
write local branches, and a hook process that fails to start, which Claude Code treats as no
decision. The backstop for these is git's own reference-transaction hook
(git-hooks/reference-transaction), defined once per machine in ~/.gitconfig by
git-hooks/install-global.sh: it refuses every non-merge update of a protected branch made through
git, whatever program runs it. This hook asks whenever a command carries core.hooksPath or a
hook.* setting, the ways to switch that off, and
before Apple's /usr/bin/git, which ignores a hook defined in ~/.gitconfig.

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
from dataclasses import dataclass, field

PROTECTED = frozenset({"main", "master", "develop"})

# Never write anything a branch points at, wherever they run.
READ_ONLY = frozenset({
    "status", "log", "diff", "show", "ls-files", "ls-tree", "ls-remote", "rev-parse", "rev-list",
    "describe", "blame", "grep", "shortlog", "cat-file", "for-each-ref", "merge-base", "name-rev",
    "show-ref", "var", "help", "version", "whatchanged", "count-objects", "check-ignore",
    "check-attr", "diff-tree", "diff-index", "diff-files", "cherry", "range-diff", "format-patch",
})

# Change the index, the working tree, tags, the stash or configuration, but never a branch.
INDEX_ONLY = frozenset({
    "add", "rm", "mv", "restore", "stash", "apply", "notes", "tag", "init", "clone", "remote",
    "gc", "prune", "clean", "config", "sparse-checkout",
})

# Options that make git run a program or take refs from somewhere the command text does not show.
# Any run carrying one asks, whatever its subcommand.
HIDDEN_EFFECT_OPTIONS = ("--upload-pack", "--receive-pack", "--exec", "--stdin", "--refmap")
# Options with that effect only for some subcommands: `clone -u PROG`, and hooks or configuration
# installed into a new repository (`clone -c core.hooksPath=…`, `--template`). `commit --template` is harmless.
HIDDEN_EFFECT_BY_SUBCOMMAND = {
    "clone": ("-u", "-c", "--template", "--config"), "init": ("--template",),
    "fetch": ("-u",), "pull": ("-u",), "ls-remote": ("-u",),
}

# Write to the branch that is checked out: silent only when that branch is named and unprotected.
CURRENT_BRANCH_WRITES = frozenset({"commit", "merge", "cherry-pick", "revert", "am", "pull", "rebase", "reset"})

# `--abort` / `--quit` leave the branch where it was; `--continue` still writes the commit.
LEAVES_BRANCH = frozenset({"--abort", "--quit"})

# `git branch` options that only list.
LISTING_FLAGS = frozenset({"-a", "--all", "-r", "--remotes", "-l", "--list", "-v", "-vv", "--verbose",
                           "--show-current", "--color", "--no-color", "-q", "--quiet"})
LISTING_PREFIXES = ("--format=", "--sort=", "--column", "--no-column", "--abbrev")

# What counts as a branch write when git is found inside another program's text (`bash -c`, a
# heredoc, `$(…)`). Unknown words are not writes there, so prose such as "the git repo" stays silent.
TEXT_WRITES = CURRENT_BRANCH_WRITES | frozenset({
    "push", "update-ref", "branch", "switch", "checkout", "worktree", "symbolic-ref", "fetch",
    "filter-branch", "filter-repo", "replace", "bisect", "fast-import",
})

# git's global options that take a separate value (`git -C dir`, `git -c key=value`).
GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"})

SEPARATORS = frozenset({"&&", "||", ";", "|", "|&", "&", ";;"})

# Print or read their arguments and never run them: only a `$(…)` or backtick inside is executed.
NON_EXECUTING = frozenset({"echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "wc", "ls", "test", "["})

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Point git at another repository or configuration: the target can no longer be named.
GIT_REDIRECT_ENV = re.compile(r"^GIT_(?:DIR|WORK_TREE|COMMON_DIR|NAMESPACE|CONFIG\w*)=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\s*\2[ \t]*(?=\n|$)", re.S)
# A git run inside free text: the subcommand after any global options.
GIT_IN_TEXT = re.compile(
    r"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|exec-path|config-env)(?:=\S+|\s+\S+)|-\S+))*"
    r"\s+(?!git\b)([a-z][a-z-]*)"
)
GH_MERGE_IN_TEXT = re.compile(r"\bgh\s+pr\s+merge\b")

GH_MERGE_REASON = "gh pr merge puts a pull request into its base branch: that needs your approval"
NESTED_REASON = ("git runs inside another command here (bash -c, eval, env, xargs, $( ), a heredoc, a variable …), "
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


@dataclass
class State:
    """What earlier runs in the same command changed: a redirect seen, branches switched to per directory."""

    redirected: bool = False
    switched: dict[str, str] = field(default_factory=dict)


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
        changes_to = _directory_change(words)
        if changes_to is not None:
            directory = UNKNOWN if changes_to is UNKNOWN else _join(directory, str(changes_to))
        elif words or env:
            runs.append(Invocation(directory, env, words))
        current = []
        if token == "(":
            saved.append(directory)
        elif token == ")" and saved:
            directory = saved.pop()
    return runs, bodies


def _directory_change(words: tuple[str, ...]) -> str | object | None:
    """Where a `cd`-like run moves the shell: a path, UNKNOWN (`popd`, `cd -`), or None if it is not one."""
    if words[:2] in (("builtin", "cd"), ("command", "cd")):
        words = words[1:]
    if words[:1] in (("cd",), ("pushd",)):
        operands = [word for word in words[1:] if not word.startswith("-") or word == "-"]
        return operands[0] if operands else "~"
    if words[:1] == ("popd",):
        return UNKNOWN
    return None


def _env_prefix_length(words: list[str]) -> int:
    index = 0
    while index < len(words) and ENV_ASSIGNMENT.match(words[index]):
        index += 1
    return index


def _join(base: str | None | object, target: str) -> str | None | object:
    if base is UNKNOWN or target == "-" or not _literal(target):
        return UNKNOWN
    if target.startswith(("/", "~")) or base is None:
        return target
    return f"{str(base).rstrip('/')}/{target}"


def _literal(word: str) -> bool:
    """Whether a word means what it says: no variable or substitution left for the shell to expand."""
    return "$" not in word and "`" not in word


def is_git(word: str) -> bool:
    return os.path.basename(word) == "git"


def git_subcommand(words: tuple[str, ...]) -> tuple[str | None | object, str, tuple[str, ...]] | None:
    """For a `git …` run: (where it writes: None, a `-C` path or UNKNOWN; the subcommand; its arguments)."""
    directory: str | None | object = None
    index = 1
    while index < len(words) and words[index].startswith("-"):
        option = words[index]
        takes_value = option in GIT_OPTS_WITH_VALUE
        if option.startswith(("--git-dir", "--work-tree")):
            directory = UNKNOWN
        elif option == "-C" and directory is not UNKNOWN and index + 1 < len(words):
            directory = _join(directory, words[index + 1])
        index += 2 if takes_value else 1
    if index >= len(words):
        return None
    return directory, words[index], words[index + 1:]


def text_writes(text: str) -> list[str]:
    """The branch-writing git subcommands found in free text (an inline `alias.` setting counts as one)."""
    return [found.group(1) for found in GIT_IN_TEXT.finditer(text)
            if found.group(1) in TEXT_WRITES or "alias." in found.group(0)]


def writes_in_text(text: str) -> bool:
    """Whether free text contains a branch-writing git run, or a `gh pr merge`."""
    return bool(GH_MERGE_IN_TEXT.search(text) or text_writes(text))


def _is_protected_ref(name: str) -> bool:
    name = name.lstrip("+")
    if name.startswith("refs/heads/"):
        name = name[len("refs/heads/"):]
    return name in PROTECTED


def _plain_branch(word: str) -> bool:
    """A branch name given literally, not an option, and not a protected one."""
    return _literal(word) and not word.startswith("-") and not _is_protected_ref(word)


def decide(command: str, branch_of: BranchOf) -> Decision | None:
    """The hook's whole rule. `branch_of(directory)` names the branch checked out there, or None."""
    parsed = split_commands(command)
    if parsed is None:
        return _decide_unparsed(command, branch_of)
    runs, bodies = parsed
    if any(writes_in_text(body) for body in bodies) and any(run.words and not is_git(run.words[0]) for run in runs):
        return "ask", NESTED_REASON
    # The print-only exemption holds only when nothing in the command can execute text:
    # `echo "git commit" | bash` and `bash <(echo git commit)` run what echo prints.
    inert = all(not run.words or is_git(run.words[0]) or run.words[0] in NON_EXECUTING for run in runs)
    state = State()
    for run in runs:
        exported = run.words[1:] if run.words[:1] == ("export",) else ()
        if any(GIT_REDIRECT_ENV.match(word) for word in exported) or (
                not run.words and any(GIT_REDIRECT_ENV.match(word) for word in run.env)):
            state.redirected = True  # GIT_DIR and the like now apply to every later git run
        if not run.words:
            continue
        verdict = _decide_run(run, branch_of, state, inert)
        if verdict:
            return verdict
    return None


def _decide_run(run: Invocation, branch_of: BranchOf, state: State, inert: bool) -> Decision | None:
    if run.words[:3] == ("gh", "pr", "merge"):
        return "ask", GH_MERGE_REASON
    if is_git(run.words[0]):
        return _decide_git_run(run, branch_of, state)
    if not _literal(run.words[0]) and (
            any(word in TEXT_WRITES or "alias." in word or word.startswith(HIDDEN_EFFECT_OPTIONS) for word in run.words[1:])
            or any(GIT_REDIRECT_ENV.match(word) for word in run.env)):
        return "ask", NESTED_REASON  # `$G commit`, `$G -c alias.x=push x`, where G=git
    scanned = _substitutions(run.words) if inert and run.words[0] in NON_EXECUTING else run.words
    return ("ask", NESTED_REASON) if writes_in_text(" ".join(scanned)) else None


def _decide_git_run(run: Invocation, branch_of: BranchOf, state: State) -> Decision | None:
    parsed = git_subcommand(run.words)
    if parsed is None:
        return None
    git_dir, subcommand, args = parsed
    if any("hookspath" in word.lower() or word.lower().lstrip("-c").startswith("hook.") for word in run.words + run.env):
        return "ask", "core.hooksPath or a hook.* setting would switch off git's own branch protection: asking"
    if run.words[0] == "/usr/bin/git" and subcommand not in READ_ONLY:
        return "ask", "Apple's /usr/bin/git ignores the branch-protection hook defined in ~/.gitconfig: asking"
    if subcommand == "config" and any(arg.lower().startswith(("include", "--file", "-f", "--blob")) for arg in args):
        return "ask", "git config including or writing another file could set core.hooksPath indirectly: asking"
    substituted = _substitutions(args)
    if substituted and writes_in_text(" ".join(substituted)):
        return "ask", NESTED_REASON
    if _has_hidden_effect(subcommand, args):
        return "ask", f"git {subcommand} with an option that runs a program or reads refs from elsewhere: asking"
    if subcommand == "stash" and args[:1] == ("branch",):
        return "ask", "git stash branch creates a branch and switches to it: asking"
    if subcommand in READ_ONLY or subcommand in INDEX_ONLY:
        return None
    target = _target(run.directory, git_dir)
    if subcommand in CURRENT_BRANCH_WRITES:
        if LEAVES_BRANCH & set(args):
            return None
        if subcommand == "pull" and any(":" in arg or not _literal(arg) for arg in args):
            return "ask", "git pull with a refspec can write a local branch other than the current one: asking"
        return _decide_branch(subcommand, _branch_at(target, run, branch_of, state))
    if subcommand == "switch":
        new = _switch_target(args)
        if new is None or target is UNKNOWN:
            return "ask", "git switch: the branch it lands on is protected, or cannot be read from the command: asking"
        state.switched[str(target)] = new
        return None
    if subcommand == "branch" and (_is_listing(args) or _is_plain_create(args)):
        return None
    if subcommand == "fetch" and all(":" not in arg and _literal(arg) for arg in args):
        return None
    if subcommand == "worktree" and args[:1] in (("list",), ("prune",)):
        return None
    if subcommand == "symbolic-ref" and _is_symbolic_ref_read(args):
        return None
    if subcommand == "push":
        return "ask", "git push publishes history: that needs your approval"
    return "ask", f"git {subcommand}: not a form this gate can show leaves main, master and develop alone, so asking"


def _branch_at(target: str | None | object, run: Invocation, branch_of: BranchOf, state: State) -> str | None:
    if target is UNKNOWN or state.redirected or any(GIT_REDIRECT_ENV.match(word) for word in run.env):
        return None
    return state.switched.get(str(target)) or branch_of(None if target is None else str(target))


def _switch_target(args: tuple[str, ...]) -> str | None:
    """The branch `git switch` lands on, when given plainly: `switch NAME` or `switch -c NAME [START]`."""
    if len(args) == 1 and _plain_branch(args[0]):
        return args[0]
    if len(args) in (2, 3) and args[0] in ("-c", "--create") and _plain_branch(args[1]):
        if len(args) == 2 or (_literal(args[2]) and not args[2].startswith("-")):
            return args[1]
    return None


def _has_hidden_effect(subcommand: str, args: tuple[str, ...]) -> bool:
    """Whether any argument is an option that runs a program or reads refs the command does not show.

    Long options match with or without `=value`; a short one also matches attached (`-ucmd`, `-ckey=value`).
    """
    extra = HIDDEN_EFFECT_BY_SUBCOMMAND.get(subcommand, ())
    return any(arg.startswith(HIDDEN_EFFECT_OPTIONS) or any(arg.startswith(option) for option in extra)
               for arg in args)


def _is_symbolic_ref_read(args: tuple[str, ...]) -> bool:
    """`git symbolic-ref [--short] [-q] NAME`: reads a symbolic ref (`-d` would delete it, a second name set it)."""
    options = [arg for arg in args if arg.startswith("-")]
    names = [arg for arg in args if not arg.startswith("-")]
    return len(names) <= 1 and all(arg in ("--short", "-q", "--quiet", "--recurse", "--no-recurse") for arg in options)


def _is_listing(args: tuple[str, ...]) -> bool:
    return all(arg in LISTING_FLAGS or arg.startswith(LISTING_PREFIXES) for arg in args)


def _is_plain_create(args: tuple[str, ...]) -> bool:
    """`git branch NEW [START]`: creates a new branch and moves nothing else."""
    if len(args) not in (1, 2) or not _plain_branch(args[0]):
        return False
    return len(args) == 1 or (_literal(args[1]) and not args[1].startswith("-"))


def _substitutions(words: tuple[str, ...]) -> tuple[str, ...]:
    """All the words when any holds a command substitution, which the shell runs before the command itself.

    All, not only the marked ones: unquoted, `echo `git commit -m x`` tokenizes as "`git", "commit", …
    """
    return words if any("$(" in word or "`" in word for word in words) else ()


def _target(run_directory: str | None | object, git_dir: str | None | object) -> str | None | object:
    """Where a git run writes: its `cd` directory, moved by `git -C`."""
    if git_dir is None or git_dir is UNKNOWN:
        return git_dir if git_dir is UNKNOWN else run_directory
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
    if GH_MERGE_IN_TEXT.search(command) or any(sub not in CURRENT_BRANCH_WRITES for sub in found) or re.search(
            r"(^|[;&|(]\s*)cd\s", command):
        return "ask", UNPARSED_REASON
    return _decide_branch(found[0], branch_of(None))


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
        if not isinstance(command, str) or not isinstance(cwd, str):
            raise TypeError("command or cwd is not a string")
    except (ValueError, AttributeError, TypeError) as error:
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
