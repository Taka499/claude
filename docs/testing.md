# Testing doctrine — cross-stack

Distilled from the source article for this harness (Isamu, 「1日500コミットは、もう読めない ── だからコードレビューをやめた」, zenn.dev/singularity, 2026-07-27) and cross-checked against this user's own projects. Read before writing or refactoring tests, in any language. Stack notes (`rust.md`, `typescript.md`, `python.md`) carry the per-toolchain specifics.

## Design for testability first

Extract rules — filtering, ordering, limits, validation, formatting, retention — into pure functions in their own files. File I/O, process spawning, sockets, and HTTP stay at the call site. A rule that can only be reached by booting the app will not be tested.

At boundaries where purity is impossible, pass the dependencies as arguments: the clock (`now()`), validators, feature probes, home-directory paths, and the **platform** (`fn(path, "win32")` beats reading `process.platform`/`cfg!` inside — it lets you test Windows behavior on any machine instead of waiting for Windows CI). A module that grabs a clock or a process at import time cannot be tested without touching the developer's machine; treat that as a design defect, not as "hard to test".

**Apply this to EXISTING code, not only new code.** When touching a large file, look for pure rules already buried in it and extract + test them as part of the work. Testable is a property of the codebase to actively restore, not a rule that binds only new lines. Periodic passes with `/code-review` and `/simplify` are the mechanism.

## The pattern checklist

When writing tests for a function, cover explicitly:

1. Happy path
2. Edge cases (strange but valid input)
3. Corner cases (multiple edges combined)
4. Boundary values (min/max, off-by-one)
5. Empty (string, array, object)
6. null / undefined / None
7. Invalid input (wrong type, corrupted data)
8. Errors (where an exception should be thrown)
9. Negative (things that must NOT happen)
10. Regression (bugs that actually occurred)

## Verify the test actually fails

A new test must be shown to go red when its target is broken: invert the condition, delete the guard, or revert the fix — watch it fail — restore. A test that passes against broken code is testing something else, and this is invisible unless checked.

Assertion-less tests are a lint error, not a review comment (`sonarjs/assertions-in-tests` in TS; the same idea applies in any stack).

The same holds for a check, not only a test: before trusting a "did the output change?" guard, ask which inputs differ between its two sides. If both sides are recomputed by the same checkout — same code, same configuration — and the rule is "unchanged input must give unchanged output", the guard is a tautology: a pure function cannot disagree with itself, so it stays green through exactly the engine or configuration change it exists to catch. One side has to be a stored fact from the past — a committed snapshot of the published outputs, a golden file over frozen inputs — that the run under test does not regenerate. Then prove it the usual way: change one number by hand and watch it go red. (gakumas-supportcards: a score-stability gate specified as "compare committed and fresh data" could never have failed; the committed score snapshot that replaced it flagged 31 cards for one hand-edited route number.)

**When a run that takes hours regenerates committed outputs, commit what it should produce before it starts.** Measure with faster tools what the change will do to each committed output, commit those predicted values, then compare the run's output with them. A prediction committed before the run tests the run; one written after it only copies it. Measure every committed output the change can move, not only the list a manifest or plan expects to move: that list is a prediction too, and it can miss an output. (gkms-contest-ai, 2026-10-17: a 5 h 46 min regeneration matched every committed prediction, and measuring all outputs first found two that neither expected-change list named, one of them 140 of 792 rows with a changed margin.)

## Prioritize by how silently it fails

Functions that throw report themselves. The dangerous ones return plausible wrong values: off-by-one indices, bytes-vs-chars confusions, shifted dates, case-mismatched extensions, too-lenient validators, prototype-chain lookups. These stay invisible until a user notices — test them first.

## Scope expensive checks by risk

**When the full check takes hours, scope each run by what changed, and let a record of a verified tree stand in for a rerun.** Run the check at the scope the changed paths call for: documentation alone runs no expensive step. When every check passes on a clean working tree, record the tree's hash (`git rev-parse HEAD^{tree}`) and the scope that ran. A later run on the same tree, such as a merge whose result equals the branch that was verified, reuses that record instead of running again. Key the record on the tree, not the commit: a merge commit has a new hash and can have the same tree. The tree is a sufficient key only when it holds every other input to the check: toolchain and dependency versions, configuration, and any data kept outside git. Pin those in the tree (a lockfile, a manifest of the data's hashes) or write them into the record and compare them too; otherwise the same tree can give a different result. Run the full check regularly while nothing else runs, say where results are reported which full run they are current as of, and keep a hash per row of the full results so that a rebuild names what it changed. The price is that a drift can pass a scoped or sampled run until the next full one, so the full run has to actually happen. (gkms-contest-ai, 2026-10-20: before the change, three days held about 30 job-hours of checking against 1.7 h of the work it guarded; its sampled merge check left about 97.5 % of result rows unchecked between full runs.)

## Machine-checkable beats review-catchable

The premise of this whole harness: most of what a reviewer would say — too long, too nested, too many params, swallowed catch, assertion-less test — a machine can say as a lint error (see `CLAUDE.md` § Quality Gates). Reserve human/agent review attention for what machines cannot check: whether the spec is right, and whether the thing feels right when used.
