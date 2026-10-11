# Plan 011: Add OSTEP PDFs with real multi-page parse

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/parse_doc.py apps/api/pipeline.py apps/api/manifest.py corpus/sources.yaml scripts/crawl_manifest.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (license accuracy; PDF text extraction quality)
- **Depends on**: plan 010 (`corpus/sources.yaml`, crawler, grown manifest)
- **Category**: direction (I1 / C5)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The corpus is all web pages. OSTEP (*Operating Systems: Three Easy Pieces*,
Arpaci-Dusseau) is a **legitimately free** systems textbook, and its multi-page
PDF chapters are exactly the kind of "long document" material a retrieval bench
should handle. This plan adds OSTEP chapters from the **official free source
only**, proves the PDF parser extracts multiple pages and per-chunk page
numbers, and records the license. It does not add any pirated book.

## Current state

- `apps/api/parse_doc.py:31-53` already parses PDFs with pypdf and emits
  `[page N]` markers:
  ```python
  reader = PdfReader(str(path))
  pages: list[str] = []
  for i, page in enumerate(reader.pages, start=1):
      extracted = page.extract_text() or ""
      pages.append(f"[page {i}]\n{extracted.strip()}")
  text = "\n\n".join(part for part in pages if part.strip())
  ...
  return ParsedDocument(text=text, page_count=len(reader.pages), content_type="application/pdf")
  ```
  `ParsedDocument` is `text, page_count, content_type` (`parse_doc.py:24-28`).
  PDF sniff checks content-type, `.pdf` suffix, or `%PDF` magic (`parse_doc.py:38-41`).
- `apps/api/pipeline.py:182` + `240-244` derive per-chunk page from the marker:
  ```python
  def _page_for_chunk(text: str, fallback_pages: int) -> int:
      match = _PAGE_MARK.search(text)
      if match:
          return int(match.group(1))
      return 1 if fallback_pages >= 1 else 0
  ```
  `_PAGE_MARK = re.compile(r"\[page (\d+)\]")` (`pipeline.py:31`).
- `apps/api/snapshot.py:175-178` names a PDF body `document.pdf`; `sha256` +
  `meta.json` are written the same as HTML.
- Plan 010 creates `corpus/sources.yaml` and `scripts/crawl_manifest.py`, which
  **skips `.pdf` links** (HTML-only crawl). OSTEP rows therefore need an explicit
  PDF path in the source config.
- `apps/api/requirements.txt` pins `pypdf==6.1.1`.
- `corpus/MANIFEST.md` `pages` column is documentation only; real page count is
  `documents.page_count` from `parse_doc` (`pipeline.py:208`).

**License to verify before adding anything**: open the OSTEP site
(`https://pages.cs.wisc.edu/~remzi/OSTEP/`) and the book's copyright/license
page. Record the exact license string (the project's site states the terms for
the free chapters). If the terms do not permit automated snapshotting/redistribution
by this open-source bench, **stop and drop the source**.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Parse one PDF | `.venv/bin/python -c "from parse_doc import parse_snapshot; ..."` | `page_count > 1` |
| Rebuild manifest | `.venv/bin/python scripts/crawl_manifest.py --write` | OSTEP rows present |
| PDF page smoke | `.venv/bin/python -m pytest apps/api/tests/test_parse_doc.py` | pass |

## Scope

**In scope**:

- `corpus/sources.yaml` — add an `ostep` source (explicit PDF URL list).
- `scripts/crawl_manifest.py` — support an explicit `pdfs:` list that bypasses
  link discovery and emits rows for each PDF URL.
- `corpus/MANIFEST.md` — regenerated with OSTEP rows (`doc_type: book_chapter`).
- `apps/api/tests/test_parse_doc.py` — a multi-page assertion (may already exist;
  extend it if not).
- `apps/api/tests/test_manifest.py` — include OSTEP in the size/id/license checks.
- `docs/decision-trail.tsv` — append the OSTEP license row.
- `plans/README.md` status row.

**Out of scope**:

- Any non-official mirror, torrent, or "combined ebook" download.
- Section-aware PDF chunking beyond the `[page N]` markers (plan 012 may add
  section paths; do not build it here).
- Re-ingesting the corpus (plan 013) or README counts.
- Changing `parse_doc._parse_pdf`'s full-document RAM strategy (that is plan
  008.2's gigabyte path, explicitly out of scope here).

## Git workflow

- Branch: `advisor/011-ostep-pdfs`
- Commit message: `Add free OSTEP chapters as multi-page PDFs.`
- Do NOT commit `corpus/raw/**` or downloaded PDF bytes.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Verify the OSTEP license

Open the OSTEP site and the license/copyright page. Record the exact string in a
comment next to the source in `corpus/sources.yaml` and in the decision trail.
If the terms forbid machine snapshotting, STOP.

### Step 2: Extend `sources.yaml` with explicit PDF URLs

Add:
```yaml
  - key: ostep
    product: OSTEP
    source: pages.cs.wisc.edu
    doc_type: book_chapter
    license: "<exact string from Step 1>"
    kind: pdf
    pdfs:
      - https://pages.cs.wisc.edu/~remzi/OSTEP/Intro.pdf
      - https://pages.cs.wisc.edu/~remzi/OSTEP/threads-intro.pdf
      # … one entry per official chapter PDF (list every chapter you include)
    max_pages: 60
```
Use the **official chapter PDF filenames linked from the OSTEP site**; do not
guess URLs. Include the front-matter/appendix only if it is offered as a PDF on
the same site.

**Verify**: every URL opens and returns `%PDF` (e.g.
`curl -sSI <url> | head` shows `content-type: application/pdf`, or
`curl -sS <url> | head -c 5` is `%PDF-`).

### Step 3: Teach the crawler about `kind: pdf`

In `scripts/crawl_manifest.py`:
- If a source has `kind: pdf`, do **not** crawl for links; iterate `pdfs`
  directly and emit one row per URL with `pages` left as `0` (the real count is
  parsed at ingest).
- Title: derive from the PDF filename slug unless a `titles:` map is provided
  next to `pdfs:`. `id` uses the same deterministic slug (prefix `ostep-`).
- Keep `doc_type/product/source/license/version_or_snapshot` identical to plan 010.
- Verify each PDF URL is on the `source` host before emitting; skip and report
  off-host URLs.

**Verify**: rebuild with `--source ostep --write`, then
`.venv/bin/python -c "import sys;sys.path.insert(0,'apps/api');from manifest import parse_manifest;from pathlib import Path;d=[x for x in parse_manifest(Path('corpus/MANIFEST.md')) if x.license and 'ostep' in x.id];print(len(d))"`
→ equal to the number of `pdfs:` entries.

### Step 4: Prove real multi-page parse

Fetch one chapter snapshot locally (via the plan 009/010 snapshot helper or a
temporary `snapshot_url` call) and parse it:
```
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "apps/api")
from parse_doc import parse_snapshot
from pathlib import Path
snap = Path("corpus/raw/<ostep-id>/document.pdf")
parsed = parse_snapshot(snap, "application/pdf")
assert parsed.page_count > 1, parsed.page_count
assert "[page 1]" in parsed.text and "[page 2]" in parsed.text
print(parsed.page_count, len(parsed.text))
PY
```
If `page_count == 1` or the text is empty, STOP: extraction failed for that PDF.

Extend `apps/api/tests/test_parse_doc.py` with a multi-page case using a small
generated PDF (pypdf can write one) — do not commit a real book chapter as a
fixture.

### Step 5: Decision trail + tests

- Append `docs/decision-trail.tsv` row:
  `<today>\tc5-ostep\tOSTEP chapters (<license>), official free PDFs; multi-page parse verified\tPASS`.
- Confirm `test_manifest.py`'s big-freeze floor test still passes with the extra
  rows and that the OSTEP license string is non-empty.

**Verify**: `.venv/bin/python -m pytest apps/api` → all pass.

## Test plan

- `test_parse_doc.py`: generated 2+ page PDF → `page_count >= 2`, `[page 1]` and
  `[page 2]` present, `application/pdf` content type.
- `test_manifest.py`: OSTEP rows have non-empty license; big-freeze floor still holds.
- No network in CI. The one-time chapter fetch is manual and documented.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] `corpus/sources.yaml` has an `ostep` source with explicit official `pdfs:`
      and the verified license string.
- [ ] `corpus/MANIFEST.md` contains the OSTEP rows (`doc_type: book_chapter`).
- [ ] A real OSTEP chapter parses with `page_count > 1` and `[page N]` markers
      (evidence pasted in the PR/commit body); `test_parse_doc.py` covers multi-page.
- [ ] `pytest apps/api` exits 0.
- [ ] `docs/decision-trail.tsv` has the OSTEP license row.
- [ ] No pirated/non-official source is referenced anywhere (`git grep -i ostep`).
- [ ] `plans/README.md` row 011 is DONE.

## STOP conditions

- The OSTEP license does not clearly permit snapshotting — stop and drop OSTEP.
- A chapter PDF cannot be found from the official site (guessed URL) — stop.
- PDF extraction yields empty text for a chapter (scanned images) — stop; do not
  add OCR here.
- The crawler emits an OSTEP URL on a non-official host — stop and fix the host check.

## Maintenance notes

- Plan 012 will add `section`/page metadata; OSTEP chunks already carry `page`
  from the markers and can gain a coarse `section` later.
- Plan 013's `/corpus/stats` page count must include OSTEP pages; if it does not,
  the PDF path lost its markers — review `_page_for_chunk`.
- Reviewers: confirm no binary book is committed and the license row is accurate.
- Deferred: page-at-a-time PDF parsing for very large books (plan 008.2).
