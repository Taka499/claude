#!/bin/sh
# Install the reference-transaction hook guarding main, master and develop into a repository.
#
#   git-hooks/protect-branches.sh [REPOSITORY]      (default: the current directory)
#
# It copies the hook into the repository's shared hooks directory, so every worktree of the
# repository is covered. A copy, not a link: the Claude Code sandbox denies writes to .git/hooks,
# so a sandboxed session cannot alter the installed copy, while it could alter this repository.
# For the same reason this script must run outside the sandbox. Re-running it updates a copy it
# installed; it refuses to overwrite a reference-transaction hook from anywhere else.
set -eu

source_hook="$(cd "$(dirname "$0")" && pwd)/reference-transaction"
repository=${1:-.}

common=$(git -C "$repository" rev-parse --path-format=absolute --git-common-dir) || {
    echo "protect-branches: not a git repository: $repository" >&2
    exit 1
}
# Set at all, even to the empty string, core.hooksPath makes git ignore the common hooks directory.
if hooks_path=$(git -C "$repository" config --get core.hooksPath); then
    echo "protect-branches: core.hooksPath is set to $hooks_path, so git ignores $common/hooks here." >&2
    echo "Copy $source_hook into that directory, combining it with any reference-transaction hook there." >&2
    exit 1
fi
target="$common/hooks/reference-transaction"
# Ours only when the marker is the hook's second line, as this script writes it.
if [ -e "$target" ] && [ "$(sed -n 2p "$target")" != "$(sed -n 2p "$source_hook")" ]; then
    echo "protect-branches: $target exists and was not installed by this script; not overwriting it." >&2
    exit 1
fi
mkdir -p "$common/hooks"
cp "$source_hook" "$target.tmp"
chmod +x "$target.tmp"
mv "$target.tmp" "$target"
echo "protect-branches: main, master and develop are protected in $(git -C "$repository" rev-parse --show-toplevel)"
