# Plan: Harvest from gkms-contest-ai — the two #119 A lessons, the parallel-session loop's lessons, a stack note for Claude Code itself

## Goal

From 2026-10-11, gkms-contest-ai ran up to three Claude Code sessions at once: a coordinator in the main checkout and one worker per feature branch, each in its own worktree. On 2026-10-23 it cut that loop back, after an external assessment measured that the loop cost more than the work it guarded. On 2026-10-26 the user asked how much of that approach could move into this repository. The answer: most of the lessons, little of the code. The worker scripts (`spawn_worker.sh`, `integrate.sh`, `reopen_worker.sh`, `inflight.py`, about 1,550 lines) read that project's status-page format and call MulmoTerminal's API. Only one project uses them, and the lean loop's first weekly measurement has not run yet.

The user chose to land two sets of lessons. The first is the two captures approved there as #119 A on 2026-10-18, which never reached this repository. The second is the lessons that need no code ("tier 1" in that answer).

## Changes

- `docs/python.md` § Showing a test red (new): delete `__pycache__` before each run of a mutation check. `-B` alone does not protect, as measured below.
- `docs/testing.md`:
  - a paragraph after the stored-fact one: commit a long regeneration's predicted outputs before the run, and measure every committed output;
  - § Scope expensive checks by risk (new): scope the check by the changed paths, record the tree hash a check passed on so a merge with that tree reruns nothing, run the full check regularly, accept the drift window.
- Global `CLAUDE.md` § Quality Gates, two bullets:
  - a rule a session must remember is carried by a tool that writes or checks the value;
  - measure what a process costs before adding a step to it, and prefer removing one.
- `docs/claude-code.md` (new stack note), listed in `CLAUDE.md` § Stack Notes and `README.md` § Layout:
  - code run outside the sandbox must be a copy no session can edit, and hooks only read;
  - in a worktree, tracked settings come from the worktree and `.claude/settings.local.json` from the main checkout (v2.1.211+);
  - approve a script by an exact-path allow rule, never by parsing shell text to grant, with the documented matching rules and the undocumented `$(…)` case;
  - `lsof -d cwd` instead of `ps`/`pgrep`.
- `docs/typescript.md` § Package manager for a repository worked on from several worktrees (new, added on the user's request of 2026-10-26 after the first review):
  - npm stays the default; a new repository worked on from several worktrees starts on pnpm, or on Bun if it runs on Bun;
  - the two settings pnpm needs under the sandbox (`storeDir`, `XDG_RUNTIME_DIR`), as measured;
  - the global virtual store stays off;
  - `strictDepBuilds` and `allowBuilds`.

## Evidence (gkms-contest-ai, `develop` at bb0bcae)

- **#119 A.**
  - `coord/handover-119-claude-lessons.md` (in `coord/`, which git ignores): the user's choice in the coordinator's cell, 2026-10-18 06:45.
  - Source: `docs/plans/EXECPLAN_GKTOOLS_COMPARE.md` Milestone 6, Python 3.13.7. A same-size mutation of `autoplay_sim.py` left the restored run failing.
  - The predictions were committed at 7f99ed8 before a 5 h 46 min run, and every figure held. Two outputs no manifest named were found, among them `sweep_results.csv`, with 140 of 792 margins moved.
- **The assessment.** `docs/reviews/2026-10-20-external-assessment.md` § 2:
  - about 30 job-hours of checking against 1.7 h of evaluation work, 10-15 → 10-18;
  - 351 of 438 sessions were per-commit security reviews;
  - progress times were typed without the clock more than 15 times, 6 after a rule;
  - hooks ran editable worktree scripts outside the sandbox for about 21 h;
  - the sampled verify left about 97.5 % of rows unchecked between whole-grid runs;
  - permission was granted by parsing shell text.
- **The decisions built on it.**
  - ADR 0009 and its 2026-10-23 amendment; `docs/plans/EXECPLAN_COORDINATION_LOOP.md` Milestone 3c.
  - ADR 0017; `docs/plans/EXECPLAN_LEAN_LOOP.md`, observations at its lines 40–42 and the verify stamp. The stamp is `tools/verify.py` `write_stamp` / `covering_stamp`, keyed on `HEAD^{tree}`.
  - `docs/PARALLEL_SESSIONS.md` § Processes: 18 prompts from `ps`/`pgrep` after the board's note.
  - `coord/lean-loop-notes.md`: the measured `settings.local.json` loading and the allow-rule questions.

## Decision Log (session 2026-10-26)

- **#119 A's fix corrected by measurement.** The handover said "run with `python -B`, or delete `__pycache__`". In a scratch directory with Python 3.14.9, mutating `X = False` → `X = True ` (same size):
  - plain runs, mutate after more than a second, restore in the same second: the restore printed `True`. That is the reported failure.
  - a normal run, then the mutant and the restore under `-B` in the same second: `False False False`. The mutant never ran, because `-B` stops writing and not reading.
  - `-B` from an empty cache, a fresh `PYTHONPYCACHEPREFIX` per run, or deleting `__pycache__` before each run: `False True False`.
  
  Apple's `/usr/bin/python3` 3.9.6 did not reproduce it: its `sys.pycache_prefix` is `~/Library/Caches/com.apple.python`, which the sandbox does not let it write. The note gives deletion or a fresh prefix, and says why `-B` is not enough.
- **A new stack note, not more `CLAUDE.md`.** These are reference facts to read before writing hooks, permission rules or sandbox settings, which is how stack notes are used, and `CLAUDE.md` stays thin. The two Quality Gates bullets do go in `CLAUDE.md`: they govern every session's own conduct and process, all the time.
- **Additive.** Nothing existing is replaced. The permission entry bans *granting* by text parsing. `hooks/git_gate.py` only ever returns `ask` or stays out of the way, so the entry cites it as the acceptable form rather than contradicting it.
- **Found and not fixed: this harness breaks the new first rule.** A sandboxed `touch hooks/.write-probe` in this checkout succeeded (2026-10-26). Meanwhile `~/.claude/settings.json` runs `$HOME/Developer/claude/hooks/git_gate.py` outside the sandbox before every Bash call of every session. The reach is wider than this repository: `sandbox.filesystem.allowWrite` opens `~/Developer/claude` to every session on the machine (`README.md`, the `mv` bullet). So any sandboxed session can change code that then runs unsandboxed in all sessions, and so does checking out a branch here. There are two ways out:
  - deploy a copy the way `git-hooks/install-global.sh` does;
  - add a deny rule, which would also stop the hook being developed in this checkout.
  
  Both change `settings.json`, which the user keeps by hand (ADR 0002). Put to the user, not decided here.
- **Not captured.**
  - The tooling (`stamp.py`, `heavy.py`, `brief_check.py`, the board, the worker scripts) waits for a second project that wants parallel sessions.
  - The package-manager question for worktree-heavy repositories was first put to the user separately. The user then asked for it in this PR; see the next entry.
- **pnpm under the sandbox, measured 2026-10-26.** pnpm 12.15.0 ran through `npx` in a scratch directory under `$TMPDIR`, in Claude Code 2.1.310, with `npm_config_cache` in `$TMPDIR`. Nothing was installed on the machine.
  - Default settings: `pnpm store path` gave `/private/tmp/claude-501/.pnpm-store/v11`, the nearest writable directory above the project, not `~/Library/pnpm/store`. The install exited 1 with `ERR_PNPM_STORE_DIR_OPEN_OPERATION_LOCK … Operation not permitted`: the lock directory falls back to `/tmp`, which the sandbox does not let it write.
  - With `XDG_RUNTIME_DIR` set to a mode-700 directory and `--store-dir` set, two installs succeeded. pnpm printed "Packages are cloned from the content-addressable store to the virtual store". The same file in the two projects had different inodes with link count 1: clones, not hard links.
  - `pnpm_config_store_dir` gave the same `storeDir` in `node_modules/.modules.yaml` as the flag. Without `XDG_RUNTIME_DIR` the lock error came back even with the store set.
  - Not measured, taken from pnpm's docs:
    - the store inside the project (`node_modules/.pnpm-store`) when no directory above the project is writable;
    - the global virtual store and its trust warning;
    - `strictDepBuilds` and `allowBuilds`;
    - `minimumReleaseAge` 1440 being non-strict unless set explicitly;
    - Bun's default `clonefile` backend on macOS.
  
  This rests on one tiny dependency, so the disk saving on a real tree is not measured.
- **No ADR.** Prose, trivially reversible: it fails gate one.
- **Codex review, one pass on `origin/master...HEAD` at 2c3b965: CHANGES REQUESTED, three findings, all accepted.**
  - Medium: reusing a check by tree hash is sound only when the check's other inputs are equal too. `docs/testing.md` now says to pin toolchain, configuration and data outside git in the tree, or record and compare them.
  - Medium: hooks at the main checkout's paths meet the rule only if those copies are themselves write-protected. `docs/claude-code.md` now requires the deny rule with them.
  - Low: the `.pyc` claim holds for timestamp-based pycs, CPython's default, and the text now says so.
  
  Two fixes of this session's own reading went in with them: the same-second condition is tied to the file's previous write, not the previous run, and a missing "were" in the second Quality Gates bullet. The snapshot's base was first fetched from the local `master` (9 commits behind), which put merged work in the diff. It was re-fetched from `refs/remotes/origin/master` before Codex ran. The repository check found no ref moved and no working-tree file changed. `.git/index` was refreshed during the run, with no Codex command against the repository in its log.

## Verification

- Each fact was measured or read on 2026-10-26, not copied:
  - the `.pyc` runs above;
  - `ps` (`operation not permitted`), `pgrep` (`Cannot get process list`) and `lsof -d cwd` (works) under the sandbox, Claude Code 2.1.310;
  - the permissions page (§ Compound commands, § Wrappers, where `.claude/settings.local.json` loads from) and the sandboxing page (what runs outside the sandbox; `Read` and `Edit` deny rules merged into its restrictions) at code.claude.com.
- No path, document or section name from gkms-contest-ai appears in the shared guidance changed here; the evidence above is the only place it is cited.
- Prose only, no test to run. After the merge, read the edited sections through `~/.claude`, which is symlinked.
