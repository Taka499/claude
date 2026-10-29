---
name: scaffold-project
description: Create a new project directory from the Taka499/project-template scaffold — CLAUDE.md skeleton, docs/PLANS.md, docs/adr/README.md, docs/plans/ — initialise git on main (its branches protected by the global hook), fill the CLAUDE.md overview, propose the first commit, then create its GitHub repository (under Taka499 or tia-tools, public or private, as the user chooses) and push on the user's go. Use when an idea has no repository yet and needs one — "scaffold a new project", "start a new repo for this", "set this up from the template", or when /grill-me ends on a greenfield design with nowhere to write its captures.
---

# Scaffold Project

A design conversation that ends without a repository has nowhere durable to put its decisions. This skill turns "we should start a repo for this" into a directory that a fresh session can be launched from: the per-project scaffold copied exactly as the template's remote tip ships it, git initialised, and the `CLAUDE.md` skeleton filled with what is already known. It never commits on its own.

## Four confirmations before creating anything

Nothing is created until all four are settled with the user, one question at a time. A directory created on inference is worse than none, and agreeing on a name is not the same as asking for the directory.

1. **Directory name.** If the user has not named it, propose three or four candidates and let them pick. Offer names in more than one register (a plain English word, a term of art, a short word in the user's own language) rather than assuming the style of neighbouring repos: in the session that produced this skill, the parent directory was full of short Japanese names and the user rejected every Japanese candidate. Repository name and directory name are the same thing.
2. **Parent directory.** Default to the parent of the current repository when the session runs inside one, and to the current working directory otherwise. State the full target path (`<parent>/<name>`).
3. **GitHub owner and visibility.** Every repository gets a GitHub remote (global `CLAUDE.md` § Git Operations). Ask where it lives, the user's account `Taka499` or the `tia-tools` organization, and whether it is public or private. Say what private costs on the free plans: GitHub enforces branch protection on public repositories only, so a private one is guarded by the local hook alone.
4. **Create it now.** A separate yes/no naming the full path and the actions: "create `<parent>/<name>` from project-template and initialise git in it now?" This is the request the global rule "MUST only make changes that were explicitly requested" is satisfied by, and it is the explicit permission for the `git init` in step 3; the first three questions only describe what would be created. The GitHub repository is not created yet: that waits for step 7. If the user says no, stop; a design note in the conversation or in a file they name is the fallback.

Refuse if the target path exists; never merge into an existing directory. This skill creates repositories; it does not retrofit the scaffold into one that already exists. For that case, extract the template as in step 2 into a directory under `$TMPDIR` and copy in only the files the repository lacks, never overwriting, with none of the confirmations or the `git init` here.

## Steps

1. **Locate the template and pin its revision.** Prefer a local checkout `<parent>/project-template` whose `origin` is `Taka499/project-template` (`git -C <path> remote get-url origin`); run `git -C <path> fetch origin` and `git -C <path> remote set-head origin --auto`, which asks the remote for its default branch, then use `origin/HEAD`; never guess `main`. If there is no local checkout, clone shallow into `$TMPDIR` and use its `HEAD`; remove the clone afterwards. The local checkout's working tree, current branch, and uncommitted changes are irrelevant, because step 2 never reads them. Two things about the fetch: run it outside the sandbox when the remote is SSH, since the sandbox's proxy refuses the connection (`This proxy requires authentication`); and a fetch, set-head, or clone that fails is a stop, not a warning. Measured while writing this skill: with the fetch refused, `origin/main` was one merge behind and `git archive origin/HEAD` silently produced the previous scaffold (`docs/plans/.gitignore` where the remote had `.gitkeep`). A stale ref looks exactly like a current one.
2. **Create the target, then extract the committed tree, not the working tree.** Run

       mkdir <target> || exit 1
       archive=$(mktemp -d "$TMPDIR/project-template.XXXXXX") || exit 1
       git -C <template> archive <revision> -o "$archive/template.tar" || exit 1
       tar -xf "$archive/template.tar" -C <target> || exit 1

   `mkdir` without `-p`, so an existing path fails instead of being merged into; each line stops the command at its own failure, since without that a failed `mkdir` goes on to extract into the existing directory and the command still exits 0. Archive to a file rather than a pipe, so a failed `git archive` is an error you see instead of `tar` succeeding on empty input and leaving a hollow target for step 3 to initialise; then list `<target>` and confirm the expected files are there. The file goes in a folder `mktemp -d` makes for this run, never at a fixed name in `$TMPDIR`: every session on the machine shares that folder, so two scaffolds at once could each extract the other's archive. Run the four lines as one command, because a shell variable does not outlive the command that set it. The archive writes the revision's export contents, preserving paths, including placeholders such as `docs/plans/.gitkeep`; that is every tracked file unless the template ever adds a `.gitattributes` with `export-ignore`, which it does not have today. Do not copy files from the checkout, and do not hardcode the file list: a copy reads whatever is in the working tree, dirty edits included, and a fixed list silently ships a stale scaffold when the template grows. Record the revision (`git -C <template> rev-parse <revision>`) for the commit message. Today the tree is `CLAUDE.md`, `docs/PLANS.md`, `docs/adr/README.md`, `docs/plans/.gitkeep`.
3. **Initialise git on `main`, outside the sandbox.** Run

       git -C <target> init -b main

   always with `-C <target>`: the session's current directory is usually some other repository, and a bare `git init` there is the wrong repository re-initialised.

   with the sandbox disabled, and say why in one line. Branch protection needs no step here when the machine has the global hook: run `<claude-clone>/git-hooks/install-global.sh --check`, which proves it with a scratch repository and prints `active`. If it fails, tell the user that `<claude-clone>/git-hooks/install-global.sh` (without `--check`) sets it up once for every repository, outside the sandbox; `<claude-clone>` is the `Taka499/claude` checkout that `~/.claude/skills/scaffold-project` links into. On a machine whose git ignores config-defined hooks, `<claude-clone>/git-hooks/protect-branches.sh <target>` protects this one repository instead. Either way the hook allows the first commit, which creates `main`, and refuses every later update of `main` that is not a merge, so work after the first commit happens on feature branches.
4. **Fill what is known in `CLAUDE.md`.** Write the Project Overview in two to four sentences from what the session established, and cite the plan or ADR path for any non-obvious claim, per the template's own sync contract. If ADRs are being written in the same session, add their index lines under Durable Decisions. Leave Architecture, Setup and Development, Build and Test, and Code Style as the template's comments; they are filled when code exists, not guessed.
5. **Write the session's captures**, if any, into their homes: ADRs under `docs/adr/` per `docs/adr/README.md`, the ExecPlan draft under `docs/plans/` per `docs/PLANS.md`. This step belongs to whichever skill invoked this one (`grill-me`, usually); do it here only when running standalone with captures in hand.
6. **Propose the first commit; do not run it.** Message pattern: `docs: scaffold <name> from project-template@<short revision> — <what else is in it>`. List the files to be added individually (the archived tree plus anything written in steps 4 and 5). Because it is the repository's first commit, it lands on `main` directly; say so, since the global Git rules otherwise forbid committing to a default branch.
7. **Create the GitHub repository and push, on the user's go.** Ask once, naming everything: "create `<owner>/<name>` (<public or private>) on GitHub, add it as `origin` and push `main`?" Then run each command on its own, outside the sandbox: a repository that does not exist yet is in no project token's scope, so `gh` needs the user's login from the keychain (global `CLAUDE.md` § Git Operations), and so does the push:

       gh repo create <owner>/<name> --<public|private> --source <target> --remote origin
       git -C <target> push -u origin main
       <claude-clone>/git-hooks/protect-github.sh <owner>/<name>      # public repositories only

   For a private repository skip the last line: on the free plans GitHub answers 403 there, and the local hook is the guard. If the user declines, say that the repository has no remote yet, which the global rule requires, and leave it at that.
8. **Tell the user the directory is ready to launch a session from**, and what does not carry over: file-based memory is keyed by working directory, so the new project starts with none, and anything decided only in the current conversation is lost unless step 5 wrote it down.

## Rules

- Never `git add .`; add the extracted and written files by name.
- Never commit, push, or create the remote without the user's go for that step: the first commit in step 6, the repository and the push in step 7.
- Do not "improve" the template while extracting it. A change to the scaffold is a PR to `Taka499/project-template`, not a local edit that drifts on the first project it ships in.
