from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.parser import ParsedSection


@dataclass(slots=True)
class TextChunk:
    ordinal: int
    section_title: str | None
    page_number: int | None
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    # A stable approximation that does not bind the project to one tokenizer.
    return max(1, (len(text) + 3) // 4)


def chunk_sections(
    sections: list[ParsedSection],
    target_chars: int = 1400,
    overlap_chars: int = 180,
) -> list[TextChunk]:
    if target_chars < 200:
        raise ValueError("target_chars must be >= 200")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be >= 0 and < target_chars")

    chunks: list[TextChunk] = []
    ordinal = 0
    for section in sections:
        for content in _split_text(section.text, target_chars, overlap_chars):
            chunks.append(
                TextChunk(
                    ordinal=ordinal,
                    section_title=section.title,
                    page_number=section.page_number,
                    content=content,
                    token_count=estimate_tokens(content),
                )
            )
            ordinal += 1
    return chunks


def _split_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) == 1:
        return _sliding_windows(text, target_chars, overlap_chars)

    result: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= target_chars:
            current = candidate
            continue
        if current:
            result.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
            while len(current) > target_chars:
                windows = _sliding_windows(current, target_chars, overlap_chars)
                result.extend(windows[:-1])
                current = windows[-1]
        else:
            windows = _sliding_windows(paragraph, target_chars, overlap_chars)
            result.extend(windows[:-1])
            current = windows[-1]
    if current:
        result.append(current)
    return [r.strip() for r in result if r.strip()]


def _sliding_windows(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + target_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            windows.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap_chars)
    return windows
