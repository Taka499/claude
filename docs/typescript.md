# TypeScript / React / web frontend — distilled cross-project lessons

Extracted from `Taka499/ss-assist` (CLAUDE.md, `_docs/execplan-*.md`, source, workflows) on 2026-08-05. Rules here apply to any TS/web project unless the project's own `CLAUDE.md` overrides them.

## Data pipelines: treat generated data like compiled code

**Keep the human-editable source in version control and gitignore the machine-readable artifact.** A pipeline of `data-sources/*.csv` (committed) → `npm run build:data` → `data/*.json` (gitignored) → app code means data edits produce readable diffs, never merge-conflict on regenerated output, and CI regenerates the artifact before every build. Generated JSON is to CSV what `dist/` is to `src/` (ss-assist CLAUDE.md, execplan-phase1).

**Never let humans hand-author IDs in a spreadsheet if they can author labels instead.** The converter builds a reverse map from human labels to stable IDs, keyed as `"category:label"` (not just `label`) so the same word in two categories cannot collide. This keeps the CSV editable by a non-programmer while the runtime uses language-neutral IDs (ss-assist execplan-phase1).

**Prefer opaque sequential IDs (`role-001`, `style-002`) over "meaningful" English slugs derived from another language.** Auto-romanization produces garbage, and inventing English names risks colliding with a future official localization. Sequential IDs are language-neutral and let you delete a whole transliteration dependency (ss-assist execplan-phase1 Decision Log — this removed an entire planned milestone).

**Run schema validation as a separate pipeline step, not inside the converter.** `build:data` then `validate:data` (AJV + cross-file referential-integrity checks on IDs) means a bad row fails loudly in CI before the app builds, and the error message names the offending row. Investing in error message quality pays off every time a non-developer edits the data.

**Match your source filenames to whatever the upstream export tool produces.** Google Sheets exports as `"spreadsheet - sheet.csv"`; keeping inputs named exactly that lets a maintainer drag the download straight in without renaming. Removing a manual rename step removes a class of "why is my data stale" bugs (ss-assist execplan-phase1).

**Watch out for `.gitignore` negation ordering when ignoring generated files by extension.** `data/*.json` also matches a committed source like `data/tags.src.json`, so an explicit `!data/tags.src.json` re-inclusion line is required. Ignore-by-glob plus one committed exception is a common and easy-to-miss trap.

**When adding an automated upstream sync, generate the committed intermediate format rather than the final artifact.** A scheduled job that regenerates the CSVs (and opens a PR) leaves the existing CSV→JSON pipeline untouched, keeps PR diffs human-reviewable, and requires zero app changes — the CSV just shifts from "hand-authored source of truth" to "generated, human-reviewed" (ss-assist execplan-auto-character-pipeline).

## Bitmasks as a performance pattern

**Encode set membership as bit positions in a 32-bit int to make "does this set intersect that set" an O(1) `&`.** Build a lookup assigning each tag in a category a bit (0..31), then `(itemMask & requirementMask) !== 0` replaces array/Set scanning. In a combinatorial search over 20 items (1,140 3-item combinations) or 50 items (19,600), this is what makes the search interactive (ss-assist `src/lib/bitmask.ts`).

**Give each category its own independent 32-bit namespace and assert the 32-tag ceiling at build time.** JavaScript bitwise ops coerce to signed 32-bit; exceeding 32 members per namespace silently corrupts results. The lookup builder throws instead. Per-category namespaces also mean adding a tag to one category never renumbers another.

**Bitmasks cannot count — OR collapses duplicates — so use them only for pruning, never for final correctness.** A requirement like "2 Attackers and 1 Balancer" is invisible to a mask: two Attackers OR'd together are indistinguishable from one. The fix is a hybrid: bitmask pruning to shrink the candidate pool (measured at 50–75% reduction), then exact count-based validation on the surviving small combinations (ss-assist execplan-phase2 — this discovery forced a mid-project redesign).

**Validate your data model against *real* data before committing to a clever representation.** The counting requirement was found by reading the actual source CSV, not the spec; ~9 of 36 records needed it. Reading real data early was the difference between a design tweak and a rewrite (ss-assist execplan-phase2 Milestone 1 retrospective).

**When pruning across multiple independent requirement sets, use union pruning, not intersection.** Keep any candidate relevant to *any* requirement; intersection pruning ("relevant to all") silently discards valid partial-coverage solutions. Correctness beats maximal pruning when the pruning check is already O(1) (ss-assist execplan-multi-mission-combos Decision 2).

## Search, scoring, and optimization heuristics

**Prefer simulation over analytical calculation for "what is the impact of change X" scoring.** Rather than deriving impact formulas, run the real search before and after a hypothetical change and diff the results. It is slower but far more likely to be correct, and it stays correct when the underlying rules change (ss-assist execplan-phase2 Milestone 4: "Simulate Don't Calculate").

**Lexicographic objectives with 100:1 weight gaps beat true multi-objective solvers for ranking UIs.** Weighting tier 1 at 1000×, tier 2 at 10×, tier 3 at 1× guarantees a lower tier can never override a higher one, gives explainable rankings, and needs no solver library. Verify the gap in tests by asserting the score of a tier-1 hit dwarfs any accumulation of tier-3 hits (ss-assist execplan-multi-mission-disjoint-assignment).

**Sort the most-constrained sub-problem first when doing DFS over assignments.** Assigning the hardest-to-satisfy item first prunes dead ends early; assigning easy ones first burns shared resources that the hard ones needed. The classic most-constrained-variable heuristic, and cheap to add.

**Skip exhaustive-search optimizations until profiling proves you need them.** The DFS shipped with no alpha-beta or branch-and-bound because realistic inputs stayed under ~10,000 nodes; a Top-K heap and greedy approximation were explicitly deferred until the UI revealed actual input sizes. Correctness before speed, and let the UI tell you where the bottleneck is (ss-assist execplan-multi-mission-combos Decision 4).

**Return a flat result array with per-item metadata rather than pre-grouped structures.** Pre-grouping in the algorithm layer locks the UI into one layout; a flat list plus coverage metadata lets the view group, filter, or re-sort however it wants without touching the algorithm or its tests (ss-assist execplan-multi-mission-combos Decision 3).

**Name your states precisely; ambiguous vocabulary becomes a bug.** Conflating "satisfiable" (requirements *can* be met) with "completable" (requirements *are* met right now, including gating conditions) produced wrong recommendations until the two were split. Define the distinction in a type or JSDoc comment, not just in your head (ss-assist execplan-phase2).

**Separate what you *display* from what you *compute over*.** The UI showed disjoint, non-overlapping assignments for clarity, but the recommendation engine needed to consider *all* candidate assignments — feeding the display-filtered set into the engine silently truncated recommendations. Design this split up front (ss-assist execplan-multi-mission-disjoint-assignment retrospective).

**Only enumerate the thresholds that actually matter.** Iterating every milestone (10, 20, …, 90) and keeping the highest-scoring one recommended "level 90" when 70 sufficed. Restricting the candidate set to real thresholds and deduplicating to the *minimum* value achieving each outcome fixed both the correctness and the cost (ss-assist execplan-multi-mission-disjoint-assignment, D5.1).

## Zustand + localStorage persistence

**One `persist` key per store, not one per state slice.** A design calling for four localStorage keys collapsed to two because Zustand's `persist` middleware assumes one key per store; this gave atomic writes and needed zero custom serialization. Namespace-prefix the keys (`ss-`) so multiple apps on the same origin don't collide (ss-assist execplan-phase3).

**Always set `version` and a `migrate` function before you ever rename a persisted field.** Renaming a persisted key across a large refactor was safe purely because a `version: 0 → 1` migrate hook rewrote the key on load. Without it, every existing user silently loses their saved state (ss-assist execplan-mission-to-commission-rename; `src/store/useAppStore.ts`).

**Use `partialize` to persist only data, never functions or derived state.** The language store persists `{ lang }` only, excluding the `t()` helper it also exposes. Serializing functions is at best wasted bytes and at worst a stale-closure bug after a deploy.

**Persisted state is a long-lived compatibility surface — build an escape hatch early.** A user hit a state where stale localStorage data from testing blocked normal interaction; the fix was shipping a visible "Clear selection" button. Assume some fraction of users are stuck on state written by an older build (ss-assist execplan-phase4.3, "Test Data Issues").

**Expose stores on `window` in development, gated on `import.meta.env.DEV`.** Being able to poke state from the DevTools console during manual testing is disproportionately useful. The env gate keeps it out of the production bundle (ss-assist execplan-phase3, Lesson 4).

## Routing and static hosting

**For a small SPA on a static host, hash routing in ~15 lines beats a router dependency.** Listen for `hashchange`, derive a page key from `location.hash.slice(1)`, and `switch` on it; navigate by assigning `window.location.hash`. Zero bundle cost, zero server rewrite rules, works offline, and there is no 404 on deep links because the server never sees the path (ss-assist `src/App.tsx`, CLAUDE.md).

**Call the hash handler once on mount, not just on the `hashchange` event.** `hashchange` does not fire for the initial page load, so a user landing directly on `#/results` gets the default page unless you invoke the handler immediately inside the same `useEffect` (ss-assist `src/App.tsx`).

**Reset scroll position manually on navigation.** Hash navigation without a router does not scroll to top; pair each hash assignment with `window.scrollTo(0, 0)`. Routers do this for you, so it's a common regression when you drop one.

**Set Vite's `base` to the repo subpath when deploying to project-scoped GitHub Pages.** `base: '/<repo>/'` in `vite.config.ts` is required for asset URLs to resolve under `user.github.io/<repo>/`; forgetting it produces a blank page with 404s on the JS bundle.

## TypeScript strict-mode practices

**Turn on `noUnusedLocals` and `noUnusedParameters` alongside `strict`, and prefix intentionally-unused params with `_`.** The underscore convention preserves a public signature you want to keep, and is self-documenting — strictly better than an `eslint-disable` comment (ss-assist execplan-phase3 Decision 3).

**Run `type-check` in CI from day one, or errors accumulate invisibly.** A pre-existing unused-parameter error survived an entire implementation phase because nothing ever ran `tsc --noEmit`. Keep `"type-check": "tsc --noEmit"` separate from the build so it can run fast and independently (ss-assist execplan-phase3).

**When a hand-written type in a shared `types/` file diverges from a working implementation's type, change the type to match the implementation.** The implementation is tested and running; the declaration was a draft. Forcing the implementation to fit a stale contract is more expensive than editing the declaration (ss-assist execplan-phase4.3 Decision 5).

**But keep two intentionally different shapes when each is right for its layer — bridge with a small adapter.** The algorithm layer used ID arrays for speed; the view layer wanted hydrated objects for rendering. A ~15-line `transformCombination()` preserved both designs. The judgment call vs. the previous item: unify when one shape is simply stale, adapt when both are genuinely correct for their context (ss-assist execplan-phase4.3 Decision 6).

**Import complex types from the module that implements them, not from a central spec file.** A `BitmaskLookup` declared as `Record<string, number>` in `types/index.ts` conflicted with the real `Map<string, BitPosition>` in `bitmask.ts`. The implementation's type is the one that is actually exercised (ss-assist execplan-phase2 Milestone 2).

**Inline `import("./types").Foo` type references break circular-import cycles between a module and its type file.** Works cleanly with TypeScript's module resolution and costs nothing at runtime (ss-assist `combos.ts`).

**`Object.values()` over a dictionary-typed object frequently loses its element type — annotate the callback parameter explicitly.** `Object.values(tags).forEach((arr: TagEntry[]) => …)` is both a fix for implicit-`any` errors and clearer to read.

**Pass dependencies as function parameters instead of importing module-level singletons.** Refactoring scoring functions to take a `bitmaskLookup` argument rather than calling a global getter made unit tests fast and independent — tests build a tiny fixture instead of booting the whole data-loading layer. The single highest-leverage testability change in the source repo (ss-assist execplan-phase2 Decision, 2025-11-07).

## Vite + Vitest configuration

**Import `defineConfig` from `vitest/config`, not `vite`, when putting `test` config in `vite.config.ts`.** Vite's `UserConfig` type has no `test` property, producing TS2769; `vitest/config` re-exports everything Vite does with the type extended. Vite ignores the `test` block during production builds, so one file serves both (ss-assist execplan-phase3 Decision 1).

**Create `src/vite-env.d.ts` with `/// <reference types="vite/client" />` or `import.meta.env` won't type-check.** Standard scaffolding that's easy to lose when a project is set up by hand rather than via `npm create vite`.

**Choose `jsdom` over `node` as the Vitest environment as soon as any code touches browser APIs.** Store code using `localStorage` needs it even before you write a single component test, and it avoids a migration later (ss-assist execplan-phase3 Decision 4).

**Keep path aliases defined in both `tsconfig.json` `paths` and `vite.config.ts` `resolve.alias`.** TypeScript uses the former for type resolution and Vite uses the latter for bundling; defining only one gives you either red squiggles or a runtime module-not-found. Vitest inherits the Vite aliases automatically.

**Use a separate `tsconfig.node.json` (with `composite: true`, referenced from the root config) for build scripts and config files.** App code compiles with DOM libs and `noEmit`; `vite.config.ts` and `scripts/**` run in Node and need different settings. `"references"` keeps them as one project graph.

**In a `"type": "module"` package, detect direct execution with `` import.meta.url === `file://${process.argv[1]}` ``.** The CommonJS `require.main === module` idiom is unavailable, and this bites every time a script needs to be both importable and runnable (ss-assist execplan-phase1, `scripts/csv-to-json.ts`).

**`tsx` is enough to run TypeScript build scripts — you don't need a second language runtime.** The source project deliberately wrote its scraping/image pipeline in TypeScript (native `fetch`, `cheerio`, `sharp`) rather than Python, to avoid forcing contributors onto two runtimes and two package managers (ss-assist execplan-auto-character-pipeline Decision Log).

## Testing strategy

**Co-locate unit tests as `foo.test.ts` next to `foo.ts`.** Tests move and get deleted with the code they cover, imports stay relative and short, and coverage gaps are visible in the file listing (ss-assist CLAUDE.md).

**Load the real data files in integration tests, not just mocks.** Doing so caught data-structure mismatches that fixture-only tests would have missed, and validated the full load→index→query pipeline. Pair with a `resetData()` helper in `beforeEach`/`afterEach` so module-level singleton caches don't leak between tests (ss-assist execplan-phase2 Milestone 2).

**If a module caches state in module scope, export a reset function purely for tests.** Singleton loaders are convenient and fine — but untestable without an explicit escape hatch.

**Keep a small set of runnable integration scripts alongside the unit tests.** Scripts run via `tsx` against real data, printing scenario results and timings — cheap end-to-end smoke tests and a benchmark harness in one, without a heavyweight e2e framework (ss-assist `tests/test-combos.ts`).

**Test the explicitly-adversarial cases for any counting or set logic: all-same, all-different, empty input, and "just barely insufficient."** These four shapes caught real bugs in count validation; happy-path tests found none of them (ss-assist execplan-phase2 Milestone 1).

**Automated tests will not find your UX bugs — schedule manual testing as a distinct step.** Five significant usability defects shipped past a green 156-test suite and were only found by a human using the app (ss-assist execplan-multi-mission-disjoint-assignment retrospective).

**Build and visually verify components in an isolated scratch page before wiring them into real pages.** A throwaway page rendering every component in every state (normal/highlighted/dimmed/error, each language) makes iteration much faster than testing inside page context — a poor-man's Storybook worth the ~70 lines. Move such pages to an `_examples/` folder with a README rather than deleting them (ss-assist `src/_examples/`).

## GitHub Pages deployment via Actions

**Deploy with the official `actions/upload-pages-artifact` + `actions/deploy-pages` pair and OIDC, not by pushing to a `gh-pages` branch.** Required job permissions are `contents: read`, `pages: write`, `id-token: write`, with a two-job build→deploy split and the deploy job declaring `environment: github-pages`. No deploy keys or PATs to rotate (ss-assist `.github/workflows/pages.yml`).

**Add `concurrency: { group: 'pages', cancel-in-progress: true }`.** Pages allows one deployment at a time; without this, rapid merges queue up and can deploy out of order.

**Put the data-generation step in the deploy workflow, before the build.** `npm ci` → `build:data` → `validate:data` → `vite build` → upload. This is what makes gitignoring generated data safe: the artifact provably exists at deploy time and a schema violation fails the deploy rather than shipping broken data.

**Always include `workflow_dispatch` alongside your push/tag triggers.** Being able to redeploy from the Actions tab without inventing a commit or tag is worth the one line, especially when the real trigger is narrow.

**Use `paths:` filters so a docs-only or refactor-only commit doesn't burn a deploy.** Only redeploy when build inputs (package.json, data sources, i18n, public assets) change.

**`actions/checkout` needs `lfs: true` when any build input is stored in Git LFS.** Without it you get LFS pointer text files instead of the real binaries, and the failure mode is broken images in production rather than a build error (ss-assist tracks PNGs via `.gitattributes`).

**Automate the release chore with a one-line npm script.** `"release": "git push origin develop --tags && gh pr create --base main --head develop --fill"` combined with `npm version patch|minor|major` removes every manual step between "I'm done" and "there's a reviewable release PR."

**For bot-authored data updates, open a PR — don't push directly.** `peter-evans/create-pull-request` with a fixed `branch:` and `delete-branch: true` keeps re-runs idempotent (it updates the existing PR instead of opening a new one each week). Constrain `add-paths:` so the bot can only touch data directories (ss-assist `.github/workflows/auto-character.yml`).

**Encode "nothing changed" as a distinct exit code from your sync script and branch on it in the workflow.** Exit 2 for no-changes, 0 for changes, anything else for real failure; the workflow maps that to a `has_changes` output guarding every later step. This distinguishes "quiet week" from "the scraper broke," which a boolean or an empty diff cannot (ss-assist auto-character.yml).

**Write multi-line PR bodies to a file and use `--body-file` / `body-path`.** Interpolating multi-line strings through `$GITHUB_OUTPUT` is fragile; a temp file is not. Include a human review checklist in generated PR bodies so the reviewer knows what a bot cannot verify.

**Chain workflows on `pull_request: types: [closed]` with a `merged == true` guard for automated promotion.** A `closed` event fires on both merge and abandon; `if: github.event.pull_request.merged == true` is mandatory. Also check whether the target PR already exists before creating it, so repeated triggers are idempotent (ss-assist `promote-to-main.yml`).

## Internationalization

**Resolve translations with a per-key fallback to a single designated base locale, and log a warning when even that misses.** Traversing the dotted key path and, on any `undefined`, re-traversing against the base locale keeps a partially-translated locale usable instead of rendering blank UI; returning the raw key as a last resort makes gaps visible in the running app (ss-assist `i18n/index.ts`).

**Store display strings as a `Record<Language, string>` on the entity and read it as `entity.name[lang] ?? entity.name[baseLang]`.** For a bounded dataset this beats maintaining a parallel key→string translation table, because a new entity cannot be added without its names, and there is no key to typo.

**Keep the base locale's strings inline in the data and only ship override files for other locales.** This halves the translation surface and makes "which strings are actually translated" answerable by file size.

**A homegrown `t()` with `{{param}}` regex interpolation is ~40 lines and often enough.** Full i18n libraries buy pluralization rules, ICU message format, and lazy locale loading — if you need none of those, the dependency is not worth it. Migrate only when a real requirement appears.

**Update `document.documentElement.lang` and `document.title` in an effect keyed on the language.** Easy to forget in a client-rendered SPA, and it affects screen readers, browser translation prompts, and font fallback selection.

**Declare per-script font stacks and select them by language.** Japanese, Simplified Chinese, and Traditional Chinese need *different* fonts for the same Unicode codepoints (Noto Sans JP / SC / TC); a single CJK font renders some glyphs in the wrong regional form. Configure them as named Tailwind `fontFamily` entries and apply by active language.

**Verify UTF-8 encoding explicitly when tooling writes CJK or emoji source files.** Repeated across three phases of the source project: files written programmatically came out mis-encoded (mojibake in Japanese strings, mangled emoji literals), and iconv round-tripping failed to recover them. Check with `file -I` and rewrite via a heredoc if wrong (ss-assist execplan-phase1, phase4.1, phase4.2).

## Refactoring at scale

**Refactor in dependency order: types → data → algorithms → state → components → tests → docs.** Starting from type definitions means the compiler enumerates the remaining work for you; a ~900-occurrence rename across 29 files stayed tractable because each step's errors pointed at the next step (ss-assist execplan-mission-to-commission-rename).

**Expect the true scope of a rename to exceed your grep-based estimate by ~30%.** The estimate was "700+", the reality "~900+", and several files were only discovered when type errors surfaced them. Rely on the type checker rather than the initial search to define "done."

**Prefer an AST-aware or reviewed edit over `sed` for identifier renames.** Bulk `sed` produced `comcommission` from overlapping patterns. Type-checking caught it, but nothing would have caught the same class of error inside a string literal or comment.

**Use `git mv` for file renames so `git log --follow` still works.** Free to do, impossible to retrofit, and it's what lets you bisect through a rename six months later.

**Ship user-visible fixes separately from and ahead of the internal refactor.** Translation/label files are leaf nodes with no dependents — they can go out immediately while the risky internal rename is planned carefully. Two commits, two rollback points (ss-assist execplan-mission-to-commission-rename, D1.1/D1.2).

**Land a placeholder to unblock the layer above you while you resolve a hard problem below.** Shipping a stub page let the entire navigation shell be built and validated while type conflicts in the analysis library were worked out separately (ss-assist execplan-phase4.3).

**Keep the old implementation alongside the new one during a migration, and prove equivalence with a test.** A new multi-input search function was validated by asserting it returns identical results to the old single-input function when given one input — turning "is this a safe superset?" from a hope into a test (ss-assist execplan-multi-mission-combos Discovery 3).

## React specifics

**Gate expensive analysis effects on a cheap precondition instead of running them every render.** Check `selectedIds.length > 0` before invoking a search and wrap the analysis in `useCallback` with an explicit dependency list; running it unconditionally in `useEffect` causes re-render churn (ss-assist execplan-phase4.3).

**Load async app data once at the root behind an explicit loading state, with an `isDataLoaded()` guard for re-entry.** Every page can then assume data exists, and remounting a page after client-side navigation doesn't re-fetch. Handle the rejection path — a caught error that leaves `isLoading` true forever is an invisible white screen.

**Build small stateless presentational components (badge, chip, avatar) first, then compose feature components from them.** Three atomic components (~40 lines each) were reused across six feature components and five pages with zero modifications during integration — the clearest signal that the seam was drawn in the right place (ss-assist execplan-phase4.3).

**Split a many-control workflow into separate pages rather than one page with tabs.** A clearer linear flow, and with hash routing this costs nothing (ss-assist execplan-phase4.3 Decision 1).

**Give analytics a typed wrapper module that fails silently.** A single `trackEvent()` that checks `typeof window !== 'undefined'`, checks the vendor global exists, and swallows exceptions means a blocked analytics script can never break the app; `declare global { interface Window { … } }` keeps call sites type-checked (ss-assist `src/lib/analytics.ts`).

**Give strategic-decision UIs grouping + visual tags + a grid, not a flat ranked list.** Users could not tell which recommendations were interchangeable until the list was grouped by category with color-coded attribute pills. A ranked list answers "what's best"; users also need "what are my equivalent options" (ss-assist execplan-multi-mission-disjoint-assignment).
