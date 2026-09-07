# Evals + Traces — hiring-manager demo surface

Audience: a reviewer opening the Compose web UI. First impression is **measurable RAG**, not a chat bubble. Start on `/evals` (or a failing `/traces?run_id=` receipt). `/` stays a boring index. Playground is how you create a run, not the pitch.

Value line (Evals): *CI fails when faithfulness drops below 0.7. Every hop is a receipt.*

## Constraints

- shadcn/ui only: Table, Card, Badge, Separator, Skeleton, Alert, Button, Input (Tabs unused; filter chips are Buttons).
- FastAPI contracts unchanged. UI may read extra fields already on the artifact (`known_bad.rows[].run_id`).
- No connectors, node editor, settings, or chat homepage.
- Empty / loading / error never render a blank white main: Skeleton or Alert.

## Evals (`/evals`)

Layout, top to bottom:

1. **Header + primary CTA.** Title, one-sentence value line, and a default **Refresh last scores** button (re-fetches `/evals/latest` + `/evals/redteam`; does not invoke the Python harness). Mode badge (`mock` | `live`), last-run timestamp, and gate chip sit in the same strip so the CTA is not buried in a card footer.
2. **Hero metrics.** Three cards: faithfulness, context precision, answer relevancy.
   - Faithfulness is the **CI gate**. Threshold **0.7**. Pass/fail Badge on the card. Score is mono tabular.
   - Companions are **logged only** (do not gate CI). Same score + diff treatment.
   - Each card shows **diff vs previous** (`+0.012` / `−0.012` / `0.000` / `n/a`).
3. **Receipts.** Known-bad rows and `failing_run_ids`. Always visible when the artifact exists — even when the phase is clean — so abstention is one click from a Trace. Failed / leaked rows use destructive Badge + `data-state=selected`. Each row with a `run_id` links to `/traces?run_id=`.
4. **Redteam.** Ten Contract A cases as a dense table: `id`, `attack_type` (Badge), result (`blocked` | `failed` | `not run`), Trace link. Summary line: blocked count, gate, mode, finished_at. No CLI dump as the first paragraph.

Copy: short. Do not lead with `python -m citebench.eval…`. Commands stay in README / DECISIONS.

### States

| State | Treatment |
| --- | --- |
| Loading | Page-level Skeleton: metric cards + table rows. |
| Error | Existing RouteError Alert + Retry. |
| No CI artifact | Alert: run the harness, then refresh. Metric cards show em dashes, not an empty main. |
| No redteam cases | Destructive Alert pointing at `evals/redteam.jsonl`. |
| Gate failed | Destructive Alert with `gate_reason` above the metric strip. |

## Traces (`/traces`)

Deep link: `?run_id=` (existing search param). Evals receipts and redteam rows use it.

Desktop (**lg+**): split view — dense run list on the left, detail on the right. Mobile: list then detail stacked.

**Run list**

- Columns: query snippet, path, latency, cost, time.
- Path Badge: `generate` | `abstain` | `error` (failed wins over abstain).
- Selected row: `data-state=selected` + muted background.
- Filter chips (client-side): All / Generate / Abstain / Error.
- Refresh is secondary, next to filters — not the page hero.

**Detail panel**

- Identity: query, path, model, latency, cost **and `cost_method`** (`citebench.cost.v1`).
- Nested span tree: `retrieve → rerank → generate|abstain`, indented by `parent_id`. Status Badge per span.
- Citations: `text_ref` table only (no chunk body dump). Generate spans list `citation_text_refs`; retrieve/rerank reuse the pointer table.
- Extra span attributes behind a native `<details>` (“Attributes”), never a raw JSON dump as the default view.

**Empty**

- No runs: Alert + one line: ask a question on Playground to create a `RunTrace`. Link to `/playground`. Do not redirect `/` to chat.
- No selection: “Select a run” in the detail pane.
- Missing `run_id`: Alert in the detail pane (keep the list).

## Navigation

Header order: **Evals · Traces · Corpus · Playground**. Index cards follow the same order so a reviewer does not land on a chat surface first.

## Out of scope

Corpus growth, Playground redesign (aside from inbound links), MCP, backend eval logic, new API fields.
