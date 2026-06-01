#!/usr/bin/env python3
"""Trích xuất PDF thành markdown có cấu trúc cây + ảnh xen kẽ + bảng."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

from common import is_likely_heading, normalize_line, slugify
from pdf_format import (
    extract_tables,
    extract_text_lines,
    get_table_bboxes,
    group_lines_by_gap,
    lines_to_markdown,
    merge_lines,
    split_text_by_headings,
)

SOURCE_DIR = Path(__file__).resolve().parent.parent.parent / "Cẩm Nang Thục Quốc"
WIKI_ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "cam-nang-thuc-quoc"
CONTENT_DIR = WIKI_ROOT / "content" / COLLECTION

PDF_CATALOG = [
    {"order": 0, "file": "0. LỜI MỞ ĐẦU.pdf", "slug": "00-loi-mo-dau", "title": "Lời Mở Đầu"},
    {"order": 1, "file": "1. CẨM NANG TÂN THỦ.pdf", "slug": "01-cam-nang-tan-thu", "title": "Cẩm Nang Tân Thủ"},
    {"order": 2, "file": "2. Tài Nguyên.pdf", "slug": "02-tai-nguyen", "title": "Tài Nguyên"},
    {"order": 3, "file": "3. Trang Bị.pdf", "slug": "03-trang-bi", "title": "Trang Bị"},
    {"order": 4, "file": "4. Mã Trường.pdf", "slug": "04-ma-truong", "title": "Mã Trường"},
    {"order": 5, "file": "5. Vợ Tri Kỉ.pdf", "slug": "05-vo-tri-ki", "title": "Vợ Tri Kỉ"},
    {"order": 6, "file": "6. Thống Soái.pdf", "slug": "06-thong-soai", "title": "Thống Soái"},
    {"order": 7, "file": "7. Vũ Khí Đặc Biệt.pdf", "slug": "07-vu-khi-dac-biet", "title": "Vũ Khí Đặc Biệt"},
    {"order": 8, "file": "8. Ấn Kế Thừa.pdf", "slug": "08-an-ke-thua", "title": "Ấn Kế Thừa"},
    {"order": 9, "file": "9. Quý Tử 2.0.pdf", "slug": "09-quy-tu", "title": "Quý Tử 2.0"},
    {"order": 10, "file": "10. Sự Kiện.pdf", "slug": "10-su-kien", "title": "Sự Kiện"},
    {"order": 12, "file": "12. Tiêu Chuẩn Cấp 310.pdf", "slug": "12-tieu-chuan-cap-310", "title": "Tiêu Chuẩn Cấp 310"},
    {"order": 13, "file": "Hệ thống hiệu ứng (buff).pdf", "slug": "13-he-thong-buff", "title": "Hệ Thống Hiệu ứng (Buff)"},
]


def save_image(
    doc: fitz.Document,
    xref: int,
    images_dir: Path,
    slug: str,
    xref_to_file: Dict[int, str],
) -> Optional[str]:
    if xref in xref_to_file:
        return xref_to_file[xref]
    try:
        base = doc.extract_image(xref)
    except Exception:
        return None
    ext = base.get("ext", "png")
    if ext == "jpg":
        ext = "jpeg"
    filename = f"img-{xref:05d}.{ext}"
    (images_dir / filename).write_bytes(base["image"])
    wiki_path = f"content/{COLLECTION}/{slug}/images/{filename}"
    xref_to_file[xref] = wiki_path
    return wiki_path


def extract_page_elements(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    images_dir: Path,
    slug: str,
    xref_to_file: Dict[int, str],
) -> List[dict]:
    raw: List[dict] = []
    table_bboxes = get_table_bboxes(page)

    text_lines = extract_text_lines(page, table_bboxes)
    for group in group_lines_by_gap(text_lines):
        merged = merge_lines(group)
        md = lines_to_markdown(merged)
        if md.strip():
            raw.append({
                "type": "text",
                "y0": group[0]["y0"],
                "x0": group[0]["x0"],
                "text": md,
            })

    raw.extend(extract_tables(page))

    for img in page.get_images(full=True):
        xref = img[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        wiki_path = save_image(doc, xref, images_dir, slug, xref_to_file)
        if not wiki_path:
            continue
        for rect in rects:
            raw.append({
                "type": "image",
                "y0": rect.y0,
                "x0": rect.x0,
                "path": wiki_path,
                "page": page_num,
            })

    raw.sort(key=lambda e: (e["y0"], e["x0"]))
    return raw


def extract_pages(pdf_path: Path, slug: str, images_dir: Path) -> List[dict]:
    doc = fitz.open(str(pdf_path))
    images_dir.mkdir(parents=True, exist_ok=True)
    xref_to_file: Dict[int, str] = {}
    pages = []
    for i, page in enumerate(doc):
        elements = extract_page_elements(
            doc, page, i + 1, images_dir, slug, xref_to_file
        )
        pages.append({"page_num": i + 1, "elements": elements})
    doc.close()
    return pages


def _extract_leading_heading(text: str) -> Optional[tuple]:
    """Tách heading ở đầu block text. Trả (level, title, remainder) hoặc None."""
    chunks = split_text_by_headings(text)
    if not chunks or not chunks[0].get("heading"):
        return None
    first = chunks[0]
    level, title = first["heading"]
    return level, title, first.get("text", "")


def split_pages_into_sections(pages: List[dict], doc_title: str) -> List[dict]:
    sections: List[dict] = []
    current: Optional[dict] = None

    def flush_section():
        nonlocal current
        if current and current["content_blocks"]:
            sections.append(current)
        current = None

    def start_section(level: str, title: str):
        nonlocal current
        flush_section()
        current = {
            "level": level,
            "title": title,
            "slug": slugify(title),
            "content_blocks": [],
            "pages": [],
        }

    start_section("h1", doc_title)

    for page in pages:
        page_num = page["page_num"]
        for elem in page["elements"]:
            if elem["type"] == "image":
                current["content_blocks"].append({
                    "type": "image",
                    "path": elem["path"],
                    "page": elem["page"],
                })
            elif elem["type"] == "table":
                current["content_blocks"].append({
                    "type": "table",
                    "html": elem["html"],
                })
            elif elem["type"] == "text":
                for chunk in split_text_by_headings(elem["text"]):
                    if chunk.get("heading"):
                        level, title = chunk["heading"]
                        if not (
                            _heading_matches_title(title, current["title"])
                            and not current["content_blocks"]
                        ):
                            start_section(level, title)
                    body = chunk.get("text", "").strip()
                    if body:
                        current["content_blocks"].append({"type": "text", "text": body})

            if page_num not in current["pages"]:
                current["pages"].append(page_num)

    flush_section()
    return sections


def section_to_markdown(section: dict) -> str:
    level = section["level"]
    prefix = {"h1": "#", "h2": "##", "h3": "###"}.get(level, "##")
    lines = [f"{prefix} {section['title']}", ""]

    for block in section.get("content_blocks", []):
        btype = block["type"]
        if btype == "text":
            lines.append(block["text"])
            lines.append("")
        elif btype == "image":
            lines.append(f'![Trang {block["page"]}]({block["path"]})')
            lines.append("")
        elif btype == "table":
            lines.append(block["html"])
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def count_images(section: dict) -> int:
    return sum(1 for b in section.get("content_blocks", []) if b["type"] == "image")


def _heading_matches_title(heading_title: str, section_title: str) -> bool:
    a = normalize_line(heading_title).lower()
    b = normalize_line(section_title).lower()
    return a == b or a in b or b in a


def extract_document(catalog_entry: dict) -> dict:
    pdf_path = SOURCE_DIR / catalog_entry["file"]
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy: {pdf_path}")

    slug = catalog_entry["slug"]
    out_dir = CONTENT_DIR / slug
    images_dir = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Xóa markdown cũ tránh file orphan
    for old_md in out_dir.glob("*.md"):
        old_md.unlink()

    pages = extract_pages(pdf_path, slug, images_dir)
    sections = split_pages_into_sections(pages, catalog_entry["title"])
    total_images = sum(count_images(s) for s in sections)
    children = []

    for sec in sections:
        (out_dir / f"{sec['slug']}.md").write_text(
            section_to_markdown(sec), encoding="utf-8"
        )
        children.append({
            "slug": sec["slug"],
            "title": sec["title"],
            "level": sec["level"],
            "file": f"{slug}/{sec['slug']}.md",
            "pages": sec.get("pages", []),
            "imageCount": count_images(sec),
        })

    meta = {
        "order": catalog_entry["order"],
        "slug": slug,
        "title": catalog_entry["title"],
        "source": catalog_entry["file"],
        "totalImages": total_images,
        "children": children,
    }
    (out_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def main(orders: Optional[List[int]] = None):
    targets = PDF_CATALOG if orders is None else [
        e for e in PDF_CATALOG if e["order"] in orders
    ]
    results = []
    for entry in targets:
        print(f"[PDF] [{entry['order']}] {entry['title']}...")
        meta = extract_document(entry)
        results.append(meta)
        print(f"  → {len(meta['children'])} sections, {meta['totalImages']} ảnh")

    manifest_path = CONTENT_DIR / "manifest.json"
    existing = []
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_slug = {d["slug"]: d for d in existing}
    for r in results:
        by_slug[r["slug"]] = r
    manifest = sorted(by_slug.values(), key=lambda x: x["order"])
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nHoàn tất PDF → {manifest_path} ({len(manifest)} tài liệu)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main([int(x) for x in sys.argv[1:]])
    else:
        main()
