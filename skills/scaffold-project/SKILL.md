---
name: scaffold-project
description: Create a new project directory from the Taka499/project-template scaffold — CLAUDE.md skeleton, docs/PLANS.md, docs/adr/README.md, docs/plans/ — initialise git on main, fill the CLAUDE.md overview, and propose the first commit. Use when an idea has no repository yet and needs one — "scaffold a new project", "start a new repo for this", "set this up from the template", or when /grill-me ends on a greenfield design with nowhere to write its captures.
---

# Scaffold Project

A design conversation that ends without a repository has nowhere durable to put its decisions. This skill turns "we should start a repo for this" into a directory that a fresh session can be launched from: the per-project scaffold copied exactly as the template ships it, git initialised, and the `CLAUDE.md` skeleton filled with what is already known. It never commits on its own.

## Inputs to settle before creating anything

Nothing is created until both are confirmed by the user. A directory created on inference is worse than none.

1. **Directory name.** If the user has not named it, propose three or four candidates and let them pick. Offer names in more than one register (a plain English word, a term of art, a short word in the user's own language) rather than assuming the style of neighbouring repos: in the session that produced this skill, the parent directory was full of short Japanese names and the user rejected every Japanese candidate. Repository name and directory name are the same thing.
2. **Parent directory.** Default to the parent of the current repository when the session runs inside one, and to the current working directory otherwise. State the full target path (`<parent>/<name>`) in the confirmation.

Refuse if the target path exists; never merge into an existing directory.

## Steps

1. **Locate the template.** Prefer a local checkout `<parent>/project-template` whose `origin` is `Taka499/project-template` (`git -C <path> remote get-url origin`). Fetch it and warn if its default branch is behind the remote. If there is no local checkout, clone shallow into `$TMPDIR` and remove the clone afterwards.
2. **Copy exactly the tracked files.** List them with `git -C <template> ls-files` and copy each one, preserving paths. Do not hardcode the file list: the template grows, and a stale list silently ships an old scaffold. Today that list is `CLAUDE.md`, `docs/PLANS.md`, `docs/adr/README.md`, `docs/plans/.gitkeep`.
3. **Initialise git on `main`, outside the sandbox.** Run

       git init -b main

   with the sandbox disabled, and say why in one line. Two sandboxed attempts failed while writing this skill: the first copying Xcode's sample hooks into `.git/hooks` (`Operation not permitted`), the second writing `.git/config` after `--template=` had avoided the hooks. The sandbox's writable "." is the directory the session was launched from, and the new directory is a sibling, not a child. Plain file copies into it succeeded; git's lock-and-rename writes did not. Do not fight this with `--template=` or `/sandbox` changes; one unsandboxed `git init` is the whole cost.
4. **Fill what is known in `CLAUDE.md`.** Write the Project Overview in two to four sentences from what the session established, and cite the plan or ADR path for any non-obvious claim, per the template's own sync contract. If ADRs are being written in the same session, add their index lines under Durable Decisions. Leave Architecture, Setup and Development, Build and Test, and Code Style as the template's comments; they are filled when code exists, not guessed.
5. **Write the session's captures**, if any, into their homes: ADRs under `docs/adr/` per `docs/adr/README.md`, the ExecPlan draft under `docs/plans/` per `docs/PLANS.md`. This step belongs to whichever skill invoked this one (`grill-me`, usually); do it here only when running standalone with captures in hand.
6. **Propose the first commit; do not run it.** Message pattern: `docs: scaffold <name> from project-template — <what else is in it>`. List the files to be added individually (the template's `ls-files` list plus anything written in steps 4 and 5). Because it is the repository's first commit, it lands on `main` directly; say so, since the global Git rules otherwise forbid committing to a default branch.
7. **Tell the user the directory is ready to launch a session from**, and what does not carry over: file-based memory is keyed by working directory, so the new project starts with none, and anything decided only in the current conversation is lost unless step 5 wrote it down.

## Rules

- Never `git add .`; add the copied and written files by name.
- Never commit, push, or create a remote without being asked. Creating the GitHub repository is a separate request.
- Do not "improve" the template while copying it. A change to the scaffold is a PR to `Taka499/project-template`, not a local edit that drifts on the first project it ships in.
