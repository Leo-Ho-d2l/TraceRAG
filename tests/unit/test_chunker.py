from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import ParsedSection


def test_chunker_preserves_section_metadata():
    sections = [ParsedSection(title="Limits", text="a" * 1600, page_number=3)]
    chunks = chunk_sections(sections, target_chars=500, overlap_chars=50)
    assert len(chunks) >= 3
    assert all(chunk.section_title == "Limits" for chunk in chunks)
    assert all(chunk.page_number == 3 for chunk in chunks)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_chunker_rejects_invalid_overlap():
    sections = [ParsedSection(title="x", text="hello")]
    try:
        chunk_sections(sections, target_chars=300, overlap_chars=300)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
