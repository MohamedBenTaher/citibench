from pathlib import Path

from parse_doc import parse_snapshot


def test_html_extracts_main_and_counts_one_page(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text(
        """
        <html><body>
          <nav>skip</nav>
          <main>
            <h1>Pods</h1>
            <p>A Pod is the smallest deployable unit.</p>
          </main>
          <footer>copyright</footer>
        </body></html>
        """,
        encoding="utf-8",
    )
    parsed = parse_snapshot(html, "text/html")
    assert parsed.page_count == 1
    assert "Pods" in parsed.text
    assert "smallest deployable" in parsed.text
    assert "skip" not in parsed.text
    assert "copyright" not in parsed.text
