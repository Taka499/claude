#!/bin/sh
# Protect main, master and develop in every repository on this machine: copy the reference-transaction
# hook to ~/.config/git/protect-branches and define it in ~/.gitconfig as a config-defined hook.
#
#   git-hooks/install-global.sh
#
# Config-defined hooks run alongside each repository's own .git/hooks (Git LFS keeps working) and need
# no per-repository step. They need a git that supports them: Homebrew's 2.56 does, Apple's /usr/bin/git
# 2.50 ignores them (git-hooks/protect-branches.sh installs a per-repository copy for such a git).
# The hook acts only in the user's own repositories; it reads origin to tell. Both files written here sit
# outside the Claude Code sandbox's writable paths, so a sandboxed session cannot alter them; for the same
# reason run this script outside the sandbox. Re-running it updates the copy.
set -eu

source_hook="$(cd "$(dirname "$0")" && pwd)/reference-transaction"
target="${XDG_CONFIG_HOME:-$HOME/.config}/git/protect-branches"
mkdir -p "$(dirname "$target")"
cp "$source_hook" "$target.tmp"
chmod +x "$target.tmp"
mv "$target.tmp" "$target"
git config --global --replace-all hook.protect-branches.event reference-transaction
git config --global hook.protect-branches.command "$target"

# Prove it runs with the git on PATH: a direct commit on develop in a scratch repository must be refused.
scratch=$(mktemp -d "${TMPDIR:-/tmp}/protect-branches.XXXXXX")
(
    cd "$scratch" || exit 1
    git init -q -b develop probe && cd probe || exit 1
    git -c user.name=p -c user.email=p@p commit -q --allow-empty -m root
    before=$(git rev-parse develop)
    git -c user.name=p -c user.email=p@p commit -q --allow-empty -m direct 2> /dev/null || true
    [ "$(git rev-parse develop)" = "$before" ]
) && active=yes || active=no
rm -rf "$scratch"
if [ "$active" = yes ]; then
    echo "protect-branches: active for $(command -v git) ($(git --version))"
else
    echo "protect-branches: installed, but $(command -v git) ($(git --version)) did not run it; it needs a git with config-defined hooks" >&2
    exit 1
fi
