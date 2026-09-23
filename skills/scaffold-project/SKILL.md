---
name: scaffold-project
description: Create a new project directory from the Taka499/project-template scaffold — CLAUDE.md skeleton, docs/PLANS.md, docs/adr/README.md, docs/plans/ — initialise git on main, fill the CLAUDE.md overview, and propose the first commit. Use when an idea has no repository yet and needs one — "scaffold a new project", "start a new repo for this", "set this up from the template", or when /grill-me ends on a greenfield design with nowhere to write its captures.
---

# Scaffold Project

A design conversation that ends without a repository has nowhere durable to put its decisions. This skill turns "we should start a repo for this" into a directory that a fresh session can be launched from: the per-project scaffold copied exactly as the template's remote tip ships it, git initialised, and the `CLAUDE.md` skeleton filled with what is already known. It never commits on its own.

## Three confirmations before creating anything

Nothing is created until all three are settled with the user, one question at a time. A directory created on inference is worse than none, and agreeing on a name is not the same as asking for the directory.

1. **Directory name.** If the user has not named it, propose three or four candidates and let them pick. Offer names in more than one register (a plain English word, a term of art, a short word in the user's own language) rather than assuming the style of neighbouring repos: in the session that produced this skill, the parent directory was full of short Japanese names and the user rejected every Japanese candidate. Repository name and directory name are the same thing.
2. **Parent directory.** Default to the parent of the current repository when the session runs inside one, and to the current working directory otherwise. State the full target path (`<parent>/<name>`).
3. **Create it now.** A separate yes/no naming the full path and both actions: "create `<parent>/<name>` from project-template and initialise git in it now?" This is the request the global rule "MUST only make changes that were explicitly requested" is satisfied by, and it is the explicit permission for the `git init` in step 3; the first two questions only describe what would be created. If the user says no, stop; a design note in the conversation or in a file they name is the fallback.

Refuse if the target path exists; never merge into an existing directory. This skill creates repositories; it does not retrofit the scaffold into one that already exists. For that case, extract the template as in step 2 into a directory under `$TMPDIR` and copy in only the files the repository lacks, never overwriting, with none of the confirmations or the `git init` here.

## Steps

1. **Locate the template and pin its revision.** Prefer a local checkout `<parent>/project-template` whose `origin` is `Taka499/project-template` (`git -C <path> remote get-url origin`); run `git -C <path> fetch origin` and `git -C <path> remote set-head origin --auto`, which asks the remote for its default branch, then use `origin/HEAD`; never guess `main`. If there is no local checkout, clone shallow into `$TMPDIR` and use its `HEAD`; remove the clone afterwards. The local checkout's working tree, current branch, and uncommitted changes are irrelevant, because step 2 never reads them. Two things about the fetch: run it outside the sandbox when the remote is SSH, since the sandbox's proxy refuses the connection (`This proxy requires authentication`); and a fetch, set-head, or clone that fails is a stop, not a warning. Measured while writing this skill: with the fetch refused, `origin/main` was one merge behind and `git archive origin/HEAD` silently produced the previous scaffold (`docs/plans/.gitignore` where the remote had `.gitkeep`). A stale ref looks exactly like a current one.
2. **Create the target, then extract the committed tree, not the working tree.** Run

       mkdir <target>
       git -C <template> archive <revision> -o "$TMPDIR/project-template.tar"
       tar -xf "$TMPDIR/project-template.tar" -C <target>

   `mkdir` without `-p`, so an existing path fails instead of being merged into. Archive to a file rather than a pipe, so a failed `git archive` is an error you see instead of `tar` succeeding on empty input and leaving a hollow target for step 3 to initialise; then list `<target>` and confirm the expected files are there. The archive writes the revision's export contents, preserving paths, including placeholders such as `docs/plans/.gitkeep`; that is every tracked file unless the template ever adds a `.gitattributes` with `export-ignore`, which it does not have today. Do not copy files from the checkout, and do not hardcode the file list: a copy reads whatever is in the working tree, dirty edits included, and a fixed list silently ships a stale scaffold when the template grows. Record the revision (`git -C <template> rev-parse <revision>`) for the commit message. Today the tree is `CLAUDE.md`, `docs/PLANS.md`, `docs/adr/README.md`, `docs/plans/.gitkeep`.
3. **Initialise git on `main`, outside the sandbox.** Run

       git -C <target> init -b main

   always with `-C <target>`: the session's current directory is usually some other repository, and a bare `git init` there is the wrong repository re-initialised.

   with the sandbox disabled, and say why in one line. The reason is an observation, not an explanation: while writing this skill, two sandboxed attempts in a directory that was a sibling of the session's launch directory failed, the first copying Xcode's sample hooks into `.git/hooks` (`Operation not permitted`), the second writing `.git/config` after `--template=` had avoided the hooks. Plain `cp` and `python3` writes into the same directory succeeded in the same session, so the cause is not simply "outside the launch directory is read-only"; it was not established, and this skill does not claim to know it. One unsandboxed `git init` is the whole cost; do not spend time on `--template=` or `/sandbox` changes.
4. **Fill what is known in `CLAUDE.md`.** Write the Project Overview in two to four sentences from what the session established, and cite the plan or ADR path for any non-obvious claim, per the template's own sync contract. If ADRs are being written in the same session, add their index lines under Durable Decisions. Leave Architecture, Setup and Development, Build and Test, and Code Style as the template's comments; they are filled when code exists, not guessed.
5. **Write the session's captures**, if any, into their homes: ADRs under `docs/adr/` per `docs/adr/README.md`, the ExecPlan draft under `docs/plans/` per `docs/PLANS.md`. This step belongs to whichever skill invoked this one (`grill-me`, usually); do it here only when running standalone with captures in hand.
6. **Propose the first commit; do not run it.** Message pattern: `docs: scaffold <name> from project-template@<short revision> — <what else is in it>`. List the files to be added individually (the archived tree plus anything written in steps 4 and 5). Because it is the repository's first commit, it lands on `main` directly; say so, since the global Git rules otherwise forbid committing to a default branch.
7. **Tell the user the directory is ready to launch a session from**, and what does not carry over: file-based memory is keyed by working directory, so the new project starts with none, and anything decided only in the current conversation is lost unless step 5 wrote it down.

## Rules

- Never `git add .`; add the extracted and written files by name.
- Never commit, push, or create a remote without being asked. Creating the GitHub repository is a separate request.
- Do not "improve" the template while extracting it. A change to the scaffold is a PR to `Taka499/project-template`, not a local edit that drifts on the first project it ships in.
