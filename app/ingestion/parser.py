from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup


@dataclass(slots=True)
class ParsedSection:
    title: str | None
    text: str
    page_number: int | None = None


class UnsupportedDocumentError(ValueError):
    pass


SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".html", ".htm"}


def parse_document(path: Path) -> list[ParsedSection]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in {".md", ".markdown"}:
        return _parse_markdown(path)
    if suffix in {".html", ".htm"}:
        return _parse_html(path)
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [ParsedSection(title=path.stem, text=_normalize(text))]
    raise UnsupportedDocumentError(f"unsupported file type: {suffix}")


def _parse_pdf(path: Path) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            blocks = page.get_text("blocks")
            text = "\n\n".join(block[4].strip() for block in blocks if block[4].strip())
            text = _normalize(text)
            if text:
                sections.append(
                    ParsedSection(title=f"Page {index + 1}", text=text, page_number=index + 1)
                )
    return sections


def _parse_markdown(path: Path) -> list[ParsedSection]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    sections: list[ParsedSection] = []
    current_title: str | None = path.stem
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = _normalize("\n".join(buffer))
        if text:
            sections.append(ParsedSection(title=current_title, text=text))
        buffer = []

    for line in lines:
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            flush()
            current_title = match.group(1).strip()
        else:
            buffer.append(line)
    flush()
    return sections


def _parse_html(path: Path) -> list[ParsedSection]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    sections: list[ParsedSection] = []
    current_title: str | None = path.stem
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = _normalize("\n".join(buffer))
        if text:
            sections.append(ParsedSection(title=current_title, text=text))
        buffer = []

    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name and element.name.startswith("h"):
            flush()
            current_title = text
        else:
            buffer.append(text)
    flush()
    return sections


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
