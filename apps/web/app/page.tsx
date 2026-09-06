import Link from "next/link";

export default function IndexPage() {
  return (
    <>
      <h1>Citebench</h1>
      <p>
        Index of placeholder surfaces. This is not a chat homepage and does not
        run retrieval.
      </p>
      <ul>
        <li>
          <Link href="/corpus">Corpus</Link> — frozen 14-doc index counts
          (docs, pages, chunks, last index, failures).
        </li>
        <li>
          <Link href="/playground">Playground</Link> — single-ask generate; not a
          chat surface.
        </li>
        <li>
          <Link href="/traces">Traces</Link> — RunTrace list (Langfuse + local
          fallback).
        </li>
        <li>
          <Link href="/evals">Evals</Link> — future RAGAS / known-bad runner.
        </li>
      </ul>
    </>
  );
}
