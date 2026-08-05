#!/usr/bin/env bash
# Deploy this repo as the user-level Claude Code config by symlinking the
# tracked pieces into ~/.claude. Idempotent; backs up pre-existing real files.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"
mkdir -p "${CLAUDE_DIR}"

link() {
  local src="$1" dst="$2"
  if [ -L "${dst}" ]; then
    [ "$(readlink "${dst}")" = "${src}" ] && { echo "ok: ${dst} already linked"; return; }
    rm "${dst}"
  elif [ -e "${dst}" ]; then
    local backup="${dst}.pre-central.$(date +%Y%m%d%H%M%S)"
    echo "backup: ${dst} -> ${backup}"
    mv "${dst}" "${backup}"
  fi
  ln -s "${src}" "${dst}"
  echo "linked: ${dst} -> ${src}"
}

link "${REPO_DIR}/CLAUDE.md" "${CLAUDE_DIR}/CLAUDE.md"
link "${REPO_DIR}/skills"    "${CLAUDE_DIR}/skills"
link "${REPO_DIR}/docs"      "${CLAUDE_DIR}/docs"

echo "Done. ~/.claude now tracks $(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD) of ${REPO_DIR}."
