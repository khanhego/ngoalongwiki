"""Utilities dùng chung cho scripts trích xuất wiki."""

import re
import unicodedata
from typing import Optional, Tuple

ROMAN_SECTION = re.compile(
    r"^(I{1,3}|IV|V|VI{0,3}|IX|X{1,3})\.\s+(.+)$", re.UNICODE
)
NUMBER_SECTION = re.compile(r"^(\d+)\.\s+(.+)$", re.UNICODE)

BULLET_PREFIX = re.compile(r"^[▪•o\-–—]\s", re.UNICODE)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text.strip())
    return text[:80] or "section"


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def is_likely_heading(line: str) -> Optional[Tuple[str, str]]:
    line = normalize_line(line)
    if not line or len(line) > 120:
        return None

    m = ROMAN_SECTION.match(line)
    if m:
        return ("h2", f"{m.group(1)}. {m.group(2).strip()}")

    m = NUMBER_SECTION.match(line)
    if m:
        title = m.group(2).strip()
        if len(title) < 3 or len(title) > 80:
            return None
        if title[0].isupper() or title.isupper():
            return ("h3", f"{m.group(1)}. {title}")

    return None


def is_docx_heading(line: str) -> Optional[Tuple[str, str]]:
    """Nhận diện heading trong DOCX (style Normal, dựa vào pattern text)."""
    found = is_likely_heading(line)
    if found:
        return found

    line = normalize_line(line)
    if not line or len(line) > 80 or len(line) < 3:
        return None
    if BULLET_PREFIX.match(line):
        return None

    sentence_markers = [" là ", " sẽ ", " có ", " được ", " trong ", " với ", " khi ", " như ", " để "]
    lower = line.lower()
    if any(m in lower for m in sentence_markers) and not line.endswith(":"):
        return None

    if line.isupper() and len(line) < 50:
        return ("h1" if len(line) > 20 else "h2", line)

    words = line.split()
    if len(words) <= 8 and words[0][0].isupper():
        if line.endswith(":"):
            return ("h3", line)
        if len(words) <= 6 and not line.endswith("."):
            return ("h2", line)

    return None
