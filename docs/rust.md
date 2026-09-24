# Rust (incl. Windows desktop apps) — distilled cross-project lessons

Extracted from `Taka499/gakumas-rehearsal-automation` (CLAUDE.md, `docs/adr/*`, `docs/EXECPLAN_*` Surprises/Decision sections) on 2026-08-05. Rules here apply to any Rust project unless the project's own `CLAUDE.md` overrides them.

## Rust language & edition

**Rust 2024 edition requires an explicit `unsafe` block inside an `unsafe fn`.** The old "the whole body of an `unsafe fn` is implicitly unsafe" rule is gone, so porting FFI-heavy code to edition 2024 produces a wave of errors that are mechanical to fix but easy to mistake for something deeper. Budget for it when bumping the edition on any Win32/FFI codebase. (gakumas CLAUDE.md, "Windows API Notes")

**A raw string `r#"…"#` is terminated by the byte pair `"#` anywhere inside it — including inside JSON test fixtures whose values start with a markdown heading.** A fixture like `{"body": "## What's new…"}` silently ends the literal mid-fixture and produces a cascade of unrelated parse errors (22 of them in one case). Use `r###"…"###` for any fixture that may embed markdown or JSON. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, Surprises)

**A dependency's API surface is feature-gated: a missing method is often a missing feature, not a wrong call.** `reqwest` with only the `blocking` feature has no `RequestBuilder::json()` (E0599); the fix was either to enable the extra feature or to set the content-type header and serialize with `serde_json::Value::to_string()`. Check `Cargo.toml` features before concluding an API changed. (gakumas EXECPLAN_FEEDBACK_FORM, Surprises)

**Use `env!("CARGO_PKG_VERSION")` as the single in-binary version source and let everything derive from it.** In the source project it fed the update-version comparison and the HTTP `User-Agent`, which in turn let server-side metrics learn the client version with zero extra client code. One constant, several free downstream uses. (gakumas EXECPLAN_DIST_PERMALINK_AND_METRICS)

**Prefer `include_str!`/`include_bytes!` over shipping a sidecar data file when the data must always match the running binary.** A changelog shipped as a file in the release zip goes permanently stale for auto-updating users if the updater refuses to overwrite existing files; embedding makes the in-app view always match the exe, works offline, and needs no packaging or updater change. (gakumas EXECPLAN_CHANGELOG_AND_JP_NOTES)

## Borrow checker patterns

**The "clone the discriminant first" pattern: matching on `&state.field` while mutating sibling fields of the same struct trips `error[E0502]`.** In immediate-mode GUI render functions taking `&mut State`, clone the status/enum once at the top (`let status = state.status.clone();`) and match on the clone; `state` is then free to mutate inside the arms. Writing the clone in from the start meant the anticipated error never appeared at all. (gakumas CLAUDE.md; EXECPLAN_GUI_STATE_DRIVEN_PANEL, Surprises)

**The same trick for collections: snapshot into an owned `Vec` before the loop.** Iterating `state.items` directly while assigning to a sibling field inside the loop body is E0502; collecting a `Vec<(usize, String)>` of just the labels you need, then looping over that, frees the borrow. Same shape, different container. (gakumas EXECPLAN_GUI_STATE_DRIVEN_PANEL, Surprises)

**Passing `&local_clone` rather than `&state.field` is what makes a later `&mut State` parameter safe.** When a helper is widened from `&State` to `&mut State`, the call compiles only if the caller was already handing it a borrow of a *local* clone. Knowing which of the two you pass tells you in advance whether the widening will compile. (gakumas EXECPLAN_ADDITIONAL_RUNS_AND_PRESETS)

**Design GUI render functions to return an action struct instead of mutating deeply.** A `render_*` function that branches on state and returns a plain `PanelActions { start: bool, extend: bool, save: bool, … }`, dispatched by the caller to `handle_*` methods, sidesteps most borrow conflicts structurally and makes "add a control" a three-step recipe rather than an open-ended edit. (gakumas EXECPLAN_GUI_STATE_DRIVEN_PANEL, Decision Log)

## Concurrency & threading

**OS handles that are logically thread-safe are often not `Send` in Rust because they wrap a raw pointer.** The workaround is to extract the numeric value (`let raw = hwnd.0 as usize;`), move that across the thread boundary, and reconstruct the handle inside the new thread. This is sound for Windows `HWND`, whose validity is process-wide, but the pattern needs a comment explaining why it is sound. (gakumas EXECPLAN_PHASE3_AUTOMATION, Surprises; `runner.rs`)

**Cancellation flags must be polled inside inner wait loops, not only at state-machine step boundaries.** An abort hotkey appeared broken because the only check was between steps, while the process spent most of its time inside a multi-second wait loop. Any long blocking helper needs the abort check threaded into it. (gakumas EXECPLAN_PHASE3_AUTOMATION, Surprises)

**Don't fold every shared flag into one mutex-guarded state struct — atomics used as mutual-exclusion guards and signals with different lifetimes should stay separate.** A "running" `AtomicBool` used with `swap` *is* the start-a-run guard; wrapping it in a mutex changes the concurrency semantics for no gain. Likewise an abort signal set by a hotkey thread and reset at run start has a different lifetime from progress state. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR, Decision Log)

**Don't bundle a growing `Vec` into a struct that gets snapshot-cloned every frame.** A live-data buffer kept its own cheap change-detection accessor (a count) instead of joining the per-frame progress snapshot, because cloning the whole vector per frame would have been the dominant cost. Snapshot the scalars; expose collections through a cheap "has it changed?" probe. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR, Decision Log)

**Pass file paths through worker channels, not decoded image/data buffers.** Queueing the on-disk path of an already-written artifact keeps memory flat, leaves the artifact for manual retry if the consumer fails, and makes crash recovery possible. Worker threads communicating only over channels (no shared mutable state) also removed the need for any locks beyond the channel's own. (gakumas EXECPLAN_PHASE3_AUTOMATION, Decision Log)

**Blocking network work belongs on a spawned thread, with results pushed back through the same channel/mutex pattern the rest of the app uses — plus an explicit repaint request.** In an immediate-mode GUI the result otherwise sits invisible until the user happens to move the mouse; `egui::Context::request_repaint()` from the worker is what makes the notice appear on its own. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, M5)

## Windows APIs & Win32 interop

**`EnumWindows` returns FALSE when the callback stops enumeration early — that is success, not an error.** Using `?` on it turns a normal early exit into a spurious failure; discard the result and judge success by whether the callback found what it wanted. (gakumas CLAUDE.md; `capture/window.rs`)

**The `windows` crate's feature flags must exactly match the API surface used, and each newly-called function tends to need another explicit type import.** Adding one function commonly produces `error[E0412]: cannot find type HWND in this scope` plus a missing-feature link error; expect to edit `Cargo.toml` features and the `use` list together. (gakumas CLAUDE.md; EXECPLAN_PHASE1_REMAINING, Surprises)

**To drive another application's UI you need `SendInput` plus `SetForegroundWindow`; `PostMessage` is silently ignored by many games and DirectX apps.** Re-focus the target window before *each* click, because the user may have clicked elsewhere mid-run, and add a small delay (~50 ms) after focusing before synthesizing input. (gakumas CLAUDE.md; EXECPLAN_PHASE3_AUTOMATION, Decision Log)

**UIPI blocks synthesized input from a lower-integrity process to a higher one: if the target runs elevated, your app must be elevated too.** This single constraint cascades into an admin manifest, an un-runnable test harness, and CLI arguments that stop working — plan for the whole chain, not just the manifest. (gakumas CLAUDE.md, "Design Constraints")

**Pass `CREATE_NO_WINDOW` (0x08000000) via `creation_flags()` whenever you shell out from a GUI app.** Without it, every subprocess invocation flashes a console window. (gakumas EXECPLAN_PHASE5_GUI, Surprises)

**Windows lets you *rename* a running .exe even though it won't let you delete it — that is the basis of in-place self-update.** Download to a temp file on the same volume (renames must not cross volumes), stage the new exe as `app.exe.new`, rename the running `app.exe` → `app.exe.old`, then rename `.new` into place, and best-effort delete `.old` at the next launch. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, M4)

**A child process spawned by an elevated parent inherits elevation, so "install update and restart" needs no second UAC prompt.** `std::process::Command` on the new binary followed by a clean exit is enough. The flip side is a security obligation: an elevated self-replacing binary is an admin-RCE path if downloads aren't authenticated. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION; ADR 0013)

**COM apartment models collide: WinRT APIs initialized multi-threaded conflict with winit/eframe's single-threaded `OleInitialize` for drag-and-drop.** The symptom is a panic `OleInitialize failed! Result was: RPC_E_CHANGED_MODE` at window creation. The cheap fix, when you don't need drag-and-drop, is `.with_drag_and_drop(false)` on the eframe viewport builder. (gakumas ADR 0003; EXECPLAN_PHASE5_GUI, Surprises)

**When a third-party framework owns the main thread, host `RegisterHotKey` in a message-only window on its own background thread.** Global hotkeys simply never fire without a message pump servicing them; a dedicated thread with a message-only window is the standard escape hatch. (gakumas ADR 0003)

**Resolve config and resources relative to `std::env::current_exe()`'s parent, never the current working directory.** Users launch from arbitrary shells and shortcuts; CWD-relative lookup mysteriously works in `cargo run` and fails everywhere else. Centralize this in one paths module so every consumer agrees. (gakumas EXECPLAN_PHASE1_REMAINING, Decision Log; `paths.rs`)

**Command-line arguments are a poor interface for an app that requires elevation.** Elevated launches don't attach to the invoking terminal, so args/UAC interact badly; move entry points into the app itself (menus, hotkeys, in-app windows, config file) instead. (gakumas EXECPLAN_CALIBRATION_TOOL)

**Zips produced by .NET/PowerShell store Windows-style backslash separators.** Extraction code and any cross-platform tooling must normalize them; Unix `unzip` warns about it, and naive path joins produce single files with backslashes in their names. (gakumas EXECPLAN_TESSERACT_BUNDLE, Surprises)

## GUI (egui / eframe)

**`eframe::run_native()` takes ownership of the main thread and cannot coexist with a pre-existing Win32 message loop.** If you're grafting an egui GUI onto an existing tray/message-loop app, plan on two separate startup paths plus side threads for anything that needs its own pump, rather than trying to interleave the loops. (gakumas ADR 0003)

**egui image widgets register with `Sense::hover()` by default, so `Response::secondary_clicked()` never fires on a bare `ui.image(...)`.** Build the widget as `egui::Image::new(…).sense(egui::Sense::click())` or the right-click feature is completely inert — it compiles, it unit-tests, and it does nothing. (gakumas EXECPLAN_IMAGE_COPY_TO_CLIPBOARD, Surprises)

**egui's default font has no CJK coverage; all Japanese/Chinese text renders as tofu boxes.** Load a system font (Yu Gothic / Meiryo / MS Gothic on Windows) at startup via `ctx.set_fonts()`. Discover this before shipping a localized UI, not after. (gakumas EXECPLAN_PHASE5_GUI, Surprises)

**In an immediate-mode GUI, anything that reads a file or recomputes a statistic runs many times per second — cache it and recompute only at the moments it can change.** A per-frame CSV re-parse to count flagged rows was replaced by a cached `Copy` pair updated at exactly two events (run finish, save). Similarly, gate expensive texture regeneration on a change counter so idle frames are free. (gakumas EXECPLAN_REVIEW_SAVE_UX / EXECPLAN_LIVE_BOX_PLOT, Decision Logs)

**Render charts with `plotters` into an in-memory RGBA buffer (`BitMapBackend::with_buffer`) and upload as a texture, rather than re-running a disk-writing pipeline or hand-drawing with `egui::Painter`.** Zero disk I/O, and the live view stays pixel-consistent with the on-disk chart because it is literally the same drawing code. Note the RGB→RGBA conversion step for egui. (gakumas EXECPLAN_LIVE_BOX_PLOT, Decision Log)

**State-machine UIs create dead ends: every terminal state needs an explicit way back.** Making the primary action idle-only meant an error state had no affordance at all and the panel was stuck; a "back" button on all terminal states fixed it. Audit each state for at least one exit. (gakumas EXECPLAN_GUI_STATE_DRIVEN_PANEL, Surprises)

**Place any control the user must reach mid-operation somewhere reachable mid-operation — or make it a pre-run preference instead.** A live-view toggle was first put in a panel that only appears after the automation has taken over the mouse; moving it to the idle panel made it usable without any mid-run interaction. (gakumas EXECPLAN_LIVE_BOX_PLOT, Decision Log)

**Resize the viewport once on a state transition, not every frame, or it fights the user's manual resize.** Track an "expanded" bool and issue the resize on its edges only. (gakumas EXECPLAN_LIVE_BOX_PLOT, Decision Log)

**Normalized `0..1` crop rectangles double as `egui::Image::uv` rects with zero conversion.** If your config already stores regions as fractions of the image, "cropping" in the GUI is a UV change on the already-loaded texture, not a new image decode. (gakumas EXECPLAN_REVIEW_INLINE_STAGE_CROPS, Surprises)

**Prefer fixed-width `SidePanel`s + a central area over `columns(n)` when you need a predictably narrow control column.** Equal columns make the control column grow with the window; fixed side panels keep it stable while giving a large, resizable area to the content that needs it. (gakumas EXECPLAN_LIVE_BOX_PLOT, Decision Log)

**Persist small UI preferences in a JSON file next to the exe, written only when the value changes.** For a portable app this beats depending on the framework's appdata storage, matches where the rest of the config lives, and avoids a write every frame — track a `saved_*` shadow field to detect change. (gakumas EXECPLAN_LIVE_BOX_PLOT, Decision Log)

**Use a floating `egui::Window` for read-only or modal-ish content and a separate OS viewport only when independent OS-level sizing is genuinely needed.** Text viewers and forms are cheaper and more consistent as floating windows inside the main viewport. (gakumas EXECPLAN_CHANGELOG_AND_JP_NOTES, Decision Log)

## Testing & test harness

**An embedded admin manifest propagates to the `cargo test` harness binary and makes it un-runnable unelevated (`os error 740`).** Gate manifest embedding in `build.rs` behind an env var (`if env::var_os("NO_MANIFEST").is_none() { embed_resource::compile(...) }` plus `println!("cargo:rerun-if-env-changed=NO_MANIFEST")`), so `NO_MANIFEST=1 cargo test` runs unelevated while normal and release builds embed as before. This one trick converted "tests only compile" into a real unit suite. (gakumas CLAUDE.md, "Testing limitations"; `build.rs`)

**`#![windows_subsystem = "windows"]` silently applies to the test harness too, so `cargo test` prints *nothing* in an interactive console — while looking fine under CI or an agent shell.** GUI-subsystem binaries never attach to an interactive console; piped stdout hides the bug. Gate it: `#![cfg_attr(not(test), windows_subsystem = "windows")]`. Confirm by reading the PE subsystem field (3 = console, 2 = GUI). (gakumas EXECPLAN_IMAGE_COPY_TO_CLIPBOARD, Surprises; `src/main.rs`)

**Introduce a trait seam over the OS/hardware-touching operations so the state machine itself becomes unit-testable.** Extracting a `GameOps` trait (window-valid check, clicks, wait-for-page) let the automation state machine get its first tests ever — ordering, resume numbering, abort-vs-error semantics — against a fake, with the real implementation left in place unchanged. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR; `automation/state.rs`)

**Asserting on the *parent* of a `tempfile::tempdir()` means asserting on the shared system `%TEMP%`, which carries pollution across runs.** A zip-slip escape test kept failing on the `evil.txt` its own earlier buggy run had written. Nest the fixture one directory deeper so the "escape target" is inside your own tempdir. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, Surprises)

**Mark binary test fixtures `-text` in `.gitattributes` — autocrlf will otherwise rewrite them on checkout and break anything byte-exact.** This is fatal for signature fixtures: the committed signature no longer matches the on-disk bytes. Verify with `git check-attr text -- <file>` (expect `text: unset`). Large binary fixtures go through Git LFS, and the test docs must tell people to `git lfs pull` first. (gakumas EXECPLAN_RELEASE_SIGNING, Surprises; `.gitattributes`)

**`#[ignore]` any test needing an external binary, a real desktop, or a live network, and document the exact command to run it.** Ignored tests keep the fast suite green while preserving genuinely valuable end-to-end coverage; they are not second-class if the run instructions live next to them. (gakumas CLAUDE.md)

**Some tests can only be run by a human on an interactive desktop, and the environment can lie about success.** In a clipboard-less agent/CI shell, `arboard::set_image` still returns `Ok` while nothing lands on any clipboard — a write-only assertion would have "passed" forever. Mark such tests clearly and verify through an independent consumer. (gakumas ADR 0010)

**An env-var-gated replay test over real production artifacts turns accumulated field data into a regression suite for free.** Pointing a `#[ignore]`d test at a session folder via an env var re-ran a 500-screenshot batch through the whole pipeline and caught regressions no synthetic fixture would have. (gakumas EXECPLAN_SCORE_ROW_THRESHOLD_RETRY; `ocr/mod.rs`)

**Field-observed failures aren't always reproducible from the saved artifact — validate fixtures against the raw input, not against what the log claimed.** One misread could not be re-provoked from its own screenshot, meaning the log-derived "expected" value would have baked a wrong assertion into the suite. (gakumas EXECPLAN_SCORE_ROW_THRESHOLD_RETRY)

**Check the test's premise before trusting a failing test.** A planned "wrong checksum must be rejected" test turned out to be mathematically unsatisfiable as written (compensating errors made the bad input still satisfy the identity); the flag path had to be validated with a genuinely unreachable value instead. (gakumas EXECPLAN_OVERLAP_SCORE_RECOVERY)

**Compilation and unit tests prove nothing about interaction wiring — schedule a hands-on acceptance pass for anything a human clicks.** The right-click-to-copy feature was fully green in CI and completely inert in the app because the widget didn't sense clicks. (gakumas EXECPLAN_IMAGE_COPY_TO_CLIPBOARD)

**Document your expected-warning baseline and filter against *that*, not against severity.** With ~30 known-benign warnings every build looks broken and nobody reads the output — but `cargo check 2>&1 | grep "^error"` is the wrong cure twice over. It hides every warning, including ones nobody has classified yet, and it yields *grep's* exit status, so a failing build matches and exits 0 while a clean build exits 1 — measured, the check is inverted. Record the known warnings in a baseline file, then show whatever is *not* in it and hand back cargo's own status:

```sh
out=./check.log
cargo check > "$out" 2>&1; rc=$?
grep -vxFf warnings-baseline.txt "$out"   # anything unclassified, new warnings included
exit "$rc"                                # cargo's status, never grep's
```

Two shell traps here, both measured. `${PIPESTATUS[0]}` is bash-only — zsh leaves `PIPESTATUS` empty and keeps the value in `${pipestatus[1]}`, indexed from 1 — which is why this redirects instead of piping. And `status` is a **read-only** parameter in zsh, an alias for `$?`, so `status=$?` aborts the line with `read-only variable: status`; name it `rc`. Checked in both zsh and bash: a clean build prints nothing and exits 0, a broken one prints only the unclassified `error[E0382]` line and exits 101. (gakumas CLAUDE.md, "Build Commands"; corrected 2026-09-24 — see global `CLAUDE.md` § Debugging.)

**After any bulk `replace_all`-style edit, grep to confirm you got them all.** A differently-indented occurrence survived a global replace and was only caught by the follow-up grep. Relatedly, acceptance criteria phrased as textual occurrence counts should be phrased as *definition-site* counts, since imports and comments also match. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR)

## Build & packaging hygiene

**Guard release builds against a running instance of the binary.** A running exe holds an exclusive lock on the output file, so a bare `cargo build --release` compiles for minutes and only *then* dies at the link step with "failed to remove file … .exe". A wrapper script that checks for the process first aborts in about a second; make killing opt-in and never kill the user's app unprompted — it may be mid-operation. (gakumas CLAUDE.md; `scripts/build.ps1`)

**Use `build.rs` to stage runtime assets into the target directory, with `cargo:rerun-if-changed` on each source path.** This makes `target/release/` a runnable layout without a separate packaging step during development, and keeps the rebuild triggers honest. (gakumas `build.rs`)

**Embedding a large third-party toolchain with `include_bytes!` and extracting it next to the exe on first run buys a genuinely zero-install user experience at the cost of binary size.** A ~30 MB zip produced a 38 MB self-contained release; extracting beside the exe rather than to `%LOCALAPPDATA%` kept the app portable with no cleanup story. Shelling out to a bundled CLI also avoided fragile C bindings. (gakumas ADR 0005)

**Ship a folder, not a lone exe, when the app has logs/output/asset subdirectories.** The package is self-contained and intuitive, and the same top-level folder name inside the release zip is what makes an updater's extraction logic simple and stable across versions. (gakumas EXECPLAN_TESSERACT_BUNDLE, Decision Log)

**`[profile.release] lto = true, strip = true` is a cheap default for a shipped desktop binary**, at the cost of noticeably longer link times — which is exactly why the running-exe lock check above must come *first*. (gakumas `Cargo.toml`)

## Configuration & data-format evolution

**Never restructure a serialized config shape to satisfy an internal-ergonomics complaint; introduce a view/parameter struct instead.** Three parallel config arrays threaded through four call sites were consolidated into a parameter object built from the existing fields — the pain went away and not one user's config file broke. Changing the serde shape would have required a migration for zero behavioural gain. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR, Decision Log)

**Prefer a new *value* of an existing field over a new field/column when adding a state.** Storing a `verified` state as another value of the existing `recovery` column meant older readers (which parsed only the first N columns) needed no migration at all. Additive-by-value beats additive-by-schema. (gakumas ADR 0007)

**Per-field serde defaults are what let a self-updating app add config keys without touching the user's file.** The updater replaces the exe and assets wholesale and *never* writes the user's config; new keys simply materialize with their defaults on next load. Preserve that invariant explicitly, because it silently invalidates any "ship a data file in the zip" design. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION / EXECPLAN_CHANGELOG_AND_JP_NOTES)

**Append-only is a crash-safety discipline for *live capture*, not a universal rule.** A deliberate post-hoc correction performed while nothing else is writing may safely rewrite files in full (temp-file-then-rename), and related files should be rewritten together so they cannot diverge. Scope the invariant explicitly or someone will "fix" the correct code in either direction. (gakumas ADR 0009)

**Prefer recomputing derived state from durable artifacts over trusting a stored counter.** Counts recomputed from files written synchronously before any async processing are crash-proof and never lag, whereas a stored counter can. Trust the file only for what genuinely cannot be recovered from artifacts. (gakumas ADR 0008)

## Library-specific lessons that generalize

**`arboard` is effectively write-only on Windows: `set_image` works and every real paste target reads it, but `arboard::get_image` fails on arboard's own custom "PNG" clipboard format even on a healthy interactive desktop.** Use it to write; verify round-trips through an independent consumer (e.g. WinForms `Clipboard.GetImage` via `powershell -NoProfile -STA`, saved to a temp PNG and pixel-compared). More generally: verify a clipboard/IPC write through the same path your real consumers use, not through the writing library. (gakumas ADR 0010)

**`zip::read::ZipFile::enclosed_name()` is not a sufficient zip-slip guard on its own.** In the pinned version a `<root>/../evil.txt` entry survived to `Path::strip_prefix`, which cheerfully returned `../evil.txt`, and the write escaped the destination directory. Add an explicit check that every component of the entry path is `std::path::Component::Normal(_)` and bail otherwise. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, Surprises; `update/install.rs`)

**`minisign-verify` is a pure-Rust, verify-only dependency — the signing side (`rsign2`) stays a dev CLI, never a runtime dependency.** This asymmetry is the right shape for client-side signature verification generally: the client needs no signing capability and no libsodium. (gakumas ADR 0013)

**Interactive-password CLIs must never be launched from a backgrounded or non-interactive shell.** A backgrounded `rsign generate` sat silently on its password prompt with a 0-byte output file, and had it later received input it would have generated a *different* keypair and overwritten the real one — a trust-breaking event. Run key generation interactively, by a human. (gakumas EXECPLAN_RELEASE_SIGNING, Surprises)

**Sanity-check whether a "cross-platform weight" dependency is actually a problem before hand-rolling.** `arboard` was chosen over ~60 lines of hand-written `unsafe` clipboard code precisely because it writes `CF_DIBV5` (what chat apps and editors read); its idle cross-platform code was judged harmless. (gakumas EXECPLAN_IMAGE_COPY_TO_CLIPBOARD, Decision Log)

## Distribution, updates & release engineering

**Bake the update-manifest URL into a single constants file and treat the hostname as a versioned API.** Once a binary ships, its endpoint is effectively immutable for those installs — changing it strands them. Keeping the only two URLs in one file made the eventual hostname migration a one-line change and made the blast radius auditable. (gakumas ADR 0014)

**Use a primary custom-domain manifest with a platform-API fallback, and make every check failure silently return "no update".** The domain gives future re-hosting freedom; the fallback means a lapsed domain degrades gracefully instead of bricking update checks. An update check must never surface an error or block anything. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, Decision Log)

**Make the manifest service stateless — derive it from the release API at request time with edge caching — so the release pipeline has zero infra state to update.** The entire release stayed one command, and there is only one source of truth for what "latest" means. Cache at the edge to stay under the platform's unauthenticated rate limit (GitHub: 60 req/hr/IP; also send a `User-Agent`, which GitHub requires). (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION)

**Sign releases with minisign/Ed25519 and bake the public key into the binary; a SHA-256 check alone is not a security control when the hash and the artifact share one origin.** An attacker who compromises the publishing token or the CDN account can serve malware *with a matching hash* — but cannot forge a signature. Verification must be mandatory (a missing signature is a hard failure, or an attacker just omits it) and the signature checked before the hash. (gakumas ADR 0013)

**Keep the signing secret key on the developer's machine only — password-protected, gitignored, offline-backed — and never in CI, a secrets store, or the edge platform.** A shared secret store is precisely the blast radius signing exists to remove. Never regenerate the key: shipped binaries can only verify signatures from the key they carry. (gakumas ADR 0013)

**Weigh Authenticode against your constraints rather than assuming it.** It costs a yearly commercial CA certificate and binds the signature to a legal identity printed in the exe; its main benefit is SmartScreen reputation. It can be layered on later without removing minisign. (gakumas ADR 0013)

**Update UX should be notify + one-click, never silent — especially for an elevated binary.** A silently self-replacing admin-elevated process is both a trust problem and exactly the shape AV heuristics dislike. Disable the update button while a long operation is running. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, Decision Log)

**An updater should replace only the exe and its assets, and skip any root-level file that already exists locally.** That is what preserves per-machine calibration/config that a user cannot cheaply recreate — and it is why data files shipped in the zip go stale forever (embed them instead). Roll back staged directory renames on failure. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION, M4)

**If you want the download page not to display a personal identity, note that release hosts show the *creating account*.** Publishing from a project-branded machine account, into a code-free releases-only repository under a neutral org, was the mechanism; a full repo transfer would still have put commit avatars one click from the download page. State the scope honestly — this is separation from casual visitors, not anonymity. (gakumas ADR 0011)

**A CLI's ambient auth will silently use the wrong identity — pass the intended token explicitly.** `gh` with ambient `gh auth` would have stamped the personal account onto every public release; the release procedure spells out sourcing a specific token (`GH_TOKEN="$BOT_TOKEN" gh …`) at every call site. (gakumas EXECPLAN_AUTO_UPDATE_DISTRIBUTION)

**Give each app its own single-level subdomain and don't serve the bare root.** It keeps a multi-tool namespace open, and note the hard constraint that drove it: Cloudflare's free Universal SSL covers only one wildcard level (`*.example.com`), so a second-level host like `dl.app.example.com` needs a paid certificate. (gakumas ADR 0014)

**Grant the edge/serverless layer only least-privilege credentials; the release-publishing token must never live there.** Each server-side feature gets its own fine-grained token scoped to the minimum permission on the minimum resource, so a leak's worst case is annoyance rather than a malware push into the update channel. (gakumas ADR 0015)

**Record every long-lived credential's expiry and, more usefully, record what its expiry will *look like*.** "401s from the release command mean the bot token expired"; "502s on the feedback endpoint mean that token expired" — future-you gets an error message, not a calendar reminder. (gakumas CLAUDE.md)

**Author release notes in a repo `CHANGELOG.md` first, then derive the release body from it — and commit before building if the file is embedded.** An entry added after the build isn't in the shipped exe. A convention where the body's first paragraph is the user-facing one-line summary costs zero code, because every consumer just splits on the first blank line without interpreting content. (gakumas EXECPLAN_CHANGELOG_AND_JP_NOTES, Decision Log)

**Conventions that ride mechanics you already have are the cheapest kind — but count the replicas.** The "first paragraph is the hint" rule had three independent implementations that agree only because all three merely split and never interpret. (gakumas EXECPLAN_CHANGELOG_AND_JP_NOTES, Surprises)

## Telemetry, feedback & privacy

**Anonymous-by-design metrics: derive uniqueness from a daily-rotating salted hash of the client IP computed server-side, and never introduce a persistent client identifier.** Truncated SHA-256 of (IP + UTC date + secret salt) is irreversible without the salt and useless across days, so buckets can't be chained into a profile; dimensions stay coarse (day, event, client version, country). An "anonymous install UUID" is a durable per-user tracker no matter what it's called. (gakumas ADR 0012)

**Get the client version dimension for free by parsing the User-Agent your updater already sends.** Zero client changes, zero new identifiers. (gakumas EXECPLAN_DIST_PERMALINK_AND_METRICS)

**A best-effort telemetry path that swallows all errors needs an out-of-band health signal.** Error-swallowing is right for the request path — but the identical swallow hid a missing API-token secret on the nightly rollup for a full day, because "misconfigured" looked exactly like "no traffic". Surface "latest rollup is N days stale" somewhere. (gakumas EXECPLAN_DIST_PERMALINK_AND_METRICS)

**Verify the observable outcome, not that the command was issued.** A step recorded as "secret set" had not actually taken effect, and the gap surfaced only days later when the expected data never appeared. For anything that fails silently, assert on the artifact. (gakumas EXECPLAN_DIST_PERMALINK_AND_METRICS)

**Platform one-time enable gates cost more time than the code — document them next to the deploy instructions.** Two separate Cloudflare gates each blocked a deploy with a cryptic unrelated error: Analytics Engine must be enabled by hand in the dashboard (code 10089), and attaching a cron trigger requires the account to have a workers.dev subdomain even when the worker never uses one (code 10063). (gakumas EXECPLAN_DIST_PERMALINK_AND_METRICS, Surprises)

**Increment a rate-limit counter only after the operation succeeds.** Otherwise a transient upstream failure eats a legitimate user's daily quota. (gakumas EXECPLAN_FEEDBACK_FORM, Surprises)

**If you're building in-app feedback on top of an issue tracker, know the constraints up front: GitHub has no API for attaching files to issues, and issue bodies cap at 65,536 characters.** The workable design is client-side truncation to a tail (that's where crashes live) embedded in a collapsed HTML details block, with a defensive server-side re-truncation. (gakumas EXECPLAN_FEEDBACK_FORM, Surprises)

**When a server enforces a length check in JavaScript, count the same way on the client: JS `String.length` is UTF-16 code units, not `chars().count()`.** Use `message.encode_utf16().count()` so nothing the client accepts can be rejected server-side. Also truncate log tails on a `char` boundary. (gakumas EXECPLAN_FEEDBACK_FORM, Surprises)

**A public unauthenticated endpoint is the honest design for a shipped desktop client — any secret in the binary is extractable.** Defend it with a request size cap and a light per-day rate limit keyed on the anonymous hash you already compute, and pick a blast radius you can live with. (gakumas EXECPLAN_FEEDBACK_FORM, Decision Log)

**Org ownership silently outranks repo-level grants: a bot that owns the org already has admin everywhere in it.** The least-privilege guarantee then rests *entirely* on the fine-grained token's scoping (effective access = token permissions ∩ user permissions), so don't reason from "the bot only has triage rights". (gakumas EXECPLAN_FEEDBACK_FORM, Surprises)

## Debugging & verification discipline

**Capture concrete evidence before theorizing — each probe should eliminate a whole hypothesis class.** A three-layer failure (invisible test output → suspected environment → actual library read path) was only untangled because each round produced a fact: reading the PE subsystem field killed one hypothesis, an external-consumer clipboard probe killed the next. (gakumas EXECPLAN_IMAGE_COPY_TO_CLIPBOARD)

**Correct a wrong-but-plausible diagnosis in the record rather than leaving it.** A clipboard read failure was first blamed on the agent environment; the user's desktop run disproved it, and the write-up was amended — which is what turned a debugging session into a durable rule others can trust. (gakumas ADR 0010)

**Don't add a helper/seam whose only caller is hypothetical.** Two proposed geometry helpers were rejected because the feature that motivated them was already shipped with its own tested implementation — "one adapter means a hypothetical seam". Add the abstraction when the second real caller appears. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR, Decision Log)

**Prefer move-not-rewrite when refactoring, so the diff stays reviewable.** Keeping a newly-extracted type in its original module (instead of the plan's proposed new file) kept a milestone's diff legible as a pure move; the file split can come later. (gakumas EXECPLAN_SUSTAINABILITY_REFACTOR)

**Satisfying a checksum/invariant is not proof of correctness — never auto-clear a human-review flag on it.** A row was flagged precisely because multiple solutions satisfied the check; auto-clearing "consistent" rows silently reintroduces the exact error class the flagging exists to catch. Resolution should be an explicit human act, recorded as such. (gakumas ADR 0007)

**Write down reversals.** An architecture was replaced by its opposite and no plan ever recorded it, so the superseded documents kept reading as current guidance for months. If a decision inverts, the correction belongs in a durable, dated, provenance-carrying note — not as edits to the historical document. (gakumas ADR 0002; ADR 0001)
