---
name: adopt-from-sibling
description: Port a workflow, config, CI setup, or tooling from a sibling local repo into the current one, adapting the repo-specific parts. Use when the user points at another local checkout as the reference — "make ../<repo>/<file> work here too", "same CI as <repo>", "adopt <thing> from <repo>", "../<repo>を参考にして".
---

# Adopt From Sibling

Copy a proven setup from a neighboring local repo and adapt it here. This is the rigorous form of the copy-paste-from-another-project motion: read fully, list adaptations before editing, verify after.

## Steps

1. **Read the source** file(s) in the sibling repo fully. Identify every repo-specific part: secret names, package/crate/module names, paths, language/toolchain versions, branch names, org/repo slugs.
2. **Diff the stacks.** Compare the target repo's toolchain (cargo vs npm vs uv, test runner, CI runners, directory layout) against the source repo's assumptions. List every adaptation needed *before* editing anything — the list is the review surface.
3. **Adapt and write** into the current repo:
   - CI workflows: check required secrets exist before shipping; flag missing ones with setup instructions instead of silently shipping a workflow that will fail.
   - Tooling/deps: propose the full delta of scripts and dev-dependencies and ask which to include, rather than importing wholesale.
   - Scaffolds/templates: strip content specific to the source (data, names) down to the template shape.
4. **Verify it works**: workflows → push to a feature branch and watch the run; scripts → run them locally.
5. Feature branch + PR per the git rules; name the source repo in the PR body.

## Rules

- NEVER copy secrets or tokens; reference secret NAMES only.
- If source and target might drift later, note in the PR that this was adopted from `<source-repo>` at that point in time.
- If the adopted piece is genuinely general (useful in a third repo too), propose promoting it to the central `Taka499/claude` config repo (skill, stack note, or template) instead of leaving copies in two projects.

---

*Adapted from [isamu/claude](https://github.com/isamu/claude) `skills/adopt-from-sibling`, de-specialized from its yarn/gh assumptions.*
