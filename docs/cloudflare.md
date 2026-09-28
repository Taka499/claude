# Cloudflare — distilled cross-project lessons

Lessons about Cloudflare services, independent of the project's language. Workers deployment entries captured earlier stay in `docs/typescript.md` § Cloudflare Workers deployment and `docs/rust.md` § Distribution, updates & release engineering.

## R2 object storage

**The Cache-Control stored with an R2 object follows it everywhere.** The value given at upload (`wrangler r2 object put --cache-control …`) is stored with the object and returned on every download, including downloads through the Cloudflare dashboard — not only requests that pass through your own Worker. So "this object is private and never served, caching doesn't matter" is wrong: private images uploaded with `public, max-age=31536000, immutable` were later overwritten with corrected versions, and the browser kept serving the old copies from the dashboard, so a correct bucket looked stale. Comparing checksums of `wrangler r2 object get … --remote` against the local files proved the bucket was right (gakumas-supportcards, 2026-09-21).

**Base the stored Cache-Control on how the object may change, not on who serves it.** Use `private, no-cache` for anything you expect to overwrite, and `immutable` only for objects whose key never gets new content (content-hashed names, for instance). A Worker that sets its own response header is unaffected; the dashboard and direct downloads still get the stored value.
