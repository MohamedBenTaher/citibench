from pathlib import Path

from pypdf import PdfWriter

from parse_doc import parse_snapshot


def _write_multipage_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=432, height=648)
    with path.open("wb") as handle:
        writer.write(handle)


def test_pdf_reports_multiple_pages_and_markers(tmp_path: Path) -> None:
    pdf = tmp_path / "document.pdf"
    _write_multipage_pdf(pdf, pages=3)
    parsed = parse_snapshot(pdf, "application/pdf")
    assert parsed.page_count == 3
    assert parsed.content_type == "application/pdf"
    assert "[page 1]" in parsed.text
    assert "[page 2]" in parsed.text
    assert "[page 3]" in parsed.text


def test_html_headings_become_section_markers(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text(
        "<html><body><main><h1>Pods</h1><p>intro</p><h2>Lifecycle</h2><p>body</p></main></body></html>",
        encoding="utf-8",
    )
    parsed = parse_snapshot(html, "text/html")
    assert "# Pods" in parsed.text
    assert "## Lifecycle" in parsed.text


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
