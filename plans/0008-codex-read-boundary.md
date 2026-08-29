# Plan: What a Codex review can actually read, and the four risks behind one sentence

## Goal

`plans/0007` shipped `codex-review` with a single stated residual risk — "the data-exposure boundary is documented, not enforced" — written from reasoning rather than measurement. Measuring it changed the answer three ways: the boundary is wider than described, the control that would narrow it does not work in the shape the documentation suggests, and two further risks were not named at all. This records what was measured, so the next session inherits evidence instead of a caveat.

## What was measured

All with `codex` v0.150.1, `--sandbox read-only`, workspace `~/Developer/claude`, using decoys with harmless contents — never a real secret, per the rule in `README.md` § The one file this repo does not deploy.

| Probe | Result |
| --- | --- |
| Read `$TMPDIR/outside-decoy.txt` (outside the workspace) | **read, contents printed** |
| Count entries directly in `$HOME` | **63** |
| Write `$TMPDIR/should-fail.txt` | refused |

Stated precisely: the probes show reads reaching **beyond the workspace**, and one refused write. Three data points cannot establish "reads everything, writes nothing" — what carries it from those points to a general claim is the documentation below, which describes no read control at all. Keep the two apart: the table is measurement, the generalisation is inference from the design.

Either way the skill's original instruction — check whether the working tree holds secrets — was checking a boundary that does not exist.

This is long-known upstream and was closed without a fix: [openai/codex#4410](https://github.com/openai/codex/issues/4410), *"Do not allow Codex to read whole filesystem by default in read-only mode"*, closed 2025-10-06 on the argument that confining reads would break `cat`, because Codex could not then read `/bin/cat`. The rebuttal in the thread is the correct one — read and execute are different permissions — and reports continued through 2026 ([#5237](https://github.com/openai/codex/issues/5237)), including one where Codex volunteered that it had found API keys in directories beside the repository. The [sandboxing docs](https://learn.chatgpt.com/docs/sandboxing) confirm the design rather than contradicting it: `sandbox_mode` and `writable_roots` govern writes; that layer has no read control at all.

## The control that exists, and the shape it has to take

Read control moved into [permission profiles](https://learn.chatgpt.com/docs/permissions), where `deny` blocks "both reads and writes under the path". The documented allowlist example — deny `:root`, re-grant `:minimal` and the workspace — **does not work in this build**:

```
sandbox-exec: execvp() of '/Users/ghensk/.local/bin/codex' failed: Operation not permitted
```

`:root = "deny"` removes *execute* on the session helper's own binary, and granting that directory `"read"` does not restore it — the value set is read/write/deny, with no execute. bolinfest's objection in #4410 turns out to describe the implementation accurately. What does work is the inverted shape, verified against a decoy:

```bash
codex exec \
  -c 'permissions.review.filesystem={":root"="read", "/path/to/protect"="deny", ":workspace_roots"={"."="read"}}' \
  -c 'default_permissions="review"' \
  -c 'approval_policy="never"' \
  "<prompt>" < /dev/null
```

| Probe under that profile | Result |
| --- | --- |
| Read `./inside.txt` (in workspace) | read |
| Read `~/Developer/claude/README.md` (outside workspace) | read |
| Read the denied decoy directory | **REFUSED** |

Note what that is: a **denylist**, the same architecture this repository already rejected for `permissions.deny` — it protects the paths someone remembered to name. It is worth having and it is not a boundary.

Two flag interactions matter and are not documented together:

- **`--sandbox read-only` suppresses the permissions profile.** With both set, the outside read succeeded and the `:root = "deny"` exec failure did not occur — the profile was not in effect. Pick one layer; combining them silently keeps the weaker.
- **`-c` values are parsed as TOML in v0.150.1** (they were JSON in v0.40.0). A JSON inline table is accepted as a literal string and fails later as `expected struct FilesystemPermissionsToml`.

## The operational finding that cost the most time

Two apparent "hangs" of 5 and 7 minutes were `codex exec` **blocking on stdin**, printing `Reading additional input from stdin...` — invisible because the call was piped to `tail`, which shows nothing until the process ends. **Every `codex exec` call needs `< /dev/null`.** isamu's `codex-cross-review` records the same requirement; it was read and not carried across, which is the cost of importing a shape rather than a checklist.

## A probe that measured the wrong thing

Both this plan and `plans/0007` cited `ENOTFOUND` from a `node -e 'fetch(...)'` one-liner as evidence that OpenAI's hosts were unreachable from sandboxed Bash. **That probe is invalid.** The sandbox routes allowed traffic through a local filtering proxy advertised in `HTTP_PROXY` / `HTTPS_PROXY`, and Node's built-in `fetch` (undici) ignores those variables — so it fails to resolve *everything*, allowed or not. Demonstrated against a host that has been in `allowedDomains` all along:

| Client | `api.github.com` | `chatgpt.com` |
| --- | --- | --- |
| `node -e 'fetch(...)'` | `ERR ENOTFOUND` | `ERR ENOTFOUND` |
| `curl` (honours proxy env) | **200** | **403** — connected; OpenAI rejects a bare GET |

The rule: **test reachability with a proxy-aware client.** A negative result from a tool that does not use the proxy says nothing about the sandbox, and it is the kind of evidence that reads as conclusive because it is specific.

## The two risks `plans/0007` never named

- **Training on individual plans.** On individual ChatGPT plans, Codex content may be used to train OpenAI's models unless the user opts out, and reporting indicates Codex carries a *separate* training control that the ChatGPT data-controls setting does not change ([help centre](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) — 403 to automated fetch, so this is from secondary reporting and is **unverified**; confirm in account settings before trusting it). This account authenticates as ChatGPT (`codex login status` → *Logged in using ChatGPT*). For a public repository this changes little; for any private or client work it dominates every sandbox question here.
- **The reviewer is an input path.** Codex reads repository contents and returns findings that this agent then acts on: untrusted content → external model → edits. The skill's "evaluate every finding, never apply blindly" already blunts it, but it was written as a quality rule and is also a security one.

## The recommendation, in order

1. **Confirm the training opt-out** before any private repository is reviewed. It is first because it is the cheapest to settle and the least reversible if left wrong: a read that was contained is over, while content already absorbed into a training set cannot be recalled. Two caveats against overstating it — opting out establishes nothing about *other* retention of what was transmitted, and it is not the only risk with effects outliving the process, since a finding acted on leaves edits behind.
2. **Run Codex inside Claude Code's sandbox — adopted and verified.** `sandbox.filesystem.denyRead` and `credentials.files` then bind the Codex process *and its children*, enforced by the OS regardless of whether Codex's own config is right. A permission profile is a setting a CLI upgrade or a typo can silently drop, and a reviewer that reads less produces no error — it looks exactly like a clean review. The cost is real and accepted: those hosts are now reachable by every later command.

   Two settings entries, not one, and the second is the one nobody would predict:

   - `sandbox.network.allowedDomains` += `chatgpt.com`, `auth.openai.com`.
   - `sandbox.filesystem.allowWrite` += `~/.codex`. Without it Codex dies at startup — `could not create PATH aliases`, then `failed to initialize in-process app-server client: Operation not permitted` — before any network call, and identically with `--dangerously-bypass-approvals-and-sandbox`, so it is not sandbox nesting. The whole premise that Codex needed the sandbox off *for network reasons* was wrong; the first blocker was always filesystem.

   And Codex's own sandbox must be **off** — `--sandbox danger-full-access`. The two do not nest: Codex's `read-only` mode shells out through `sandbox-exec`, which inside Claude Code's Seatbelt fails every command with `sandbox-exec: sandbox_apply: Operation not permitted`. A first sandboxed review round reached the model, could not run `git diff`, and correctly returned a BLOCKER rather than inventing findings. Nothing is given up, because the outer sandbox covers both directions — verified in that configuration: workspace read works, a write to `~/should-not-be-writable.txt` is REFUSED, and a read of `~/.ssh/config` is REFUSED. The flag's name is the trap: `danger-full-access` is full access *relative to the inner sandbox*, and this is the most protected configuration available.

   And one that must **not** be added: `~/.codex/auth.json` under `credentials.files`. It was tried, and it leaves Codex unable to read its own credential (`sed: …/auth.json: Operation not permitted`). `credentials.files` protects a credential *from* sandboxed commands, and here Codex is one — so protecting that token and running Codex sandboxed are mutually exclusive. Declining costs nothing that was previously held: the file was never protected.
3. **Failing that, use the deny profile above** for `~/.ssh`, `~/.aws`, `~/.config/gcloud` and the `.env` globs — worth having, not a boundary.
4. **Or contain the whole thing**: run Codex in a container, VM, or dedicated OS account that can see only the repository and the runtime it needs. This is the option that needs neither an incomplete denylist nor a permanently wider egress allowlist, and it is what the maintainer of #4410 suggests to people raising this. It costs a working setup, which is why it sits below the two that cost a settings edit — but on a machine holding client work it is the honest answer.

## Changes

- `skills/codex-review/SKILL.md` — probe results replace the reasoned assertion, with measurement and inference kept apart; `< /dev/null` made mandatory; the prompt-injection reading of the evaluation rule made explicit; and the call moved *inside* Claude Code's sandbox, with `dangerouslyDisableSandbox` removed. The profile shape and the `--sandbox`/profile interaction stay *here* rather than in the skill — the skill links to them, because they are findings about a tool's configuration, not steps in a review.
- `plans/0007` — pointer to this plan, which supersedes its single-risk residual note.

## Verification

- Every table above is a probe run in this session against decoys, not a citation.
- **The recommendation was applied and verified in three stages, which are worth keeping apart** — the first two look like success and are not:
  1. `codex exec --sandbox read-only "Reply with exactly: PING-OK"` returned `PING-OK` sandboxed. That proves startup, network and auth only. **A prompt-only PING executes no shell command, so it cannot detect the nesting failure** — which is exactly why the preflight in the skill is a floor and not a verification.
  2. A full review round in that same configuration reached the model and then failed every command with `sandbox-exec: sandbox_apply: Operation not permitted`, returning a BLOCKER.
  3. With `--sandbox danger-full-access`, the probe table above passed and a full review round completed, read the diff, and produced findings. That is the configuration the skill now ships, and the only one of the three that was verified end to end.

  `dangerouslyDisableSandbox` is gone from the skill. Note also the failure mode found on the way: with the network blocked, `codex exec` **hangs silently** rather than erroring — two probe runs sat with empty output until abandoned. With the stdin hang, the rule is that *no output is never evidence of a clean run*.
- This plan was itself put through `codex-review`: **six rounds, thirteen findings, all accepted, ending in the skill's first `CODEX VERDICT: LGTM`.** The round count is the useful number, not the finding count — three of the six rounds existed only because a claim was corrected in the plan and left standing in `SKILL.md`, which is the Decision Log entry above and the reason it is there.
- Cleanup confirmed: the decoy files and directories created under `$HOME` and `$TMPDIR` were removed and their absence checked. (This says nothing about the repository working tree, which necessarily carries this plan uncommitted while it is being written.)

## Decision Log

- **Deny-list profile accepted as a fallback, not as the fix.** It has the same weakness this repo rejected for `permissions.deny`; it is recommended only where option 2, Claude-side sandboxing, is unavailable.
- **Claude-side sandboxing preferred over Codex-side configuration** because it does not depend on the reviewed tool's own settings being correct, and its failure mode is a visible violation rather than a silent widening.
- **Fix the class, not the site — recorded because this plan failed it twice.** Two consecutive review rounds ended with a finding corrected in the plan and left standing in `SKILL.md`, costing a round each time. The skill's own step 3 already says to sweep every site of a pattern before re-running; having the rule written down did not make it fire. When a finding names a claim, grep the claim.
- **The training question is ordered first**, not because the other risks are transient — an acted-on finding leaves edits behind — but because it is the cheapest of the four to settle and the least reversible once it has gone wrong.
