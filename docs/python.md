# Python — distilled cross-project lessons

Extracted from `Taka499/info-gathering` (CLAUDE.md, `docs/plans/2026-06-11-info-gathering-bot.md`, source, tests) on 2026-08-05. Rules here apply to any Python project unless the project's own `CLAUDE.md` overrides them.

## Environment and dependency management with uv

**Use `uv sync` + `uv run <cmd>` as the entire local workflow; commit `uv.lock` and use `uv sync --frozen` in CI.** `uv sync` builds `.venv` from `pyproject.toml`/`uv.lock`, `uv run` executes inside it, and `--frozen` in CI guarantees the runner installs exactly the locked versions rather than re-resolving. Combined with the `astral-sh/setup-uv` action this makes a CI install step two lines (info-gathering `.github/workflows/test.yml`).

**Prefer your app's own `load_dotenv()` over `uv run --env-file .env` — a malformed env line makes uv echo the offending line verbatim, printing secrets to the terminal.** A `.env` that held a bare API key with no `KEY=` prefix caused uv's parser to print part of the key into terminal output (and therefore into scrollback and any captured logs). python-dotenv's parse warnings, by contrast, name only the line number. Keep `.env` strictly `KEY=VALUE`, one per line (info-gathering plan 2026-06-11, Surprises).

**Call `load_dotenv()` once inside `main()` so local runs and CI need zero code branching.** In CI the same variables arrive as real environment variables and `load_dotenv()` is a harmless no-op, so there is no `if os.environ.get("CI")` fork anywhere in the codebase (info-gathering `src/infobot/main.py`).

**pytest does not load `.env`, so tests that need real credentials must be run as `uv run --env-file .env pytest`.** The application entry point loads dotenv, but pytest imports modules directly and never runs `main()`. Documenting both invocations (plain `uv run pytest` for the offline suite, `--env-file` for the live one) avoids the confusing "it works when I run the app but not the test" failure (info-gathering README, Development).

**`src/` layout with hatchling: declare `[tool.hatch.build.targets.wheel] packages = ["src/<pkg>"]`.** This keeps the importable package out of the repo root so tests import the installed package rather than accidentally shadowing it with the working directory, and it is the whole build config a small tool needs (info-gathering `pyproject.toml`).

## Lean dependency policy

**Pick one library per concern and refuse the rest: one HTTP client for everything, one feed/format parser, no vendor SDKs.** A project that uses `httpx` for every network call — API JSON, feed bytes, webhook POSTs — gets one shared client, one timeout policy, one set of retry semantics, and one thing to mock in tests. Adding a second HTTP library multiplies all of those (info-gathering CLAUDE.md, Code Style).

**Chat/notification platforms rarely need their SDK: incoming webhooks are a plain HTTP POST of a small JSON body.** Discord and Slack posting, including per-platform rendering, batching, and 429 retry, fit in ~130 lines of `httpx` with no `discord.py` or `slack_sdk` dependency. SDKs earn their weight only for interactive features (slash commands, reactions, socket mode) that a one-way notifier does not have (info-gathering plan 2026-06-11, Decision Log).

**Use Pydantic only at the LLM/serialization boundary; use plain dataclasses for internal domain objects.** The item record flowing through the pipeline is a `@dataclass` — mutable, zero validation overhead, trivially constructible in tests — while Pydantic models exist solely as the schema handed to the structured-output API. Mixing the two everywhere buys validation you do not need on data you created yourself (info-gathering CLAUDE.md; `src/infobot/models.py` vs `summarize.py`).

**Prefer `feedparser` for any RSS/Atom ingestion, and remember that many "APIs" are secretly Atom feeds.** feedparser tolerates malformed feeds that stricter parsers reject, and because arXiv's query API returns Atom, the exact same parse-and-map function serves both blog feeds and the "API" — one code path, two source kinds (info-gathering plan 2026-06-11, Interfaces and Dependencies).

**Feed the parser bytes you fetched yourself rather than letting it fetch.** `feedparser.parse()` accepts a URL, but doing `client.get(url).content` then `feedparser.parse(data)` puts timeouts, headers, redirect policy, and error handling under your control and makes network failures catchable per source (info-gathering `src/infobot/fetchers/rss.py`).

## Fail-open pipeline design

**In a gather-enrich-deliver pipeline, every optional stage must degrade to passthrough, never to data loss.** When the summarization API errors, returns no parsed output, or omits an input id from its response, the affected items are kept with their original defaults and delivered anyway. The invariant "an item that was fetched either gets delivered or gets recorded, but never silently disappears" is worth more than any single enrichment (info-gathering `src/infobot/summarize.py`).

**Handle the three distinct LLM-failure modes separately: exception, `None` parsed output, and id-missing-from-response.** They fail at different layers (transport, schema parsing, model compliance) and only the first is caught by a normal `try/except`. Code that only guards the exception path will still drop items when the model silently returns a short list (info-gathering `summarize.py`, `enrich`).

**Catch broad exceptions at per-source boundaries and log-and-continue; a single dead source must never abort the run.** The dispatcher wraps each source's fetch in `try/except Exception` with `log.exception(...)`, so a 404'd feed, a DNS failure, or a parser crash costs you one source's items rather than the whole batch. Broad `except` is correct here precisely because the boundary is coarse and the recovery is "skip this unit" (info-gathering `src/infobot/fetchers/__init__.py`).

**Validate model-chosen enum values against your own allow-list before applying them.** The summarizer may return a category string that is not in the configured category list; the code checks membership and keeps the source default otherwise. Structured output guarantees a well-typed string, not a meaningful one (info-gathering `summarize.py`; test asserts an invalid category is ignored).

**Give the model an explicit "drop this" verdict field rather than inferring irrelevance from an empty summary.** A boolean `relevant` in the output schema, with a system prompt saying "false only for spam/marketing/content-free; when in doubt, true," makes filtering auditable and biases toward keeping items (info-gathering `summarize.py`).

## Dedup and crash-safe state

**Record item ids at *filter* time, not at delivery time — a crash mid-run should skip, never duplicate.** `filter_new()` does an `INSERT OR IGNORE` and returns only the rows it actually inserted, so an item is marked "seen" before anything downstream can fail. For a bot that posts to human-facing channels, the failure mode "one item was missed" is vastly cheaper than "the whole backlog was posted twice" (info-gathering `src/infobot/store.py`; CLAUDE.md, Architecture).

**`INSERT OR IGNORE` + checking `cursor.rowcount` gives you cross-run dedup and intra-batch dedup in one operation.** Duplicates within a single fetch (the same record arriving from two overlapping queries) collapse for free, with no in-memory set. This turned out to be load-bearing, not a nicety: 75 fetched papers collapsed to 57 unique because cross-listed items appear under multiple category queries (info-gathering plan 2026-06-11, Surprises).

**`CREATE TABLE IF NOT EXISTS` in the store constructor plus primary-key dedup makes the whole pipeline re-runnable by construction.** There is no migration step, no "initialize the database" command, and no first-run special case — deleting the DB file and re-running is a valid recovery path (info-gathering `store.py`).

**Track a separate `posted_utc` column that is NULL until delivery succeeds.** Splitting "seen" from "delivered" costs one nullable column and lets you answer "did this ever actually go out?" during incident triage, without weakening the seen-at-filter-time guarantee.

**Deleting rows from the local state DB is the cheapest way to exercise a delivery path end-to-end.** When nothing genuinely new exists, `DELETE` a few rows and re-run: the items re-deliver harmlessly and you get a live check of routing, rendering, and credentials that no mock can give you (info-gathering plan 2026-06-11, Milestone 4 retrospective).

**Design a documented recovery for total state loss.** Here it is: run once with `--dry-run`, which records ids without delivering, then ship the resulting DB. Any pipeline whose dedup state can vanish needs an equivalent "absorb the current backlog silently" mode, or the first run after a loss floods downstream (info-gathering README, Operations).

**Cap per-source item counts even when the source "should" only return recent items.** One innocuous-looking feed returned its entire ~1800-entry archive on first fetch; without a `max_entries_per_feed` cap (newest first), adding any such source later would flood every channel. Make the cap a per-source config option with a sane default (info-gathering plan 2026-06-11, Surprises).

## Probe external APIs before writing code against them

**Spend ten minutes probing a third-party endpoint with a throwaway `uv run python -c` script before you write the integration.** In the source project *every* external integration behaved differently than its documentation implied. The probe is cheap and decisive; discovering the same facts after writing a fetcher, its tests, and its config schema is not (info-gathering CLAUDE.md, Build and Test).

**A site's public JSON API can be blocked to anonymous clients while the RSS/Atom endpoint for the same listing stays open.** Reddit's `/r/{sub}/top.json` returned `403 Blocked` for every User-Agent tried — bot UA, descriptive `platform:app:version` UA, full browser UA, and the legacy `old.` host — while `/r/{sub}/top/.rss` returned 200. When an API 403s you, check whether a feed, sitemap, or embed endpoint exposes the same data before reaching for OAuth registration (info-gathering plan 2026-06-11, Surprises + Decision Log).

**Assume hrefs inside feed/HTML payloads are entity-escaped; run `html.unescape()` or you will ship URLs containing literal `&amp;`.** This is invisible in casual testing because such URLs often still resolve, then break on the one query parameter that matters. Pin the behavior with a fixture that contains a multi-parameter escaped URL (info-gathering `fetchers/reddit.py`; `tests/fixtures/reddit_sample.xml`).

**Set `follow_redirects=True` on your shared HTTP client — many stable-looking URLs quietly 301/307.** Several configured feeds had moved paths or upgraded `http`→`https`; without redirect following the bot would have silently fetched nothing from them and logged no error. Silence, not failure, is the dangerous outcome (info-gathering plan 2026-06-11, Surprises).

**Accept that an API change can force a feature to be cut, and say so in the design doc.** Losing score-based filtering because the RSS endpoint carries no scores was resolved by leaning on the source's own "top of timeframe" ranking as the quality filter, recorded as an explicit decision rather than an undocumented gap (info-gathering plan 2026-06-11, Decision Log).

**Collect the exact endpoint URLs and their quirks in one "Artifacts and Notes" section of the design doc.** Request shapes, per-request caps, rate limits, and success-response formats (some webhooks answer with a literal `ok` body, not JSON) are expensive to rediscover and trivial to write down once.

## HTTP client practice

**Create one `httpx.Client` for the whole run and pass it down; use a context manager so it always closes.** Connection reuse matters when a fetcher makes ~100 sequential per-item requests, and a single client is the natural place to pin timeout, `User-Agent`, and redirect policy for every call site (info-gathering `fetchers/__init__.py`).

**Always send an explicit `User-Agent`.** Several services reject or throttle default library agents; a stable identifying agent (`myapp/0.1`) is one line and prevents an entire class of intermittent 403s.

**Don't reach for async when the workload is a short-lived batch job.** ~100 sequential requests take about 20 seconds, which is irrelevant inside a scheduled job that runs unattended. Introducing `asyncio` would touch every layer for no user-visible gain (info-gathering plan 2026-06-11, Milestone 2).

**Accept an optional `client` parameter in functions that make HTTP calls, defaulting to one they create and close.** This single-parameter seam is what lets tests inject `httpx.MockTransport` without patching globals, and it costs an `own_client = client is None` flag plus a `finally` block (info-gathering `post.py`, `post_all`).

**Rate-limit retry: read the delay from wherever that specific API puts it, and retry exactly once.** Different services put `retry_after` in the JSON body versus a `Retry-After` header; the code tries the body and falls back to the header. One retry bounds worst-case runtime while absorbing the common single-burst 429 (info-gathering `post.py`, `_post`).

**Respect documented per-request batch caps and let them set your batching constant.** The delivery layer batches at 10 items because that is the platform's cap on embeds per request; reusing the same constant for the other platform keeps messages skimmable and the code single-pathed.

## Secret hygiene

**Never log a webhook URL — the secret token is in the URL path.** Any log line, exception message, or debug print containing the full URL is a credential leak, which is why the code logs only the *env var name* when a webhook is missing, never the value (info-gathering `post.py`, `_webhooks`).

**Pin the `httpx` logger to `WARNING` in your entry point; at INFO it logs full request URLs.** With default logging, the first real delivery run writes every webhook URL into CI logs. This was caught by reasoning ahead rather than by an incident — set it before you write the posting code, and leave a comment saying why so nobody "cleans it up" (info-gathering `main.py`).

**Secrets leak through tooling side channels — parse warnings, request logs, error messages — not just through committed files.** `.gitignore` and secret scanning cover the file vector only. Audit anything that echoes input back: env-file parsers, HTTP client logs, exception reprs that embed the request (info-gathering plan 2026-06-11, project retrospective).

**Derive credential env-var names from config values instead of storing credentials or their names in config.** Deriving `<PLATFORM>_WEBHOOK_<CATEGORY>` (upper-cased, dashes to underscores) from the category name keeps the checked-in config file structurally secret-free and makes adding a destination a pure ops action (info-gathering `post.py`, `_env_name`).

**Treat "credential absent" as a supported off switch, not an error.** A missing webhook variable means that platform/channel is disabled: logged once at startup, skipped silently after. This is what let a second delivery platform be fully implemented and unit-tested while remaining dark in production with zero code changes to enable later (info-gathering plan 2026-06-11, Decision Log).

## Testing an integration-heavy pipeline

**Make the default test command hermetic: `uv run pytest` must touch no network.** Every fetcher test uses `httpx.MockTransport` with a request handler, and every parser test reads a small checked-in fixture. This is what makes the suite runnable on a fresh CI runner with no secrets configured (info-gathering `.github/workflows/test.yml`).

**`httpx.MockTransport(handler)` is the right mock granularity: it exercises your real client, real headers, and real response handling.** The handler receives an actual `httpx.Request`, so you can route on `request.url.path` to serve different fixtures, and — usefully — *assert on the outgoing request* inside the handler (one test asserts the custom User-Agent is present, encoding a real API requirement as a test) (info-gathering `tests/test_hackernews.py`, `tests/test_reddit.py`).

**Collect requests into a list inside the handler to assert on batching and routing.** Checking `len(requests) == 4` and the set of URLs proves batch-splitting, per-destination fan-out, and that unconfigured destinations were skipped — behavior that is invisible from return values alone (info-gathering `tests/test_post.py`).

**Check in the smallest possible fixture that reproduces the exact quirk you had to handle.** A two-entry Atom fixture — one external link with an escaped multi-parameter URL, one self-post whose link equals its comments URL — regression-tests unescaping *and* self-post filtering in a file you can read at a glance (info-gathering `tests/fixtures/reddit_sample.xml`).

**Auto-skip live-API tests with `@pytest.mark.skipif(not os.environ.get("API_KEY"), reason=...)`.** The test is valuable when someone runs it deliberately with credentials and invisible otherwise, so CI stays green and offline contributors are not blocked. Keep exactly one such test — a smoke test that the call shape and response parsing still work (info-gathering `tests/test_summarize.py`).

**Neutralize client construction in unit tests with a fixture that stubs the SDK constructor.** A `monkeypatch.setattr(module.sdk, "Client", lambda: object())` fixture guarantees no test can accidentally require a key, even if a code path changes. Pair it with monkeypatching the single network-calling helper (info-gathering `tests/test_summarize.py`, `no_real_client`).

**Factor the one API call behind a small named function so the surrounding apply/fallback logic is testable without mocks-of-mocks.** Isolating `_summarize_batch(client, config, items) -> Verdict | None` means `enrich()`'s batching, verdict application, and fail-open branches are all tested by patching a single symbol (info-gathering `summarize.py`).

**Monkeypatch `time.sleep` when testing retry paths.** `monkeypatch.setattr(module.time, "sleep", lambda s: None)` keeps a rate-limit-retry test instant while still proving the retry happened via a call counter (info-gathering `tests/test_post.py`).

**Test dry-run mode with a handler that raises `AssertionError` on any call.** This proves "dry run makes no network calls" as a hard invariant rather than trusting an `if` statement, and it is the one property that makes dry-run safe to hand to a user (info-gathering `tests/test_post.py`).

**Make dry-run print what *would* happen for every destination, including unconfigured ones.** Skipping credential resolution entirely in dry-run means the preview works before any secret exists — a useful first-run experience — and it must also skip the "mark delivered" step so previews are repeatable.

**Fixture-based tests will not catch the bugs that matter most in an ingestion pipeline; do a real network run early.** Both of the source project's biggest surprises (archive-sized sources, silently redirecting URLs) were invisible to the entire fixture suite and appeared within seconds of the first live run (info-gathering plan 2026-06-11, Milestone 1 retrospective).

## Scheduled bots on GitHub Actions

**Split a cron bot into a public code repo and a private state repo when you want the code open but the activity private.** The private repo holds the live workflow, the Actions secrets, and the state file; its scheduled job checks itself out plus the public code repo into a subdirectory, runs the tool with `working-directory: code`, and commits state back to itself. This matters because on public repos the Actions run logs and schedule are publicly visible — keeping only the state file private is not enough (info-gathering plan 2026-06-11, Decision Log).

**Keep a non-executing `run.yml.sample` in the public repo as documentation.** Actions only executes `*.yml`/`*.yaml`, so the `.sample` suffix makes the file a readable reference that can never fire. Say in its header comment that the live copy lives elsewhere, or someone will edit the sample and wonder why nothing changed (info-gathering `.github/workflows/run.yml.sample`).

**Commit small state files back to git rather than relying on `actions/cache`.** Cache entries can be evicted, and for a dedup database eviction means mass re-delivery. A binary blob in git history is ugly in diffs but durable, and when only the bot writes it, conflicts cannot occur (info-gathering plan 2026-06-11, Decision Log).

**Guard the commit-back step with a `concurrency` group and `permissions: contents: write`.** The concurrency group (`cancel-in-progress: false`) prevents two runs racing on the state push; least-privilege permissions keep the token from doing anything else.

**Use `git diff --cached --quiet || git commit` so a no-change run doesn't fail the workflow.** Committing generated state unconditionally makes every quiet run red; this one-liner makes the commit conditional (info-gathering `run.yml.sample`).

**Note that state commits keep the schedule alive.** GitHub disables scheduled workflows after 60 days of repository inactivity; a bot that commits its own state into the repo where the workflow lives is self-sustaining, whereas a bot that writes nothing back will silently stop after two months.

**Offset cron minutes off the hour.** `17 */6 * * *` rather than `0 */6 * * *` avoids the top-of-hour scheduling rush, where free-tier scheduled runs are commonly delayed.

**A brand-new repo can fail to register its workflow on the first push; the fix is a commit that modifies the workflow file itself.** After `gh repo create --push`, the file existed on the default branch and Actions reported `enabled: true`, yet `GET /actions/workflows` stayed at `total_count: 0` for many minutes — the initial push apparently raced the Actions app installation. An empty commit did **not** fix it; touching the workflow file and pushing registered it within seconds (info-gathering plan 2026-06-11, Surprises).

**Decide explicitly which branch the scheduled job checks out, and document that merging to it *is* the deploy.** The cron checks out the code repo's default branch, so "deploy" means merging the working branch to it and pushing — a fact worth stating in CLAUDE.md, because there is no other deploy artifact to hint at it (info-gathering CLAUDE.md, Architecture).

## Configuration and CLI shape for batch tools

**Give every path a `--flag` override defaulting to the production value.** `--db PATH` and `--config PATH` let tests and CI point at scratch locations without env-var gymnastics — the Actions workflow passes `--db "$GITHUB_WORKSPACE/seen.db"` to run code from one checkout against state in another (info-gathering `main.py`).

**Provide both a `--dry-run` (do everything but deliver) and a `--no-<expensive-stage>` flag (skip the paid/slow step).** They compose into a fast, free, side-effect-free smoke test of the whole pipeline that a new contributor can run before configuring anything.

**Keep every stage independently disableable from config *and* CLI.** The enrichment stage is skipped if either `--no-llm` is passed or `llm.enabled` is false in config, so the operator can turn off API spend permanently or for one run without touching code (info-gathering `main.py`).

**Parse config into typed dataclasses with a per-kind `options: dict` escape hatch.** Shared fields (`kind`, `category`) become real attributes while kind-specific keys stay in a passthrough dict read with `.get(key, default)` — adding a new source kind and its options requires no config-schema change (info-gathering `src/infobot/config.py`).

**Dispatch on a `kind` string through a dict of functions with a uniform signature.** `{"rss": fetch_rss, "arxiv": fetch_arxiv, ...}` with an "unknown kind, skipping" warning keeps plugin registration to one line and keeps a typo in config from crashing the run (info-gathering `fetchers/__init__.py`).

**Canonicalize URLs before using them as dedup keys: lowercase scheme and host, drop the fragment, strip `utm_*` parameters, keep everything else.** Naive URL keys re-deliver the same content arriving from different referrers. Keep meaningful query parameters — over-normalizing collapses genuinely distinct pages (info-gathering `src/infobot/models.py`, `canonical_url`).

**Prefer a native stable id (`hn:12345`, `arxiv:2406.01234v1`) over a URL key whenever the source provides one, and namespace it by source.** Prefixing eliminates cross-source collisions and makes state rows self-describing when you inspect the database by hand.

## Working with an LLM stage inside a pipeline

**Use the SDK's structured-output/parse API with a schema model so you write zero JSON parsing or repair code.** Defining the response as a nested model (a batch object wrapping a list of per-item verdicts) and reading the parsed result meant the project shipped with no `json.loads`, no regex extraction, and no retry-on-malformed-JSON logic (info-gathering plan 2026-06-11, Milestone 3 retrospective).

**Batch items per API call with a configurable `max_items_per_call` and correlate results back by id.** Batching cuts cost and latency versus one call per item; requiring the model to echo each input's id makes the mapping explicit and makes "missing id" a detectable, handleable condition rather than a silent misalignment (info-gathering `summarize.py`).

**Keep the system prompt a frozen module-level string so prompt caching can apply, and put only the variable batch in the user turn.** A prompt rebuilt from scratch each call defeats caching; formatting in a stable value like the allowed category list is fine, per-item data is not.

**Delimit batched items with simple tags and truncate free text before sending.** Rendering each item as an `<item>` block with labeled fields, excerpt clipped to ~800 characters, bounds token cost and keeps a stray long field from crowding out later items.

**Let the model refine, not route.** Primary routing comes from static source→category mapping in config; the model may override the category, write the summary, and drop noise. This keeps the no-LLM code path fully functional and means an API outage degrades quality rather than correctness (info-gathering plan 2026-06-11, Decision Log).

**Tell the model what to do when its input is thin, and expect hedged output.** Sources that give titles only produce summaries like "likely explores…" — acceptable and honest, given a system prompt that says to summarize conservatively from title and source when the excerpt is empty. Decide up front whether hedged-but-honest beats confident-but-invented (info-gathering plan 2026-06-11, Milestone 3 retrospective).

**Surface model-choice cost tradeoffs to the human as a config knob rather than deciding silently.** Defaulting to the strongest model with a commented alternative in config (`# set to <cheaper model> to cut cost`) makes the tradeoff visible and reversible without a code change (info-gathering plan 2026-06-11, Decision Log).

**Check which sampling parameters your target model actually accepts.** Passing `temperature`/`top_p` is a hard error on some current models; the safe default for a classification-and-summary task is to pass neither (info-gathering plan 2026-06-11, Artifacts and Notes).

## Design-doc and decision discipline

**Keep one living plan document per significant piece of work with mandatory `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` sections.** The value shows up when a session's context is gone: every non-obvious choice in the source codebase (why RSS instead of JSON, why two repos, why state is written at filter time) is answerable from one file rather than from archaeology (info-gathering `docs/PLANS.md`).

**Record surprises as Observation + Evidence, with the actual log line or probe output.** "Reddit JSON 403s anonymous clients" is a claim; `www json, browser UA -> 403 / www rss, infobot UA -> 200 application/atom+xml` is a finding nobody has to re-verify.

**Write acceptance criteria as observable behavior, not as code attributes.** "Run twice; the second run prints zeros across all categories" is verifiable by anyone in thirty seconds and actually proves the dedup property; "added a Store class" proves nothing.

**Expect late-arriving, deployment-time requirements to restructure your last milestone, and design so that pivot is cheap.** A privacy requirement surfacing at deploy time converted a single-repo design into a two-repo split; because the code had no deployment coupling (all destinations resolved from env vars, all paths overridable by flag), the change touched CI configuration and documentation only (info-gathering plan 2026-06-11, retrospective).

**Put the durable operational facts into CLAUDE.md — the ones an agent would otherwise re-derive or get wrong.** The highest-value entries are the non-obvious constraints and their reasons: the deploy path, the fail-open policy, the never-log-webhooks rule with "keep it that way," and the probe-before-you-code rule. Conventions with a stated *why* survive refactors; bare rules get optimized away.
