# Canonical Usability and Compact Rust Slice

Goal: make `moredakka` more canonical, simpler, and more robustly usable while beginning a compact Rust implementation at the deterministic local-surface seam.

## Landed in this tranche

### Python surface hardening
- CLI now collapses expected runtime failures into compact operator-facing errors instead of full Python tracebacks.
- `review` mode now derives changed files from branch-vs-base diff, not just working-tree status.
- `doctor` now checks repo/base-ref readiness in addition to env/config/provider readiness.
- config validation is stricter around empty fields and invalid reasoning values.
- core install path is slimmer: direct Gemini SDK moved out of mandatory dependencies.

### Rust sidecar bootstrap
- Added Cargo workspace.
- Added `crates/moredakka-core`.
- Implemented narrow Rust CLI for:
  - `doctor`
  - `pack`
- Rust sidecar shells out to git and mirrors the deterministic local-work-surface logic rather than attempting orchestration.

## Why this is the right seam

The local surface is the real leverage point and is much safer to port first than providers/orchestration.

Keep Rust narrow until parity and ergonomics are proven.

## Next tranche
- richer report trust surfaces: facts vs inference vs ambiguity
- evidence-seeking second pass before final synthesis
- optional Python delegation to Rust for `doctor` and `pack`
