"""Format text, tables và layout từ PDF PyMuPDF."""

import html
import re
from typing import List, Optional, Tuple

import fitz

from common import is_likely_heading, normalize_line

BULLET_MARKERS = {
    "▪": 2,
    "•": 3,
    "◦": 3,
    "‣": 3,
    "▫": 2,
}


def _rect_overlap_ratio(inner, outer) -> float:
    """Tỷ lệ diện tích inner nằm trong outer."""
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    x0, y0 = max(ix0, ox0), max(iy0, oy0)
    x1, y1 = min(ix1, ox1), min(iy1, oy1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    inner_area = max((ix1 - ix0) * (iy1 - iy0), 1)
    return inter / inner_area


def get_table_bboxes(page: fitz.Page) -> List[tuple]:
    bboxes = []
    try:
        finder = page.find_tables()
        for table in finder.tables:
            bboxes.append(tuple(table.bbox))
    except Exception:
        pass
    return bboxes


def _in_table(bbox, table_bboxes, threshold: float = 0.5) -> bool:
    line_box = (bbox[0], bbox[1], bbox[2], bbox[3])
    for tb in table_bboxes:
        if _rect_overlap_ratio(line_box, tb) > threshold:
            return True
    return False


def extract_text_lines(page: fitz.Page, table_bboxes: List[tuple]) -> List[dict]:
    """Trích từng dòng text kèm vị trí, bỏ qua vùng bảng."""
    lines = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line["bbox"]
            if _in_table(bbox, table_bboxes):
                continue
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            text = text.replace("\u00a0", " ").strip()
            if not text:
                continue
            lines.append({
                "x0": bbox[0],
                "y0": bbox[1],
                "y1": bbox[3],
                "text": text,
            })
    lines.sort(key=lambda ln: (ln["y0"], ln["x0"]))
    return lines


def _indent_level(x0: float, base_x: float) -> int:
    delta = x0 - base_x
    if delta < 12:
        return 0
    if delta < 35:
        return 1
    if delta < 55:
        return 2
    return 3


def _strip_bullet(text: str) -> Tuple[int, str]:
    text = text.strip()
    for marker, level in BULLET_MARKERS.items():
        if text.startswith(marker):
            rest = text[len(marker):].lstrip(" \t")
            return level, rest
    if text.startswith("o ") or text.startswith("o\t"):
        return 1, text[2:].strip()
    if text.startswith("- "):
        return 1, text[2:].strip()
    if re.match(r"^\d+\.\s", text) and len(text) < 80:
        return 0, text  # numbered handled separately
    return -1, text


def _should_merge(cur: dict, nxt: dict) -> bool:
    ct = cur["text"].strip()
    nt = nxt["text"].strip()

    if is_likely_heading(normalize_line(nt)):
        return False

    # Bullet mới cùng cấp (▪, •, o )
    if nt[:1] in BULLET_MARKERS or nt.startswith("o "):
        if abs(nxt["x0"] - cur["x0"]) <= 8 and ct.endswith((".", ":", "?", "!", "…")):
            return False
        if nxt["x0"] >= cur["x0"] - 5:
            return False

    # Cùng cột → gộp dòng wrap PDF
    if abs(nxt["x0"] - cur["x0"]) <= 12:
        return True

    # Dòng con thụt sâu hơn nhưng là wrap (không có bullet mới)
    if nxt["x0"] > cur["x0"] and nt[:1] not in BULLET_MARKERS and not nt.startswith("o "):
        return True

    return False


def merge_lines(lines: List[dict]) -> List[dict]:
    if not lines:
        return []
    merged = [dict(lines[0])]
    for nxt in lines[1:]:
        cur = merged[-1]
        if _should_merge(cur, nxt):
            cur["text"] = cur["text"].rstrip() + " " + nxt["text"].lstrip()
            cur["y1"] = nxt["y1"]
        else:
            merged.append(dict(nxt))
    return merged


def _clean_cell(text) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("\n", "<br>")
    return html.escape(text, quote=False).replace("&lt;br&gt;", "<br>")


def table_to_html(table) -> str:
    data = table.extract()
    if not data:
        return ""

    rows_html = []
    for row in data:
        if not any(cell not in (None, "") for cell in row):
            continue
        cells = "".join(
            f"<td>{_clean_cell(cell)}</td>" for cell in row
        )
        rows_html.append(f"<tr>{cells}</tr>")

    if not rows_html:
        return ""

    return (
        '<table class="wiki-table">\n'
        + "\n".join(rows_html)
        + "\n</table>"
    )


def extract_tables(page: fitz.Page) -> List[dict]:
    items = []
    try:
        finder = page.find_tables()
        for table in finder.tables:
            html_table = table_to_html(table)
            if not html_table:
                continue
            bbox = table.bbox
            items.append({
                "type": "table",
                "y0": bbox[1],
                "x0": bbox[0],
                "html": html_table,
            })
    except Exception:
        pass
    return items


def lines_to_markdown(lines: List[dict]) -> str:
    """Chuyển dòng đã merge thành markdown có bullet/paragraph."""
    if not lines:
        return ""

    base_x = min(ln["x0"] for ln in lines)
    out: List[str] = []

    for ln in lines:
        raw = ln["text"]
        bullet_level, content = _strip_bullet(raw)
        indent = _indent_level(ln["x0"], base_x)
        level = bullet_level if bullet_level >= 0 else indent

        content = normalize_line(content)
        if not content:
            continue

        heading = is_likely_heading(content)
        if heading and level == 0:
            _, title = heading
            out.append(f"**{title}**")
            continue

        if level <= 0:
            out.append(content)
        elif level == 1:
            out.append(f"- {content}")
        elif level == 2:
            out.append(f"  - {content}")
        else:
            out.append(f"    - {content}")

    return "\n\n".join(out)


def group_lines_by_gap(lines: List[dict], gap: float = 16) -> List[List[dict]]:
    """Tách nhóm dòng theo khoảng cách dọc (giữa các đoạn/bảng)."""
    if not lines:
        return []
    groups: List[List[dict]] = [[lines[0]]]
    for ln in lines[1:]:
        prev = groups[-1][-1]
        if ln["y0"] - prev["y1"] > gap:
            groups.append([ln])
        else:
            groups[-1].append(ln)
    return groups


SECTION_INLINE = re.compile(
    r"^(\d+)\.\s+(.+?)(?:\s*[-–—]\s*(.+))?$", re.UNICODE
)


def parse_section_heading(line: str) -> Optional[Tuple[str, str, str]]:
    """Parse '1. Bạc - mô tả' → (level, title, inline_rest)."""
    line = line.strip().strip("*").strip()
    found = is_likely_heading(line)
    if found:
        return found[0], found[1], ""

    m = SECTION_INLINE.match(line)
    if not m:
        return None

    num, title_part, rest = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
    title = f"{num}. {title_part}"
    if len(title_part) > 80:
        return None
    if not (title_part[0].isupper() or title_part.isupper()):
        return None
    return "h3", title, rest


def split_text_by_headings(text: str) -> List[dict]:
    """Tách block text theo heading numbered / Roman."""
    chunks: List[dict] = []
    buffer: List[str] = []

    def flush_buffer():
        if buffer:
            chunks.append({"heading": None, "text": "\n\n".join(buffer)})
            buffer.clear()

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue

        first_line = para.split("\n")[0].strip()
        parsed = parse_section_heading(first_line)

        if parsed:
            flush_buffer()
            level, title, inline_rest = parsed
            body_parts = []
            if inline_rest:
                body_parts.append(inline_rest)
            if "\n" in para:
                tail = "\n".join(para.split("\n")[1:]).strip()
                if tail:
                    body_parts.append(tail)
            chunks.append({
                "heading": (level, title),
                "text": "\n\n".join(body_parts),
            })
        else:
            buffer.append(para)

    flush_buffer()
    return chunks


def format_text_block(raw_text: str) -> str:
    """Format một khối text thô từ PDF block (fallback)."""
    lines = []
    for part in raw_text.split("\n"):
        part = part.strip()
        if part:
            lines.append({"x0": 0, "y0": 0, "y1": 0, "text": part})
    if not lines:
        return ""
    merged = merge_lines(lines)
    return lines_to_markdown(merged)
