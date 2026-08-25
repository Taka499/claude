#!/usr/bin/env bash
# Deploy this repo as the user-level Claude Code config by symlinking the
# tracked pieces into ~/.claude. Idempotent; backs up pre-existing real files.
#
# CLAUDE.md, docs/ and commands/ are linked whole — nothing but this repo
# writes there. skills/ is different: ~/.claude/skills is a shared namespace
# that other tools install into, so it stays a real directory and each skill
# this repo owns is linked into it individually.
# See docs/adr/0003-skills-are-linked-per-skill.md.
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
    if [ -d "${dst}" ]; then
      echo "  NOTE: ${dst} is a directory. Everything inside it leaves the live config;"
      echo "        port anything you still want into ${REPO_DIR} and re-run."
    fi
    mv "${dst}" "${backup}"
  fi
  ln -s "${src}" "${dst}"
  echo "linked: ${dst} -> ${src}"
}

# Refuse to run against the pre-0003 layout rather than guess which skills in
# the repo are ours and which an installer dropped there. Migration moves
# files the user owns, so it is a deliberate manual step, done once.
refuse_old_skills_layout() {
  local src_dir="${REPO_DIR}/skills" dst_dir="${CLAUDE_DIR}/skills"
  [ -L "${dst_dir}" ] || return 0
  [ "$(readlink "${dst_dir}")" = "${src_dir}" ] || return 0
  cat >&2 <<MSG
error: ${dst_dir} is a link to ${src_dir} (the layout before ADR 0003).

  While it is linked, every skill another tool installs lands in this repo's
  working tree. Migrate once, by hand, so you decide what moves:

    1. Check what is in the repo but not tracked by it:
         git -C "${REPO_DIR}" status --porcelain --untracked-files=all skills/
    2. Replace the link with a real directory:
         rm "${dst_dir}" && mkdir -p "${dst_dir}"
    3. Move every untracked (i.e. externally installed) skill back out of the
       repo, e.g.:
         mv "${src_dir}/<their-skill>" "${dst_dir}/<their-skill>"
    4. Re-run this script. It will link this repo's own skills individually.

  Commit any skill of your own that is still untracked before step 3, or it
  will look external to you when you read that list.
MSG
  exit 1
}

link_skills() {
  local src_dir="${REPO_DIR}/skills" dst_dir="${CLAUDE_DIR}/skills"
  mkdir -p "${dst_dir}"

  local entry name
  for entry in "${src_dir}"/*/; do
    [ -d "${entry}" ] || continue
    name="$(basename "${entry}")"
    link "${src_dir}/${name}" "${dst_dir}/${name}"
  done

  # Drop links left behind by a skill this repo no longer has — deleted, or
  # absent on the branch now checked out. Only ever removes a symlink that
  # points into this repo; real directories and other tools' skills are
  # untouchable here.
  local target
  for entry in "${dst_dir}"/*; do
    [ -L "${entry}" ] || continue
    target="$(readlink "${entry}")"
    case "${target}" in
      "${src_dir}"/*)
        [ -e "${target}" ] || { echo "prune: ${entry} (gone from ${src_dir})"; rm "${entry}"; }
        ;;
    esac
  done
}

refuse_old_skills_layout

link "${REPO_DIR}/CLAUDE.md" "${CLAUDE_DIR}/CLAUDE.md"
link "${REPO_DIR}/docs"      "${CLAUDE_DIR}/docs"
link "${REPO_DIR}/commands"  "${CLAUDE_DIR}/commands"
link_skills

# settings.json is deliberately NOT linked — Claude Code owns and rewrites that
# file (effortLevel, tui, enabledPlugins, …). See docs/adr/0002-settings-json-stays-untracked.md.

echo "Done. ~/.claude now tracks $(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD) of ${REPO_DIR}."
