#!/bin/sh
# Install the session scratch root's scripts (plan 0041) as a copy outside every repository:
#
#   scratch/install.sh           copy (or update) them into ~/.local/libexec/claude-scratch/
#   scratch/install.sh --check   only report whether the installed copy matches this checkout; exit 1 if not
#
# The allow rule for scratch-rm runs the copy with no prompt, so the copy, not this checkout, is what it
# trusts. Re-run after each merge that changes scratch/. The settings entries it needs are printed at the end.
set -eu
src="$(cd "$(dirname "$0")" && pwd)"
dst="$HOME/.local/libexec/claude-scratch"
files="common.sh session-start scratch-rm scratch-sweep"

if [ "${1:-}" = --check ]; then
    for f in $files; do
        cmp -s "$src/$f" "$dst/$f" || { echo "differs or missing: $dst/$f"; exit 1; }
    done
    echo "ok: $dst matches $src"
    exit 0
fi

mkdir -p "$dst"
for f in $files; do
    cp "$src/$f" "$dst/$f.tmp"
    chmod 755 "$dst/$f.tmp"
    mv -f "$dst/$f.tmp" "$dst/$f"
done
chmod 644 "$dst/common.sh"
echo "installed: $dst"
cat <<SETTINGS

~/.claude/settings.json needs, once:
  permissions.allow:  "Bash($dst/scratch-rm *)"
  permissions.deny:   "Edit($dst/**)"
  hooks.SessionStart: {"hooks": [{"type": "command", "command": "$dst/session-start"}]}
SETTINGS
