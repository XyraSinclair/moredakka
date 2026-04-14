# Beauty, Provenance, and Rust Canonicalization Plan

> For Hermes: keep the product narrow. Prefer small reversible tranches. Push deterministic local truth and durable provenance into Rust first. Leave volatile provider/network glue in Python until the contracts are stable.

Goal: turn `moredakka` into a more beautiful canonical software system: denser, more typed, more inspectable, more reproducible, more bounded, and more Rust-native without paying rewrite tax.

Architecture in one sentence: Rust should become the authoritative home for deterministic local truth, storage, provenance, accounting, and report rendering; Python should temporarily remain the thin orchestration shell for provider churn.

Tech stack:
- Rust for deterministic core, storage, provenance, report assembly
- SQLite + content-addressed blobs for durable local history
- Python only where SDK churn and provider quirks still dominate

---

## The beauty target

The repo should converge toward these properties:

1. One invocation = one durable run record.
2. Facts, inference, and ambiguity are explicitly separated.
3. Boundedness includes cost, time, and context loss, not just rounds.
4. Failures become typed artifacts, not only exceptions.
5. Deterministic local logic has one implementation, not Python/Rust drift.
6. Reports are falsifiable: provenance, timings, prompts, schemas, usage, stop reason.
7. Storage is append-only and backup-friendly.
8. The narrow product shape stays intact.

---

## Current ugliness to eliminate

1. Run provenance is mostly missing from the product surface.
2. Usage/cost data is captured internally but discarded from reports.
3. Cache exists, but there is no canonical run journal.
4. Rust and Python deterministic logic are near-duplicates, not one source of truth.
5. Schema checking is too shallow.
6. Truncation and omission are mostly invisible.
7. Failure states are not yet modeled as first-class results.

---

## Canonical target architecture

### Rust owns
- config discovery/defaults/validation
- doctor
- context packet construction
- context rendering and loss accounting
- typed schemas and validation
- novelty/convergence logic
- canonical report DTOs and rendering
- run journal / provenance event model
- usage normalization and cost accounting
- durable local store
- export / backup / restore

### Python owns temporarily
- CLI entrypoint compatibility
- prompt composition from markdown prompts
- provider client construction
- actual model API calls
- round scheduling / concurrency policy
- transient retries and provider-specific quirks

### Persistence model
- SQLite for metadata/indexes
- content-addressed blob store for large prompts/responses

Suggested layout:
- `.moredakka/store/db.sqlite3`
- `.moredakka/store/blobs/sha256/...`
- `.moredakka/runs/<timestamp>-<shortid>/manifest.json` during initial tranche or as export view

---

## Proposed Rust crate/module shape

Keep this compact.

### Crate 1: `moredakka-core`
- `config`
- `surface`
- `packet`
- `doctor`
- `schema`
- `analysis`
- `report`

### Crate 2: `moredakka-store`
- `db`
- `events`
- `artifacts`
- `usage`
- `cost`
- `backup`
- `query`

### Optional crate 3 later: `moredakka-cli`
Only if the Rust command surface expands enough to justify a dedicated thin binary crate.

For now, keeping CLI thin inside `moredakka-core` is acceptable.

---

## Data model that beauty requires

### Invocation
- invocation_id
- started_at
- ended_at
- duration_ms
- command
- mode
- explicit_objective
- inferred_objective
- cwd
- repo_root
- branch
- head_sha
- merge_base
- base_ref
- config_path
- config_hash
- tool_version
- cache_enabled
- stop_reason
- run_status

### Context packet accounting
- packet_hash
- char_budget
- original_chars
- final_chars
- diff_chars_kept
- doc_chars_kept
- file_excerpt_chars_kept
- omitted_docs_count
- omitted_files_count

### Provider call
- invocation_id
- round_index
- role_name
- provider_name
- model_name
- prompt_artifact_id
- schema_name
- schema_hash
- response_artifact_id
- response_id
- cache_hit
- started_at
- ended_at
- duration_ms
- status

### Usage / cost
- input_tokens
- output_tokens
- reasoning_tokens_nullable
- total_tokens
- pricing_version
- estimated_cost_microusd

### Failure / degraded mode
- role_status: success | timeout | provider_error | schema_error | skipped
- run_status: success | degraded | failed
- stop_reason: max_rounds | low_novelty | budget | timeout | provider_failure | explicit_abort

---

## Tranche plan

## Tranche 1: Canonical run journal

Objective: every invocation becomes a durable inspectable artifact.

Files:
- Create: `crates/moredakka-store/`
- Modify: `crates/moredakka-core/src/main.rs`
- Modify: `src/moredakka/cli.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: `README.md`
- Modify: `SPEC.md`
- Test: Rust unit tests + Python integration tests

Steps:
1. Introduce a run manifest schema in Rust.
2. Emit invocation metadata, repo metadata, config hash, packet hash, round metadata, provider usage, and stop reason into a durable run record.
3. Preserve prompts/raw outputs as artifacts referenced by hash.
4. Add a user-visible location for the run artifact in final CLI output.
5. Add `moredakka runs` later only after the storage contract is stable.

Verification:
- one run produces one durable record
- rerunning the same command in the same repo creates a second run with separate timestamps but shared blob artifacts when content is identical
- report output references invocation_id

Why first:
- This fixes provenance, inspectability, reproducibility, and future backup/export all at once.

## Tranche 2: Usage and cost become first-class bounds

Objective: make boundedness real.

Files:
- Modify: `src/moredakka/providers/*.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: `src/moredakka/report.py`
- Modify: `src/moredakka/config.py`
- Modify: Rust store/accounting modules
- Modify: `README.md`
- Modify: `SPEC.md`

Steps:
1. Normalize raw usage from every provider into one internal accounting shape.
2. Add configured price tables with explicit versioning.
3. Add `max_cost_usd`, `max_total_tokens`, and `max_wall_seconds` defaults.
4. Surface per-role and total usage/cost in JSON and markdown outputs.
5. Stop early with an explicit stop reason when a bound would be exceeded.

Verification:
- reports show role-level and total usage
- cost estimation is replayable from stored usage + pricing version
- configured hard bounds fail closed with explicit output

## Tranche 3: Replace weak shape checks with real typed validation

Objective: make typed outputs true, not aspirational.

Files:
- Modify: `src/moredakka/schemas.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: Rust schema module
- Test: malformed nested JSON fixtures

Steps:
1. Perform full schema validation at the provider boundary.
2. Persist validation errors into the run record.
3. Model degraded-mode synthesis explicitly.
4. Surface role failure objects in report JSON.

Verification:
- malformed provider output becomes a typed schema failure artifact
- degraded runs render as degraded, not silently successful

## Tranche 4: Make Rust the single source of deterministic local truth

Objective: remove Python/Rust drift.

Files:
- Modify: `crates/moredakka-core` into lib + thin bin
- Modify: `src/moredakka/cli.py`
- Delete or freeze: Python duplicates in `context.py` and `doctor.py` once cutover is complete
- Test: golden parity fixtures shared across both surfaces

Steps:
1. Make Rust `doctor` and `pack` JSON contracts authoritative.
2. Call Rust from Python for doctor/pack.
3. Lock down parity with golden fixtures.
4. Remove duplicate Python logic once parity is trusted.

Verification:
- Python and Rust doctor/pack outputs match the same fixtures
- only one implementation defines packet semantics

## Tranche 5: Report beauty and evidence-class separation

Objective: reports become calm, dense, falsifiable, and timeless.

Files:
- Modify: Rust report modules
- Modify: `src/moredakka/report.py` or replace with Rust-backed rendering
- Modify: `SPEC.md`

Steps:
1. Represent explicit sections for facts, inferences, and unresolved ambiguity.
2. Add stop reason, loss accounting, role status, and provenance summary to reports.
3. Keep markdown concise and terminal-native.
4. Keep JSON richly typed for machine use.

Verification:
- every report shows what was observed locally vs inferred by models
- truncation and omission are explicit
- final path selection is justified by preserved evidence

---

## Non-goals during this migration

- Do not turn the tool into a general agent platform.
- Do not migrate provider transport into Rust prematurely.
- Do not add ornamental UI or orchestration pageantry.
- Do not widen the product beyond “one disciplined next move on the live work surface.”

---

## Immediate next implementation tranche

If only one tranche is executed next, do this:

1. add the Rust-backed run journal
2. preserve provider usage and response provenance in it
3. surface invocation_id, stop_reason, and role accounting in final report output

That is the shortest path from “disgusting” to materially more beautiful.
