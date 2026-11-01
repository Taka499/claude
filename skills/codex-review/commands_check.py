"""Check where Codex ran its commands, from the log of a `codex exec` run.

Usage: python3 -I commands_check.py <codex log> <snapshot repo> <repository>

Step 4 of SKILL.md runs it before treating any changed entry in the repository
as another process's. A command passes only if it ran in the snapshot and
every word of its script, resolved as a path, lands inside the snapshot or
under a system prefix (ALLOWED).

How a command is read. Its record must split, as a shell would, into exactly
`<shell> -lc <script> in <dir>`; the script is then split the same way
(shlex), so quotes and backslashes cannot disguise a path. Each word is
brace-expanded, kept whole and also split at `=` and `,`. A path attached to
a prefix is checked too: a `file://` URL to this machine, the rest of an
option (`-C/p`), or what follows `:`, `@` or `+`. Each word is resolved
against the command's working directory: `~`, `~user` and `$HOME` expanded,
globs matched against the files there (every match checked), symlinks
followed. So `../` out of the snapshot, a link into the repository (such as
those under ~/.claude), or a bare name of such a link, is caught like the
repository's own path. A bare variable (`"$f"`) is left out; a path through
any other variable, or `~` for an unknown user, fails.

It fails closed: a log with no records, a record with no status line after
it, a record or script that will not split, or a brace it cannot expand, is
flagged, not passed. Out of its sight: a `cd` between commands of one shell
line, a path built at run time (`$(…)`, `$'…'`, `eval`, decoding), and a
program that chooses its own paths.

Exit status: 0 every command passed, 1 something to look at (printed),
2 bad usage or the log could not be read.
Tests: python3 -m unittest discover -s skills/codex-review
"""
import glob
import os
import re
import shlex
import sys

STATUS = re.compile(r"^ (succeeded|exited|failed|declined|timed out)\b")
SHELLS = ("/bin/zsh", "/bin/bash", "/bin/sh")
GLOB = re.compile(r"[*?\[]")
BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")
TOKEN = re.compile(r"[^\s'\"`;|&<>()=,]+")
URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/]*)(/.*)?$")
LOCAL_HOSTS = ("", "localhost", "127.0.0.1")
ALLOWED = ("/bin/", "/usr/", "/dev/null", "/opt/homebrew/", "/System/", "/Library/Developer/")


def records(text):
    """Yield (record text, has a status line) for each command record of a codex exec log."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i] == "exec":
            j = i + 1
            while j < len(lines) and not STATUS.match(lines[j]):
                j += 1
            yield "\n".join(lines[i + 1:j]), j < len(lines)
            i = j
        i += 1


def parse(body):
    """(script, working directory) when the record splits as exactly `<shell> -lc <script> in <dir>`, else None.

    Requiring the whole record to split this way means a line inside the
    script that looks like a status line cannot end the record early: the
    text cut there leaves the script's quote open, and the split fails.
    """
    try:
        w = shlex.split(body)
    except ValueError:
        return None
    if len(w) != 5 or w[0] not in SHELLS or w[1] != "-lc" or w[3] != "in" or not w[4].startswith("/"):
        return None
    return w[2], w[4]


def inside(path, base):
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def resolve(token, cwd, home):
    """The real absolute paths a token may name, or None when a variable or an unknown user hides it.

    `~`, `~/…`, `$HOME` and `${HOME}` expand to home, `~user/…` to that
    user's home. A glob is matched against the file system, as the shell
    would, and every match is returned; with no match, the literal path.
    """
    t = token
    for prefix in ("${HOME}", "$HOME", "~"):
        if t == prefix or t.startswith(prefix + "/"):
            t = home + t[len(prefix):]
            break
    else:
        if t.startswith("~"):
            expanded = os.path.expanduser(t)
            if expanded == t:
                return None
            t = expanded
    if "$" in t:
        return None
    t = t if os.path.isabs(t) else os.path.join(cwd, t)
    matches = glob.glob(t) if GLOB.search(t) else []
    return [os.path.realpath(m) for m in matches] or [os.path.realpath(t)]


def braces(word):
    """The words a shell's brace expansion makes of one word; None for a nested or unbalanced brace."""
    m = BRACE.search(word)
    if not m:
        return None if ("{" in word and "}" in word and "," in word) else [word]
    out = []
    for part in m.group(1).split(","):
        more = braces(word[:m.start()] + part + word[m.end():])
        if more is None:
            return None
        out += more
    return out


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


def words(script):
    """The words a shell would see in the script, quotes and backslashes resolved; None if it will not split.

    `\\/repo` and `"/"repo` both read as `/repo`.
    """
    try:
        lex = shlex.shlex(script, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return None


def path_tokens(script):
    """Every token of the script that may name a file; None if the script will not split or a brace will not expand.

    Each word is brace-expanded, then kept whole and also split at `=` and
    `,` (`--file=/p`, `a,/p`). A bare variable such as `"$f"` is left out:
    what it holds was named where it was set, or was built at run time.
    """
    found = words(script)
    if found is None:
        return None
    out = []
    for w in found:
        expanded = braces(w)
        if expanded is None:
            return None
        for e in expanded:
            for t in dict.fromkeys([e, *TOKEN.findall(e)]):
                if not re.fullmatch(r"\$\{?\w+\}?", t):
                    out.append(t)
    return out


def problems(body, snapshot, repository, home, complete=True):
    """Why a command record does not pass, as a list of reasons; empty when it passes."""
    if not complete:
        return ["no status line after the command"]
    parsed = parse(body)
    if parsed is None:
        return ["the record does not split as `<shell> -lc <script> in <dir>`"]
    script, cwd = parsed
    snap = os.path.realpath(snapshot)
    repo = os.path.realpath(repository)
    plugin_log = os.path.realpath(os.path.join(home, ".claude", "security"))
    where = os.path.realpath(cwd)
    if not inside(where, snap):
        return [f"ran outside the snapshot, in {cwd}"]
    out = []
    # Of the paths a token may name, report the gravest.
    rank = ("names the repository", "names the plugin's log", "a path through a variable or an unknown user's ~",
            "a path outside the snapshot")
    tokens = path_tokens(script)
    if tokens is None:
        return ["the script will not split, or a brace in it will not expand"]
    for token in tokens:
        found = set()
        for cand in candidates(token):
            paths = resolve(cand, where, home)
            for path in paths if paths is not None else [None]:
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
    bad = [(body, why) for body, complete in found
           for why in [problems(body, snapshot, repository, home, complete)] if why]
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
