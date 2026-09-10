from pathlib import Path

from app.ingestion.parser import parse_document


def test_markdown_parser_splits_headings(tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text("# Title\nIntro text.\n\n## Limits\n60 requests per minute.", encoding="utf-8")
    sections = parse_document(path)
    assert [s.title for s in sections] == ["Title", "Limits"]
    assert "60 requests" in sections[1].text
