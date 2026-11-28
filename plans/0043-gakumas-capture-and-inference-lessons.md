# Plan: Rust lessons from the gakumas custom-OCR-model plan

## Goal

`Taka499/gakumas-rehearsal-automation` completed `docs/EXECPLAN_CUSTOM_OCR_MODEL.md` on 2026-11-27 (Tesseract replaced by project-trained CRNNs; M8 fixed a capture slowdown and memory growth). The user approved on 2026-11-28 ("Go ahead for the follow-ups") capturing its lessons that generalize beyond that repository into the Rust stack note.

## Changes

`docs/rust.md`, one paragraph per lesson, each in the section it belongs to:
- § Concurrency & threading: the `unsafe impl Send` argument for cached D3D11/WinRT objects; `Duration` comparisons instead of `as_secs() > N`.
- § Windows APIs & Win32 interop: reuse the D3D11 device and capture item across Windows Graphics Capture calls.
- § Build & packaging hygiene: `build.rs` must not overwrite a user-edited staged config.
- § Library-specific lessons: loading dynamo-exported ONNX in `tract-onnx` 0.23; preprocessing as a byte-exact contract.
- § Debugging & verification discipline: measure inside the app when offline probes are flat; the per-process GPU dedicated-usage counter is misleading.

Not included: the proposed `codex-review` note about running Codex on an isolated copy when there is no outer sandbox — the skill's snapshot procedure (step 2) already covers it.

## Evidence

All from the gakumas repository, `docs/EXECPLAN_CUSTOM_OCR_MODEL.md`:
- Capture reuse: M8 step 3 and acceptance — per-phase probe (device ~130 ms, item ~40 ms of ~190 ms), in-app run 230 → 451 ms and ~5 MB/iteration before the fix; 500-rehearsal single-instance run after it, captures ~20 → ~80 ms flat from iteration ~200, memory ~0.16 MB/iteration.
- `unsafe impl Send`, `as_secs()` timeout: decision D24 (Codex review, 3 rounds).
- `build.rs`: M8 step 2 (marker survives a forced rerun; overwritten with the guard removed).
- tract-onnx: M2 (Surprises), parity tests against ONNX Runtime; ADR 0016.
- GPU counter: Surprises, M6 series (300-capture probe).

## Verification

Read the diff of `docs/rust.md`: each new paragraph cites its source, sits in the matching section, and duplicates no existing entry.
