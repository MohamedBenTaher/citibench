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
          <Link href="/corpus">Corpus</Link> — frozen manifest of 14 public
          Kubernetes and Azure documents.
        </li>
        <li>
          <Link href="/playground">Playground</Link> — query scratch pad; not a
          chat surface.
        </li>
        <li>
          <Link href="/traces">Traces</Link> — future RunTrace viewer.
        </li>
        <li>
          <Link href="/evals">Evals</Link> — future RAGAS / known-bad runner.
        </li>
      </ul>
    </>
  );
}
