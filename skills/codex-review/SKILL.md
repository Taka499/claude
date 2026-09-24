---
name: codex-review
description: Get a second opinion on a local diff from Codex (OpenAI) before it becomes a PR. Runs `codex exec` over the working-tree or branch diff with no write access, under a forced-verdict contract, then evaluates every finding rather than applying it. Use when the user asks for a "second opinion", "codex review", "have Codex look at this", or before committing anything whose failure mode is expensive — permissions, secrets handling, destructive operations, or any claim that behaviour is unchanged.
---

# Codex Review

A pre-commit second opinion from a model that does not share this one's priors. Codex reads the diff read-only; you evaluate what it says. Nothing is committed, pushed, or posted.

The point is **disagreement, not coverage**. Another pass by the same reviewer finds the same things — the value here is that Codex was trained differently and will object to things this agent considers settled. Treat a finding you immediately want to dismiss as the most interesting one on the list.

## Before running it: what leaves the machine

`codex exec` sends the diff **and whatever files Codex reads for context** to OpenAI. That is the real cost of this skill. No setting prevents the diff itself from leaving — that is what you asked for. What a setting can change is how much else travels with it, which is the subject of the rest of this section.

**The exposure is wider than the repository, and checking the diff does not bound it.** Codex's own `--sandbox read-only` mode stops it *writing*; it does not confine its *reading*, which is why this skill does not rely on it. Measured: from a workspace inside this repo, Codex read a decoy under `$TMPDIR` and counted 63 entries in `$HOME`, while a write was refused. Those probes establish that reads reach **beyond the workspace** — no more than that. That the practical boundary is **anything readable by your user account** is inferred from the documented design, whose filesystem controls govern writes only. Plan against the inference; it is what the design implies, but three probes did not prove it.

What narrows it is the *outer* sandbox: run inside Claude Code's, as the section below requires, `sandbox.filesystem.denyRead` and `sandbox.credentials.files` do bind the Codex process and its children. Codex's own read-only mode contributes nothing here.

This is known upstream and closed without a fix ([openai/codex#4410](https://github.com/openai/codex/issues/4410)). Mitigations and the probes behind them are in [`plans/0008-codex-read-boundary.md`](../../plans/0008-codex-read-boundary.md); the strongest is to run Codex *inside* Claude Code's sandbox, which is what the next section requires and what this machine is now configured for.

**And it may not stop at reading.** On individual ChatGPT plans, Codex content may be used for training unless opted out, reportedly under a Codex-specific control separate from ChatGPT's data settings. **Treat that as unverified** — it comes from secondary reporting, not a primary source that could be fetched — and confirm it in account settings rather than repeating it. Confirm it *before* reviewing anything private: of the exposures here it is the hardest to undo once it has gone wrong, and opting out still says nothing about what other retention applies.

So: never run this on a machine or in a repository where that is unacceptable — credentials, customer data, anything under an NDA. Say plainly which repository is about to be sent out if there is any doubt, and keep the prompt scoped to the diff so the reviewer has no reason to wander. A `.env` beside the diff is not in the diff, but it is one read away.

## Preflight

1. `command -v codex` — if missing, stop and tell the user to install `@openai/codex`. Do not fall back to reviewing it yourself and calling it a Codex review.
2. Check the flags against the installed version rather than assuming: `codex exec --help`. `--sandbox` and its accepted values are what this skill depends on. **Do not hardcode a `--model`** — a pinned model that the installed CLI has stopped accepting fails by producing no output and a near-silent exit, which is indistinguishable from a clean review.
3. **Prove it can answer at all**, with a call that costs nothing:

   ```bash
   codex exec --sandbox danger-full-access "Reply with exactly: PING-OK" < /dev/null
   ```

   **`< /dev/null` is not optional, here or below.** Without it `codex exec` can block reading stdin — it prints `Reading additional input from stdin...`, which a pipe into `tail` hides completely, so the call looks like a hang with no output. Two multi-minute stalls in this skill's own development were exactly that.

   An installed binary with the right flags can still reach no model. Measured here: every model name was refused with `400 … model is not supported when using Codex with a ChatGPT account`, including the CLI's own default.

   The error names the *model*, which invites a hunt through model names. It is never worth more than one retry, because two different causes wear the same message and the *scope* of the refusal tells them apart:

   - **Some models refused, the CLI's default works** → an account-entitlement mismatch, widely reported ([openai/codex #17642](https://github.com/openai/codex/issues/17642), [#19654](https://github.com/openai/codex/issues/19654)). Re-authenticating with `codex login` is the remedy people report.
   - **Every model refused, including the CLI's own default** → the CLI is too old for the account type. Check it: `npm view @openai/codex version`. Measured here, v0.40.0 against a latest of v0.150.1 — 110 versions — refused every name, and re-login changed nothing.

   `codex login status` distinguishes neither: it reports *Logged in using ChatGPT* while every request is refused. Diagnose by scope, not by the error text.

   Never let this step's failure become the review. A skill that cannot run reports that it could not run.

## Sandboxing: this runs INSIDE the Claude Code sandbox

Run `codex exec` as an ordinary sandboxed command. **Do not pass `dangerouslyDisableSandbox`** — that is the whole point of the arrangement. `sandbox.filesystem.denyRead` and `sandbox.credentials.files` are enforced by the OS on the Codex process *and its children*, so the read boundary above is narrowed by Claude Code rather than entrusted to Codex's own configuration, which a CLI upgrade or a typo can silently drop.

**Turn Codex's own sandbox off — `--sandbox danger-full-access` — and let Claude Code's be the only one.** The two cannot nest: Codex's `read-only` mode shells out through `sandbox-exec`, and inside Claude Code's Seatbelt every command it runs dies with `sandbox-exec: sandbox_apply: Operation not permitted`. A review whose reviewer cannot run `git diff` is worth nothing.

Nothing is lost by dropping it, because the outer sandbox already covers both directions. Measured, running this way:

| Probe | Result |
| --- | --- |
| `head -1 README.md` in the workspace | works |
| write to `~/should-not-be-writable.txt` | **REFUSED** |
| read `~/.ssh/config` | **REFUSED** |

Note the flag's name is actively misleading here: `danger-full-access` grants full access *relative to the inner sandbox*, which is itself inside the outer one that constrains it. This is the most protected configuration available, reached through the most alarming flag.

It needs two entries in `~/.claude/settings.json` (untracked per ADR 0002 — the invariants live in `README.md`):

- **`sandbox.network.allowedDomains`** — `chatgpt.com` and `auth.openai.com` for a ChatGPT-plan login; `api.openai.com` instead under API-key auth.
- **`sandbox.filesystem.allowWrite`** — `~/.codex`. Without it Codex dies at startup, long before any network call, with `could not create PATH aliases` and `failed to initialize in-process app-server client: Operation not permitted`. That failure is filesystem, and it looks nothing like a blocked host — expect to misdiagnose it once.

**Do not add `~/.codex/auth.json` to `credentials.files`.** It was tried and it makes Codex unable to read its own credential: `credentials.files` protects a credential *from* sandboxed commands, and here Codex is one. There is no per-command exemption, so protecting that token and running Codex sandboxed are mutually exclusive — and the token was never protected before, so declining to protect it costs nothing that was previously held.

## Steps

### 1. Scope the diff, and say what you scoped

- uncommitted work → `git diff`, plus `git diff --staged` if anything is staged
- a branch → `git diff <base>...HEAD`, resolving `<base>` from the repo's default branch

**The diff must contain only the intended change.** A stray formatter run or an unrelated edit buries the real change, and Codex will spend its whole review on the noise. Clean it up first, or narrow the paths.

### 2. Run Codex

```bash
codex exec --sandbox danger-full-access -c 'approval_policy="never"' "Review ONLY the change described below in this repository.
Run \`git diff <paths>\` to see it and read surrounding files for context. Do NOT modify anything.

INTENT: <what this change is for, and what must stay true after it>

Answer these specifically:
1. <the thing you actually fear about this change>
2. <the invariant that must not have moved>

List one bullet per finding, each with a severity. Then end the ENTIRE response with
exactly one final line and nothing after it:
'CODEX VERDICT: LGTM' or 'CODEX VERDICT: CHANGES REQUESTED'." < /dev/null
```

Three things decide whether this call is worth anything:

- **State the intent.** A diff does not say what invariant it was protecting. Without it Codex reviews the code that is there against no standard, and returns style notes.
- **Ask what you actually fear**, not "review this". Generic prompts return generic prose. Name the thing: does the happy path still produce identical output, does a retry double-apply, does removing this guard swallow an error that should surface.
- **Force the verdict line, and put it last.** Without the contract you get an essay you cannot act on, and no way to tell a clean review from an inconclusive one. Asking for a line that both "ends" the response and is "followed by" the findings is not a contract — asked that way, Codex emitted the whole verdict block twice.

Codex output is long — read the tail for the findings and the verdict. That is the other reason the verdict goes last: it makes `tail` a contract rather than a guess. When waiting for the run in the background, wait for the process to exit or for a line that is *only* the verdict — never for the bare phrase, because Codex echoes the prompt into its log, and the prompt contains the phrase. A wait keyed on the phrase ends before Codex has read the diff. Anchor the match, but tolerate what a model adds around a line it was told to emit verbatim: the prompt displays the verdict in quotes, and quotes, leading or trailing space, `**bold**` or a CR each defeat a strictly bare pattern. `grep -qE "^[[:space:]]*['\"*]*CODEX VERDICT: (LGTM|CHANGES REQUESTED)['\"*.]*[[:space:]]*$"` accepts all of those and still rejects the echoed `'CODEX VERDICT: LGTM' or 'CODEX VERDICT: CHANGES REQUESTED'.` line, which is the one that must never match. Missing a real verdict is the safe direction — the wait falls through to process exit — but **a run that exits with no matching verdict is inconclusive**, and step 5 reports it as inconclusive, never as LGTM. If the call outlives the harness's per-call ceiling, run it in the background rather than shortening the prompt.

### 3. Evaluate every finding — this is the step that is not optional

For each one, in this order:

1. **Is it real?** Verify it against the code before accepting it. Codex cannot see the intent you did not write down. This step is also the security boundary, not only a quality one: Codex read repository contents that someone else may have written, and its findings arrive here as suggested edits. Untrusted content reaching your hands through a model is still untrusted content.
2. **Does it generalise?** If the finding names a class of mistake, fix the class. A one-site fix that leaves three identical sites is worse than the finding, because it looks handled.
3. **What does the fix break?** A suggestion that satisfies the finding and regresses a caller is not an improvement.
4. **What did it miss?** Read the diff yourself as well. Codex is a floor, not a ceiling.

Sort into MUST-FIX / VALID-NIT / FALSE-POSITIVE / DEFER. Apply the MUST-FIX items and the cheap nits. **Where you disagree, write down why — and where.** In the report of step 5 always; additionally in the plan file's Decision Log when the change has one, since that is the copy that outlives the session. A rejection recorded nowhere comes back next time and gets rejected again with no more evidence than the first.

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
