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

## Prioritize by how silently it fails

Functions that throw report themselves. The dangerous ones return plausible wrong values: off-by-one indices, bytes-vs-chars confusions, shifted dates, case-mismatched extensions, too-lenient validators, prototype-chain lookups. These stay invisible until a user notices — test them first.

## Machine-checkable beats review-catchable

The premise of this whole harness: most of what a reviewer would say — too long, too nested, too many params, swallowed catch, assertion-less test — a machine can say as a lint error (see `CLAUDE.md` § Quality Gates). Reserve human/agent review attention for what machines cannot check: whether the spec is right, and whether the thing feels right when used.
