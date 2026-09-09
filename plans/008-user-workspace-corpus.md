# Plan 008: User-dictated workspace corpus

> Operator request 2026-09-09: the floor should accept a URL or upload, not
> only `corpus/MANIFEST.md`. Gigabyte sources need streaming, quantization,
> hierarchical embeddings, and structure-aware chunking. Do not mix this
> into the 14-doc eval freeze.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH (SSRF, disk, RAM, eval leakage)
- **Depends on**: leftover ingest hardening (`a932dda`)
- **Category**: product + retrieve scale
- **Planned at**: commit `a932dda`, 2026-09-09

## Product rule

The **bench freeze** (14 Kubernetes/Azure URLs, RAGAS/redteam) stays pinned.
User sources live in `documents.origin = 'user'`. Freeze ingest wipe/delete
unknown must not drop user rows. Live eval retrieve stays freeze-only.

Playground retrieve defaults to **all** origins so a user can ask over what
they just indexed.

## Phases

### 008.1 (this slice) — isolation + bounded ingest

- `origin` on documents (`freeze` | `user`)
- HTTPS-only user URLs; reject non-public resolved addresses
- Stream snapshot to disk with `CITEBENCH_USER_SOURCE_MAX_BYTES` (default 64 MiB)
- Structure-aware chunk windows for user docs (headings / `[page N]`, then 512/64)
- Corpus UI: paste a URL; optional file upload same cap
- Tests: fetch guard, stream cap, freeze wipe leaves user rows (unit)

STOP: do not raise the cap to gigabytes in this slice. Do not load the whole
file into `response.content`.

### 008.2 — gigabyte path

- Page-at-a-time PDF parse (no full-text RAM)
- Embed in batches with spill to Postgres
- Optional object store for raw bytes (not `corpus/raw` on the API disk)
- ANN index (HNSW) once chunk count leaves sequential `<=>` range
- `halfvec` / int8 quantization of nomic 768 (Matryoshka prefix first)

### 008.3 — hierarchy

- Leaf chunks (current)
- Section/doc summary embeddings (`layer`, `parent_id`)
- Retrieve: coarse then fine (parent then children)

## Out of scope here

- Second embed or chat vendor
- Chat homepage
- Invented eval scores on user PDFs
- Fetching private/RFC1918 hosts
