#!/bin/sh
# Protect main, master and develop in every repository on this machine: copy the reference-transaction
# hook to ~/.config/git/protect-branches and define it in ~/.gitconfig as a config-defined hook.
#
#   git-hooks/install-global.sh            install or update, then prove it runs
#   git-hooks/install-global.sh --check    only prove it runs; exit 1 if it does not
#
# Config-defined hooks run alongside each repository's own .git/hooks (Git LFS keeps working) and need
# no per-repository step. They need a git that supports them: Homebrew's 2.56 does, Apple's /usr/bin/git
# 2.50 ignores them (git-hooks/protect-branches.sh installs a per-repository copy for such a git).
# The hook acts only in the user's own repositories; it reads every remote's URL to tell. Both files written here sit
# outside the Claude Code sandbox's writable paths, so a sandboxed session cannot alter them; for the same
# reason run this script outside the sandbox. Re-running it updates the copy.
set -eu

source_hook="$(cd "$(dirname "$0")" && pwd)/reference-transaction"
target="${XDG_CONFIG_HOME:-$HOME/.config}/git/protect-branches"
if [ "${1:-}" != --check ]; then
    mkdir -p "$(dirname "$target")"
    cp "$source_hook" "$target.tmp"
    chmod +x "$target.tmp"
    mv "$target.tmp" "$target"
    git config --global --replace-all hook.protect-branches.event reference-transaction
    git config --global hook.protect-branches.command "$target"
fi

# Prove it is set up and runs with the git on PATH. Configured: the command is this copy, unchanged, and not
# disabled. Running: a direct commit on develop in a scratch repository is refused with this hook's own
# message. The probe's commits skip signing and --no-verify skips commit hooks, which a machine's global
# setup may have, so neither can fail the probe; reference-transaction is not a commit hook and still runs.
[ "$(git config --global --get hook.protect-branches.command || true)" = "$target" ] &&
    cmp -s "$source_hook" "$target" &&
    [ "$(git config --global --type=bool --get hook.protect-branches.enabled || echo true)" = true ] ||
    { echo "protect-branches: not configured as installed; run $0 without --check" >&2; exit 1; }
scratch=$(mktemp -d "${TMPDIR:-/tmp}/protect-branches.XXXXXX")
(
    cd "$scratch" || exit 1
    git init -q -b develop probe && cd probe || exit 1
    git -c user.name=p -c user.email=p@p -c commit.gpgSign=false commit -q --no-verify --allow-empty -m root
    before=$(git rev-parse develop)
    git -c user.name=p -c user.email=p@p -c commit.gpgSign=false commit -q --no-verify --allow-empty -m direct 2> refused.txt || true
    [ "$(git rev-parse develop)" = "$before" ] && grep -q "protect-branches: refusing" refused.txt
) && active=yes || active=no
rm -rf "$scratch"
if [ "$active" = yes ]; then
    echo "protect-branches: active for $(command -v git) ($(git --version))"
else
    echo "protect-branches: installed, but $(command -v git) ($(git --version)) did not run it; it needs a git with config-defined hooks" >&2
    exit 1
fi
