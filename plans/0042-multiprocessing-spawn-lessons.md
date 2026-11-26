# Plan: Three lessons about process pools and the spawn start method

Issue #70.

## Goal

On 2026-11-24 a scratch script in gkms-contest-ai filled the disk through a loop that nothing reported. The user asked on 2026-11-26 ("Do both of report and lesson pls") to record its lessons in the Python stack note:
- `multiprocessing.Pool` hangs forever when its workers die at start-up, and silently keeps replacing them;
- under the spawn start method each child re-imports the parent's main script, and the only reliable in-child test is a private flag;
- setup that needs cleanup belongs inside the `try` whose `finally` cleans it up.

## Changes

- `docs/python.md`: a new § Process pools and the spawn start method, before § Working with an LLM stage inside a pipeline, with one paragraph per lesson.

## Evidence

- **The incident** (gkms-contest-ai, 2026-11-24, its issue #149 and `docs/plans/EXECPLAN_ENGINE_DIFF_LEAK.md`):
  - A scratch wrapper script ended with an unguarded `sys.exit(ED.main(argv))` and imported `tools/engine_diff.py`, which creates its pools with `multiprocessing.get_context("spawn")`.
  - Each spawned worker re-imported the wrapper as `__mp_main__` and ran `main()`. That `main()` made a 62 MB `git archive` copy of the repository in a `mkdtemp` folder, then tried to create its own pools, which multiprocessing refused during bootstrap with a `RuntimeError`. The pool creation sat outside the `try` whose `finally` ran `rmtree`, so the copy stayed.
  - The worker died, the parent's `Pool` replaced it, and the replacement did the same: about one copy a second for 2 h 17 min. 9,212 copies, about 570 GB, filled the disk; every session hit ENOSPC, and the terminal app lost its cells.
- **The fix there** (branch `feature/engine-diff-leak`):
  - `tools/engine_diff.py` refuses to run in a child before any copy, testing `multiprocessing.parent_process()` and `current_process()._inheriting`, and moves the copy and the pool creation inside the `try`.
  - `worker_pool.py` subclasses `multiprocessing.pool.Pool`: its `Process` hook counts created workers and sets an event once more than `processes` were created; it refuses `maxtasksperchild`; every wait polls every 0.2 s and raises `WorkerDied` once the event is set.
  - A bounded test of the wrapper: 1,477 copies in 60 s before the fix; 0 copies and an error in 0.28 s after.
  - `tests/test_engine_diff_leak.py` measures, by spawning one child from a script that prints at import, that `parent_process()` is `None` and `_inheriting` is `True` while the child imports `__mp_main__`; it pins the private flag.
- **Re-measured for this note,** 2026-11-26, Homebrew Python 3.14.10, from scripts under the session's scratch root:
  - A spawn `Pool(1)` whose worker raised at import: about 100 workers (`SpawnPoolWorker-1` … `-99` printed) before `map_async(...).get(timeout=6)` raised `multiprocessing.context.TimeoutError`. Nothing else was raised.
  - A spawn `Pool(1)` whose `initializer` raised: the initializer ran 101 times before `.get(timeout=5)` gave up.
  - `ProcessPoolExecutor(1, mp_context=spawn)` with the same failing import: `BrokenProcessPool` on the first death, one worker started.
  - Every child printed `parent_process=None _inheriting=True` during its import of the main script.
  - In CPython 3.14's `multiprocessing/spawn.py`, `prepare` sets `current_process()._inheriting` and `_check_not_importing_main` reads it to refuse starting a child during bootstrap; `pool.py` creates every worker through `Process(ctx, …)`, called from `_repopulate_pool_static`.

## Decision Log (session 2026-11-26)

- **The stack note, not `CLAUDE.md`.** Reference facts for anyone writing multiprocessing code, read before that work.
- **A section of its own,** after § Configuration and CLI shape for batch tools, since none of the existing sections is about processes.
- **Additive.** Nothing existing is replaced.
- **The wrapper is described, not shipped.** The note gives the three moves that make it work (the `Process` hook sets an event, `maxtasksperchild` refused, waits poll), including why the hook must not raise: it runs on the pool's handler thread.
- **The shared text names no path of the source project,** only "(gkms-contest-ai, 2026-11-24)", per global `CLAUDE.md` § Continuous Learning. The paths above are history.
- **No ADR.** Prose, trivially reversible.
- **`/codex-review` (codex-cli 0.150.1, verdict CHANGES REQUESTED), answered:**
  - *Rejected:* "the wrapper falsely reports a death during a normal `Pool.close()`, because a worker can take its sentinel and be replaced while results are still cached". In CPython 3.14.10's `pool.py`, `_handle_workers` keeps maintaining the pool while the cache is non-empty and puts the stop sentinel on the task queue only after that loop exits, so no worker gets a sentinel while results are pending. Measured: 30 trials of a spawn `Pool(4)` subclass counting `Process` calls, `map_async` over 200 tasks, `close()` before `get()`: at most 4 workers created.
  - *Rejected:* "`Pool.Process` is a regular instance method". `inspect.getattr_static(Pool, "Process")` is a `staticmethod` in 3.14.10; the note now says so and why an ordinary-method override still works (the pool calls `self.Process`).
  - *Accepted:* the first `processes` workers are created in `Pool.__init__` on the caller's thread, only replacements on the worker-handler thread; the note says so.
  - *Accepted:* Python 3.14 made `forkserver` the Linux default. `forkserver.py` imports the main script once in the server with `_inheriting` set; the note adds that as a parenthesis.

## Verification

- `git diff origin/master -- docs/python.md` adds one section and changes no existing line.
- No path inside another project appears in `docs/python.md`.
- Read the section through `~/.claude/docs/python.md` after the merge.
