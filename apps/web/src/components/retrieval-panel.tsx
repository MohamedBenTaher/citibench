import { StatusPill } from "@/components/status-pill";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import type { RetrievalReport, RetrievalRow } from "@/lib/types";

function MatrixCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "good" | "bad" | "neutral";
}) {
  const toneClass =
    tone === "good" ? "text-success" : tone === "bad" ? "text-destructive" : "text-foreground";
  return (
    <div className="bg-background px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </p>
      <p className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

export function RetrievalPanel({ report }: { report: RetrievalReport | null }) {
  if (!report?.present || !report.retrieval) {
    return (
      <p className="text-sm text-muted-foreground">
        No retrieval run yet. Run the retrieval evaluation to measure whether the gold source
        document is actually found.
      </p>
    );
  }

  const metrics = report.retrieval;
  const k = report.k ?? 8;
  const calibration = report.calibration;
  const failing = report.rows.filter((row) => row.answerable && (row.recall ?? 0) < 1);

  return (
    <div className="space-y-5">
      <div className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-3">
        <MatrixCell label={`Recall@${k}`} value={metrics.recall_at_k} tone="neutral" />
        <MatrixCell label="MRR" value={metrics.mrr} tone="neutral" />
        <MatrixCell label={`nDCG@${k}`} value={metrics.ndcg_at_k} tone="neutral" />
      </div>
      <p className="text-xs text-muted-foreground">
        {metrics.n_scored} answerable · {metrics.unanswerable} unanswerable · mode{" "}
        <code className="font-mono">{report.mode}</code>
        {report.measured_at ? ` · ${report.measured_at.slice(0, 16).replace("T", " ")}` : ""}
      </p>

      {report.variants && report.variants.length > 0 ? (
        <div className="space-y-2">
          <h3 className="font-heading text-sm font-medium tracking-tight">
            Configuration comparison
          </h3>
          <div className="overflow-hidden border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Variant</TableHead>
                  <TableHead className="text-right">Recall@{k}</TableHead>
                  <TableHead className="text-right">MRR</TableHead>
                  <TableHead className="text-right">nDCG@{k}</TableHead>
                  <TableHead className="text-right">Δ nDCG</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.variants.map((variant, index) => {
                  const baseline = report.variants?.[0]?.retrieval;
                  const delta =
                    baseline != null ? variant.retrieval.ndcg_at_k - baseline.ndcg_at_k : 0;
                  return (
                    <TableRow key={variant.name} data-state={index === 0 ? "selected" : undefined}>
                      <TableCell className="text-sm font-medium">
                        {variant.name}
                        {index === 0 ? (
                          <span className="ml-2 text-[11px] text-muted-foreground">baseline</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {variant.retrieval.recall_at_k.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {variant.retrieval.mrr.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {variant.retrieval.ndcg_at_k.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {index === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <span className={delta >= 0 ? "text-success" : "text-destructive"}>
                            {delta >= 0 ? "+" : ""}
                            {delta.toFixed(3)}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <p className="text-xs text-muted-foreground">
            Same {metrics.n_scored} labeled questions for every variant. Chunk size is fixed at
            index time, so it is not a query-time toggle.
          </p>
        </div>
      ) : null}

      {calibration ? (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="font-heading text-sm font-medium tracking-tight">Answerability</h3>
            <span className="text-xs text-muted-foreground">
              {calibration.kind === "live" ? "end-to-end generate" : "retrieval gate"}
            </span>
          </div>
          <div className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2">
            <MatrixCell
              label="Answered · answerable (good)"
              value={calibration.answered_answerable}
              tone="good"
            />
            <MatrixCell
              label="Answered · unanswerable (false answer)"
              value={calibration.answered_unanswerable}
              tone={calibration.answered_unanswerable > 0 ? "bad" : "neutral"}
            />
            <MatrixCell
              label="Abstained · answerable (false abstain)"
              value={calibration.abstained_answerable}
              tone={calibration.abstained_answerable > 0 ? "bad" : "neutral"}
            />
            <MatrixCell
              label="Abstained · unanswerable (good)"
              value={calibration.abstained_unanswerable}
              tone="good"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            false-answer {formatNumber(calibration.false_answer_rate)} · false-abstain{" "}
            {formatNumber(calibration.false_abstain_rate)}
          </p>
        </div>
      ) : null}

      {failing.length > 0 ? (
        <div className="space-y-2">
          <h3 className="font-heading text-sm font-medium tracking-tight">
            Retrieval misses ({failing.length})
          </h3>
          <div className="overflow-hidden border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Question</TableHead>
                  <TableHead className="hidden md:table-cell">Gold source</TableHead>
                  <TableHead className="w-24 text-right">First hit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {failing.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="max-w-md whitespace-normal text-sm">
                      {row.question}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {row.gold_doc_ids.join(", ")}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {row.first_relevant_rank ? (
                        <Badge variant="outline">#{row.first_relevant_rank}</Badge>
                      ) : (
                        <StatusPill tone="danger" withIcon={false}>
                          not found
                        </StatusPill>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}

      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">
          All labeled questions ({report.rows.length})
        </summary>
        <div className="mt-2 overflow-hidden border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead className="w-24">Recall</TableHead>
                <TableHead className="w-24">First hit</TableHead>
                <TableHead className="hidden w-24 sm:table-cell">Gate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.rows.map((row: RetrievalRow) => (
                <TableRow key={row.id}>
                  <TableCell className="max-w-md whitespace-normal text-sm">
                    {row.question}
                    {!row.answerable ? (
                      <span className="ml-2 text-[11px] text-muted-foreground">(unanswerable)</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {row.answerable ? formatNumber(row.recall) : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {row.answerable ? (row.first_relevant_rank ?? "miss") : "—"}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {row.gate_answered == null ? (
                      "—"
                    ) : row.gate_answered ? (
                      <StatusPill tone="success" withIcon={false}>
                        answered
                      </StatusPill>
                    ) : (
                      <StatusPill tone="warning" withIcon={false}>
                        abstained
                      </StatusPill>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </details>
    </div>
  );
}
