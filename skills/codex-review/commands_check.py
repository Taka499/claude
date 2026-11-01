"""Check where Codex ran its commands, from the log of a `codex exec` run.

Usage: python3 -I commands_check.py <codex log> <snapshot repo> <repository>

Step 4 of SKILL.md runs it before treating any changed entry in the repository
as another process's. A command passes only if it ran in the snapshot and
every path it names lands, once resolved, inside the snapshot or under a
system prefix (ALLOWED). Each path is resolved against the command's own
working directory, with ~ and $HOME expanded and symlinks followed, so `../`
climbing out of the snapshot, or a symlink into the repository such as one
under ~/.claude, is caught like the repository's own path. A path through any
other variable cannot be resolved and fails. It cannot follow a `cd` between
commands of one shell line, a path built at run time (`$(…)`, decoding), or
a program that picks its own paths: that is out of sight of any log reader.

A record in the log is a line that is exactly "exec", the shell command after
it (starting `/bin/zsh -lc`, `/bin/bash -lc` or `/bin/sh -lc`, possibly over
several lines and ending " in <working directory>"), then a status line
(" succeeded in …", " exited N in …"). The check fails closed: a log with no
records, a record with no status line after it, one whose command does not
start with such a shell, or one with no working directory, is flagged, not
passed. The script is split the way a shell splits it (shlex), so quotes
and backslashes cannot hide a path, and a script that will not split is
flagged. A path attached to a prefix is checked too: `file://` URLs to this
machine, an option's letters (`-C/p`), and a `:`, `@` or `+` before it.

Exit status: 0 every command passed, 1 something to look at (printed),
2 bad usage or the log could not be read.
Tests: python3 -m unittest discover -s skills/codex-review
"""
import os
import re
import shlex
import sys

STATUS = re.compile(r"^ (succeeded|exited|failed|declined|timed out)\b")
SHELL = re.compile(r"^/bin/(zsh|bash|sh) -lc ")
CWD = re.compile(r" in (/[^\n]*)$")
TOKEN = re.compile(r"[^\s'\"`;|&<>()=,]+")
URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/]*)(/.*)?$")
LOCAL_HOSTS = ("", "localhost", "127.0.0.1")
ALLOWED = ("/bin/", "/usr/", "/dev/null", "/opt/homebrew/", "/System/", "/Library/Developer/")


def records(text):
    """Yield (command text, working directory, has a status line) for each command record."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i] == "exec":
            j = i + 1
            while j < len(lines) and not STATUS.match(lines[j]):
                j += 1
            body = "\n".join(lines[i + 1:j])
            m = CWD.search(body)
            yield (body[:m.start()] if m else body), (m.group(1).strip() if m else ""), j < len(lines)
            i = j
        i += 1


def inside(path, base):
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def resolve(token, cwd, home):
    """The real absolute path a path-like token names, or None when a variable hides it."""
    t = token
    for prefix in ("${HOME}", "$HOME", "~"):
        if t == prefix or t.startswith(prefix + "/"):
            t = home + t[len(prefix):]
            break
    if "$" in t:
        return None
    return os.path.realpath(t if os.path.isabs(t) else os.path.join(cwd, t))


def candidates(token):
    """The paths a token may name: itself, or what follows an attached prefix.

    `file:///p` and `file://localhost/p` name /p; a URL to another host names
    no local path. A path may also follow an option's letters (`-C/p`,
    `-o~/p`, `--output../p`) or a `:`, `@` or `+` (`host:/p`, `@/p`).
    """
    m = URL.match(token)
    if m:
        return [m.group(2) or "/"] if m.group(1) in LOCAL_HOSTS else []
    out = [token]
    option = re.match(r"^-+[A-Za-z0-9][A-Za-z0-9-]*", token)
    starts = {option.end()} if option else set()
    starts |= {i + 1 for i, ch in enumerate(token) if ch in ":@+"}
    for i in sorted(starts):
        rest = token[i:]
        if "/" in rest or "~" in rest or ".." in rest:
            out.append(rest)
    return out


def words(command):
    """The words a shell would see in the command, quotes and backslashes resolved; None if it will not parse.

    The record's line is `/bin/zsh -lc <quoted script>`: the script is split
    the way a shell splits it, so `\\/repo` or `"/"repo` read as `/repo`.
    """
    try:
        outer = shlex.split(command)
        if len(outer) != 3 or outer[1] != "-lc":
            return None
        lex = shlex.shlex(outer[2], posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return None


def path_tokens(command):
    """The tokens of a command that may name a path: those holding a slash, a ~ or `..`; None if unparsable."""
    found = words(command)
    if found is None:
        return None
    return [t for w in found for t in TOKEN.findall(w) if "/" in t or "~" in t or ".." in t]


def problems(command, cwd, snapshot, repository, home, complete=True):
    """Why a command does not pass, as a list of reasons; empty when it passes."""
    if not complete:
        return ["no status line after the command"]
    if not SHELL.match(command):
        return ["not a shell command record"]
    if not cwd:
        return ["no working directory"]
    snap = os.path.realpath(snapshot)
    repo = os.path.realpath(repository)
    plugin_log = os.path.realpath(os.path.join(home, ".claude", "security"))
    where = os.path.realpath(cwd)
    if not inside(where, snap):
        return [f"ran outside the snapshot, in {cwd}"]
    out = []
    # Of the paths a token may name, report the gravest.
    rank = ("names the repository", "names the plugin's log", "a path through a variable",
            "a path outside the snapshot")
    tokens = path_tokens(command)
    if tokens is None:
        return ["the command will not parse as `<shell> -lc <script>`"]
    for token in tokens:
        found = set()
        for cand in candidates(token):
            path = resolve(cand, where, home)
            if path is None:
                found.add(rank[2])
            elif inside(path, repo):
                found.add(rank[0])
            elif inside(path, plugin_log):
                found.add(rank[1])
            elif not inside(path, snap) and not path.startswith(ALLOWED):
                found.add(rank[3])
        if found:
            out.append(f"{min(found, key=rank.index)}: {token}")
    return out


def check(text, snapshot, repository, home):
    """(number of records, [(command, reasons)] for the ones that do not pass)."""
    found = list(records(text))
    bad = [(cmd, why) for cmd, cwd, complete in found
           for why in [problems(cmd, cwd, snapshot, repository, home, complete)] if why]
    return len(found), bad


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    log, snapshot, repository = argv[1:]
    try:
        with open(log, errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"cannot read the Codex log: {e}", file=sys.stderr)
        return 2
    n, bad = check(text, snapshot, repository, os.path.expanduser("~"))
    if n == 0:
        print("no command records found: the log is empty or its format changed; read it by hand")
        return 1
    if not bad:
        print(f"{n} commands, every one run in the snapshot, every path inside it or under a system prefix")
        return 0
    print(f"{n} commands; {len(bad)} to look at:")
    for cmd, why in bad:
        print("---")
        print("; ".join(why))
        print(cmd[:500])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
