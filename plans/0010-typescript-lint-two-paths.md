# Plan: TypeScript stack note — list Oxlint for TypeScript 7 next to ESLint, without replacing it

## Goal

`docs/typescript.md` § Lint & static-analysis policy prescribes ESLint with typescript-eslint and sonarjs. On 2026-09-23 the nudge repository hit the wall that makes this incomplete: the `typescript@7` npm package is the native compiler with no JavaScript API, so typescript-eslint and sonarjs cannot load at all. Nudge moved to TypeScript 7 with Oxlint and tsgolint (nudge execplan, decision A17). After this change the stack note tells a project which path to take by its TypeScript version and what the Oxlint path gains and loses, while every project already on ESLint keeps reading exactly the guidance it follows today.

## Changes

- `docs/typescript.md` § Lint & static-analysis policy — one opening paragraph choosing the linter by TypeScript major version (≤ 6: ESLint, unchanged; 7: Oxlint), with the reason and the `typescript@~6.0` pin for projects that want the full ESLint gate. A new subsection "Oxlint path (TypeScript 7)" at the end: what carries over, the two sonarjs rules that do not and their compensation, and the config-file and verification rules learned while building it. No existing paragraph is edited or removed.

## Decision Log (session 2026-09-23)

- **Two paths, not a replacement** — the user's call: existing projects on TypeScript ≤ 6 and ESLint must not read a note that now contradicts their setup, and a migration forced by a documentation edit would be scope creep across every repo. The ESLint text is kept verbatim; the Oxlint text is additive.
- **Selection by TypeScript major version** — it is the actual constraint (the compiler API exists or it does not), it is checkable in `package.json`, and it does not depend on taste.
- **Only measured claims** — every Oxlint claim is from the nudge trial (injected violations, timed runs); the missing-rule list is what failed there, not what the docs imply.
- **No ADR** — a stack-note paragraph, trivially reversible. Fails gate one.

## Verification

- `git diff master -- docs/typescript.md` shows only additions inside § Lint & static-analysis policy.
- The nudge repository's `oxlint.config.ts` and its plan's decision A17 match what the subsection says (versions, lost rules, `complexity` 15, `--deny-warnings`, the injected-`any` check).
