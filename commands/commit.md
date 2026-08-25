---
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git branch:*)
description: Propose a commit for the current changes
---

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Your task

Propose a commit for the affected files — do not create one yet. Global `CLAUDE.md` § Git Operations governs this command:

- **Never run `git commit` until the user has approved this specific commit.** Present the message and the exact file list, then wait.
- If the changes cover more than one meaningful unit of work, propose a small series rather than one batched commit, and say what each one contains.
- Stage affected files individually. Never `git add .`, never add whole directories, and leave untracked files alone unless the user names them.
- Message format: a type prefix (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `ci:`) following the house pattern `type: summary — key detail`.
- No coding-agent attribution: no `Co-Authored-By`, no session trailers, no model IDs.
- If the current branch is the default branch, say so and propose a feature branch first.
