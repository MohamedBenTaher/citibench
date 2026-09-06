export default function EvalsPage() {
  return (
    <>
      <h1>Evals</h1>
      <p>
        Placeholder for the eval runner. Faithfulness 0.7 is a future CI gate
        only; this page reports no scores. See{" "}
        <code>evals/splits/known_bad.jsonl</code> and{" "}
        <code>docs/contracts/eval-jsonl.md</code>.
      </p>
    </>
  );
}
