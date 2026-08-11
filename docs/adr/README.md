# Architecture Decision Records (ADRs) — harness scope

ADRs here record **harness-architecture decisions**: choices about how this central configuration itself works, which every future change to the harness must respect. They are NOT for ordinary rule edits — a rule in `CLAUDE.md` can simply be edited back, so it fails the reversibility gate; its provenance is the PR that introduced it.

Record an ADR only when **all three** gates pass:

1. **Hard to reverse** — projects or workflows come to depend on it, so changing course later has real cost.
2. **Surprising without context** — a future session would look at the setup and wonder why.
3. **A real trade-off** — genuine alternatives existed and one was picked for specific reasons.

This filter is expected to keep the set in the low single digits. Most PRs — including most that add or change rules — produce zero ADRs; that is the filter working.

## Format

One file per decision, numbered sequentially: `0001-slug.md`. A few sentences: context, decision, why, and the genuine alternatives if the rejection is non-obvious. The `Source:` line is mandatory — it is what makes the decision auditable later.

```md
---
status: accepted
---

# {Short title of the decision}

{1-3 sentences: context, what was decided, and why.}

Source: {provenance — which PR/plan/session produced this, and the evidence level.}
```

## Lifecycle (`status`)

`proposed` → `accepted` → `superseded-by-NNNN` or `rescinded` (found false all along). Never delete or rewrite an ADR's original content when its status changes; append one sentence saying what changed. The history is the point.

This convention is a scope-narrowed copy of the project-level one in `Taka499/project-template` `docs/adr/README.md`; project repos keep using that one for their own decisions.
