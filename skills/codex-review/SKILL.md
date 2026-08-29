---
name: codex-review
description: Get a second opinion on a local diff from Codex (OpenAI) before it becomes a PR. Runs `codex exec` read-only over the working-tree or branch diff under a forced-verdict contract, then evaluates every finding rather than applying it. Use when the user asks for a "second opinion", "codex review", "have Codex look at this", or before committing anything whose failure mode is expensive — permissions, secrets handling, destructive operations, or any claim that behaviour is unchanged.
---

# Codex Review

A pre-commit second opinion from a model that does not share this one's priors. Codex reads the diff read-only; you evaluate what it says. Nothing is committed, pushed, or posted.

The point is **disagreement, not coverage**. Another pass by the same reviewer finds the same things — the value here is that Codex was trained differently and will object to things this agent considers settled. Treat a finding you immediately want to dismiss as the most interesting one on the list.

## Before running it: what leaves the machine

`codex exec` sends the diff **and whatever files Codex reads for context** to OpenAI. That is the real cost of this skill, and it is not covered by any Claude Code sandbox setting.

So: never run this in a repository whose working tree holds credentials, customer data, or anything under an NDA. Check what the diff touches first, and say plainly to the user which repository is about to be sent out if there is any doubt. A `.env` sitting next to the diff is not in the diff, but it is one `cat` away for a reviewer that is allowed to read for context.

## Preflight

1. `command -v codex` — if missing, stop and tell the user to install `@openai/codex`. Do not fall back to reviewing it yourself and calling it a Codex review.
2. Check the flags against the installed version rather than assuming: `codex exec --help`. `--sandbox read-only` is the one this skill depends on. **Do not hardcode a `--model`** — a pinned model that the installed CLI has stopped accepting fails by producing no output and a near-silent exit, which is indistinguishable from a clean review.

## Network: this runs outside the Claude Code sandbox

The Bash sandbox's `network.allowedDomains` does not include OpenAI's hosts, so a sandboxed `codex exec` cannot reach the API — measured, it fails as `ENOTFOUND`, not as a clean error. Run the call with `dangerouslyDisableSandbox: true`.

That is deliberate, not a workaround. The alternative — adding the hosts to `allowedDomains` — widens egress for *every* command from then on, while the unsandboxed retry hits the `Bash(dangerouslyDisableSandbox:true)` ask rule and puts one review in front of the user as one decision.

Note the two sandboxes are different layers: turning off Claude Code's does not turn off Codex's. `--sandbox read-only` still stops Codex writing to the tree, and it is mandatory here — this is a review, not a second author.

## Steps

### 1. Scope the diff, and say what you scoped

- uncommitted work → `git diff`, plus `git diff --staged` if anything is staged
- a branch → `git diff <base>...HEAD`, resolving `<base>` from the repo's default branch

**The diff must contain only the intended change.** A stray formatter run or an unrelated edit buries the real change, and Codex will spend its whole review on the noise. Clean it up first, or narrow the paths.

### 2. Run Codex

```bash
codex exec --sandbox read-only "Review ONLY the change described below in this repository.
Run \`git diff <paths>\` to see it and read surrounding files for context. Do NOT modify anything.

INTENT: <what this change is for, and what must stay true after it>

Answer these specifically:
1. <the thing you actually fear about this change>
2. <the invariant that must not have moved>

End with exactly one line: 'CODEX VERDICT: LGTM' or 'CODEX VERDICT: CHANGES REQUESTED',
followed by one bullet per finding with a severity."
```

Three things decide whether this call is worth anything:

- **State the intent.** A diff does not say what invariant it was protecting. Without it Codex reviews the code that is there against no standard, and returns style notes.
- **Ask what you actually fear**, not "review this". Generic prompts return generic prose. Name the thing: does the happy path still produce identical output, does a retry double-apply, does removing this guard swallow an error that should surface.
- **Force the verdict line.** Without the contract you get an essay you cannot act on, and no way to tell a clean review from an inconclusive one.

Codex output is long — read the tail for the findings and the verdict. If the call outlives the harness's per-call ceiling, run it in the background rather than shortening the prompt.

### 3. Evaluate every finding — this is the step that is not optional

For each one, in this order:

1. **Is it real?** Verify it against the code before accepting it. Codex cannot see the intent you did not write down.
2. **Does it generalise?** If the finding names a class of mistake, fix the class. A one-site fix that leaves three identical sites is worse than the finding, because it looks handled.
3. **What does the fix break?** A suggestion that satisfies the finding and regresses a caller is not an improvement.
4. **What did it miss?** Read the diff yourself as well. Codex is a floor, not a ceiling.

Sort into MUST-FIX / VALID-NIT / FALSE-POSITIVE / DEFER. Apply the MUST-FIX items and the cheap nits. **Where you disagree, write down why** — a rejected finding with no recorded reason comes back next time and gets rejected again with no more evidence than the first time.

### 4. Re-run only if the logic moved

Material change to what the diff does → run step 2 again, so the verdict covers what will actually ship. Comment and naming changes → don't.

### 5. Run the repo's own gates, then report

Whatever the project's `CLAUDE.md` names — build, lint, typecheck, tests. Do not run a repo-wide formatter unless the repo is already format-clean; it rewrites unrelated files and turns a reviewable diff into an unreviewable one.

Then report, in one message:

- what was reviewed, and what was deliberately out of scope
- the Codex verdict, verbatim
- your evaluation: accepted, rejected with reasons, and anything Codex missed
- residual risk the change does *not* address
- gate results

Then ask whether to commit. **Never commit, push, merge, or open a PR from this skill.** It is a gate, and a gate that also ships is not a gate.

## Honesty rules

- Findings you made are yours. Do not launder your own review through Codex's name — in the report or in a commit message.
- A Codex LGTM is a data point, not a permit. If your own reading found a MUST-FIX, say so and fix it; two reviewers agreeing on a bug still leaves the bug.
- Report an inconclusive run as inconclusive. A `codex exec` that produced no verdict line did not return LGTM, and the difference is the whole reason for the contract in step 2.
- Distinguish "this change adds no new risk" from "this code is now safe". Pre-existing problems the diff does not touch get named, not implied away.

## When this repository is the subject

Reviewing a change to a Claude Code configuration is not a code review, and the questions have to change with it. Ask whether a new permission rule is anchored, whether a rule contradicts one already in the file, whether a documented invariant still matches what the settings actually do, and whether the change is enforced anywhere or is only prose. Codex has no way to guess that a `Bash(...)` pattern matches the whole command string — put it in the prompt.
