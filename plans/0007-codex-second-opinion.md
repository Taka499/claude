# Plan: A Codex second opinion, and the review loop deliberately not taken

## Goal

This repository emulates [isamu/claude](https://github.com/isamu/claude)'s delivery mechanism — global config in a repo, every change a PR — but adopted only half the thesis of the article it came from. 「コードレビューをやめた」 stops human review by handing review to *other models*; here, every PR so far has been reviewed by the same agent that wrote it. This adds the missing half in its smallest honest form: a skill that asks Codex for a second opinion on a local diff before it becomes a PR.

## What was imported, and what was not

isamu's repository has two Codex skills. Only the shape of the smaller one is adopted, re-expressed in this repository's own terms and vocabulary (that repository states no license — see `README.md` § Attribution, which already binds this repo to restating rather than copying).

| | `codex-local-review` (93 lines) | `codex-cross-review` (~780 lines) |
| --- | --- | --- |
| Reviews | a local diff | an open GitHub PR |
| Codex writes | nothing | inline + top-level PR comments |
| Needs | the `codex` CLI | gh, CI, bot reviewers, a Codex sandbox proven able to run tests and bind sockets |
| Ends with | a report | `gh pr merge` |
| Adopted | the shape, rewritten | **no** |

Four reasons the cross-review loop is rejected, recorded so this is not re-litigated as an oversight:

1. **Its calibration is not transferable.** It is tuned on 91 measured loops (mean 7.4 rounds) against repos with CI and bot reviewers, optimising an arithmetic — a fix pushed in round N is first reviewed in N+1 — that only pays when a round costs a CI cycle. A round in this repository is a `git diff`.
2. **It merges.** `gh pr checkout`, pushes throughout, `gh pr merge` at the end. That contradicts `CLAUDE.md` § Git Operations, which requires explicit permission per history-mutating operation.
3. **It is pinned to an environment that has already drifted.** It hardcodes `--model gpt-5.5` and a `sandbox_workspace_write.network_access=true` override against Codex CLI v0.137.0; the CLI installed here is v0.40.0. Re-deriving 780 lines is not importing.
4. **Size.** A 93-line skill can be honestly re-expressed; 780 lines cannot be, and a verbatim copy is not available to us.

## The decision that needed making: how Codex reaches the network

`codex exec` cannot run inside the Bash sandbox. Measured in-session, both `api.openai.com` and `chatgpt.com/backend-api/codex` fail with `ENOTFOUND`, because `sandbox.network.allowedDomains` lists GitHub and the package registries only.

Two ways out, and they are not equivalent:

- **Add OpenAI's hosts to `allowedDomains`** — Codex runs sandboxed like everything else, at the cost of widening egress permanently, for every command, including ones executing content nobody in this repo wrote.
- **Run the call with `dangerouslyDisableSandbox: true`** — chosen. Nothing widens; the existing `Bash(dangerouslyDisableSandbox:true)` ask rule turns each review into one decision the user makes. Codex's own `--sandbox read-only` still applies, since the two sandboxes are separate layers.

The larger exposure is not the sandbox either way: the diff and any file Codex reads for context are sent to a third party. The skill leads with that rather than burying it, and the settings file is unchanged by this plan.

> **Superseded, 2026-08-29** by [`plans/0008-codex-read-boundary.md`](0008-codex-read-boundary.md). The residual risk stated at the close of this plan — "documented, not enforced" — was written from reasoning, not measurement. Measured, the boundary is wider than described, the documented allowlist profile does not work in this build, and two further risks (training on individual plans; the reviewer as an input path) went unnamed here. Read 0008 for the probes and the recommendation order.

## Changes

- `skills/codex-review/SKILL.md` — new. Read-only `codex exec`, forced verdict marker, mandatory evaluation of every finding, and an explicit prohibition on committing or pushing from the skill.
- `README.md` — skill listed; attribution bullet for the borrowed shape; the settings invariant about `Read(...)` denies corrected (below).
- `CLAUDE.md` — added to the skills index.

## Correction to a settings invariant

The README claimed `Read(...)` deny rules and the sandbox "cover different paths — neither one covers the other's". That understates them. Per the [sandboxing docs](https://code.claude.com/docs/en/sandboxing), *"paths and domains from both sandbox settings and permission rules are merged into the final sandbox configuration"*, and this session's own resolved sandbox config contains `id_rsa`, `**/*token*`, `**/build`, `**/archived` and `./.dev.vars` — entries that exist nowhere in the `sandbox` block and come from `permissions.deny`. So the `Read` denies *do* bind Bash.

What stays true is the practical advice, for a different reason: a `.key` file created under `$TMPDIR` was readable, so the unanchored `**/*.key` form does not cover the machine. The `~/**/*.key` entries in `sandbox.filesystem.denyRead` are what give that coverage. Both lists earn their place; the old wording gave the wrong reason.

## Verification

- `codex --version` → `codex-cli 0.40.0`; `codex exec --help` confirms `--sandbox read-only` exists in the installed build.
- **The skill was run against its own diff and could not complete.** `codex exec` reached the API and was refused: `400 … The 'gpt-5-codex' model is not supported when using Codex with a ChatGPT account`, identically for `gpt-5`, `gpt-5.1`, `gpt-5.1-codex` and `gpt-5.5-codex`. Every name fails the same way, including the CLI's own default, and `codex login status` reports *Logged in using ChatGPT* throughout. Two causes share this message and were separated by testing both: re-authenticating with `codex login` succeeded and changed nothing, while `npm view @openai/codex version` returned **0.150.1** against the installed **0.40.0**. The published entitlement reports ([openai/codex #17642](https://github.com/openai/codex/issues/17642), [#19654](https://github.com/openai/codex/issues/19654)) describe *specific* models refused on current builds; refusal of every model including the default is the version signature instead. **Resolved**: upgraded to v0.150.1 and re-authenticated, after which preflight returned `PING-OK`. The failure earns its place in this record. Note it was **loud** — an explicit `400` on every call — which is the opposite of the silent no-output failure isamu documented for a pinned model. Same lesson, inverted symptom: the preflight has to prove a model *answers*, because either symptom means the review cannot run, and only one of them is visible. That is what put the live PING and the scope-based diagnosis into the skill.
- **Dogfooded on its own diff** (`git diff origin/master`), which is the acceptance evidence for this plan. Codex returned `CODEX VERDICT: CHANGES REQUESTED` with six findings. Three were accepted as MUST-FIX and fixed on this branch: that `--sandbox read-only` bounds Codex's *writes* and not its *reads*, so the data-exposure warning was checking the wrong thing; that `README.md` still said secrets are protected "not by `permissions.deny`" one bullet above the new text saying those denies are merged into the sandbox; and that the verdict contract asked for a line that both ended the response and was followed by the findings — Codex complied by emitting the verdict block twice, which is the ambiguity made visible. Two more were accepted as cheap nits (name where a rejected finding is recorded; narrow `plans/0006`'s "skills and setup scripts are fine sandboxed", which is true of editing those paths and false of running `setup.sh`). One INFO on skill-trigger overlap needed no action; none were rejected.

  The HIGH finding is the argument for the whole skill: it contradicted a safety claim the author had written and re-read twice without seeing, which is exactly what a reviewer sharing the author's priors cannot do.

  A second round on the fixes confirmed all five and found two more, both accepted: `plans/0005` still asserted the pre-correction claim about `Read(…)` denies (appended there as a dated correction, per the immutability convention), and this plan called the loud `400` a silent failure. The round-2 verdict also validated the contract fix — one verdict line, genuinely last.
- Network probe from sandboxed Bash: `api.openai.com` and `chatgpt.com/backend-api/codex` both `ENOTFOUND`.
- Both isamu skills read in full from `isamu/claude` before deciding; nothing copied verbatim.
- `./setup.sh` re-run so the new skill is linked into `~/.claude/skills/`. The sandboxed run failed at exactly the new link — `ln: /Users/ghensk/.claude/skills/codex-review: Operation not permitted` — while reporting every pre-existing link healthy; re-run outside the sandbox, it linked. `~/.claude/skills` is itself an agent-config path, so `setup.sh` needs the sandbox off whenever it has a link to add or prune. This is the first change since ADR 0003 to add a skill, which is why it had not surfaced; `README.md` § Git in this clone corrected accordingly.

## Decision Log

- **Single skill, not two.** A local-diff gate is the piece that fits a repo with no CI. If a PR-stage loop is ever wanted, it should be written for this environment rather than ported.
- **No `--model` pin.** Directly from isamu's recorded failure: a pinned model the CLI stops accepting fails silently, and a silent failure reads as a clean review.
- **The skill never commits.** Every other skill here that ends in an action asks first; a review gate that also ships is not a gate.
