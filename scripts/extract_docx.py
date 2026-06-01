#!/usr/bin/env python3
"""Trích xuất DOCX thành markdown + ảnh xen kẽ cho Bản Mềm và Cẩm Nang Nâng Cao."""

import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from common import is_docx_heading, normalize_line, slugify

SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent / "Cẩm Nang Thục Quốc"
WIKI_ROOT = Path(__file__).resolve().parent.parent

COLLECTIONS = {
    "ban-mem": {
        "source_dir": SOURCE_ROOT / "Bản Mềm",
        "content_dir": WIKI_ROOT / "content" / "ban-mem",
        "catalog": [
            {"order": 0, "file": "CẨM NANG THỤC QUỐC.docx", "slug": "cam-nang-tong", "title": "Cẩm Nang Thục Quốc (Tổng hợp)"},
            {"order": 1, "file": "Tài Nguyên.docx", "slug": "tai-nguyen", "title": "Tài Nguyên"},
            {"order": 2, "file": "Trang Bị.docx", "slug": "trang-bi", "title": "Trang Bị"},
            {"order": 3, "file": "Mã Trường.docx", "slug": "ma-truong", "title": "Mã Trường"},
            {"order": 4, "file": "Vợ Tri Kỉ.docx", "slug": "vo-tri-ki", "title": "Vợ Tri Kỉ"},
            {"order": 5, "file": "Thống Soái.docx", "slug": "thong-soai", "title": "Thống Soái"},
            {"order": 6, "file": "Vũ Khí Đặc Biệt.docx", "slug": "vu-khi-dac-biet", "title": "Vũ Khí Đặc Biệt"},
            {"order": 7, "file": "Ấn Kế Thừa.docx", "slug": "an-ke-thua", "title": "Ấn Kế Thừa"},
            {"order": 8, "file": "Quý Tử.docx", "slug": "quy-tu", "title": "Quý Tử"},
        ],
    },
    "cam-nang-nang-cao": {
        "source_dir": SOURCE_ROOT / "CẨM NANG NÂNG CAO",
        "content_dir": WIKI_ROOT / "content" / "cam-nang-nang-cao",
        "catalog": [
            {"order": 0, "file": "Chiến Báo.docx", "slug": "chien-bao", "title": "Chiến Báo"},
        ],
    },
}


def _flush_text(buffer: List[str], blocks: List[dict]) -> None:
    if not buffer:
        return
    text = "\n".join(buffer).strip()
    if text:
        blocks.append({"type": "text", "text": text})
    buffer.clear()


def extract_paragraph_images(
    paragraph: Paragraph,
    doc: Document,
    images_dir: Path,
    collection: str,
    doc_slug: str,
    img_counter: List[int],
) -> List[str]:
    paths = []
    for run in paragraph.runs:
        for blip in run._element.findall(".//" + qn("a:blip")):
            embed = blip.get(qn("r:embed"))
            if not embed:
                continue
            try:
                part = doc.part.related_parts[embed]
                img_counter[0] += 1
                ext = part.content_type.split("/")[-1]
                if ext == "jpg":
                    ext = "jpeg"
                filename = f"img-{img_counter[0]:04d}.{ext}"
                (images_dir / filename).write_bytes(part.blob)
                paths.append(f"content/{collection}/{doc_slug}/images/{filename}")
            except Exception:
                continue
    return paths


def extract_docx(docx_path: Path, collection: str, catalog_entry: dict, content_dir: Path) -> dict:
    doc = Document(str(docx_path))
    doc_slug = catalog_entry["slug"]
    out_dir = content_dir / doc_slug
    images_dir = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    sections: List[dict] = []
    current = {
        "level": "h1",
        "title": catalog_entry["title"],
        "slug": "index",
        "content_blocks": [],
    }
    text_buffer: List[str] = []
    img_counter = [0]

    def flush_section():
        nonlocal current
        _flush_text(text_buffer, current["content_blocks"])
        if current["content_blocks"]:
            sections.append(current)

    def start_section(level: str, title: str):
        nonlocal current
        flush_section()
        current = {
            "level": level,
            "title": title,
            "slug": slugify(title),
            "content_blocks": [],
        }

    for para in doc.paragraphs:
        text = normalize_line(para.text)
        img_paths = extract_paragraph_images(
            para, doc, images_dir, collection, doc_slug, img_counter
        )

        if text:
            heading = is_docx_heading(text)
            if heading:
                _flush_text(text_buffer, current["content_blocks"])
                level, title = heading
                if current["slug"] == "index" and not current["content_blocks"]:
                    current["level"] = level
                    current["title"] = title
                    current["slug"] = slugify(title)
                else:
                    flush_section()
                    start_section(level, title)
            else:
                text_buffer.append(text)

        if img_paths:
            _flush_text(text_buffer, current["content_blocks"])
            for p in img_paths:
                current["content_blocks"].append({"type": "image", "path": p})

    flush_section()

    if not sections:
        sections = [current]

    total_images = sum(
        1 for s in sections for b in s.get("content_blocks", []) if b["type"] == "image"
    )
    children = []
    for sec in sections:
        md = section_to_markdown(sec)
        (out_dir / f"{sec['slug']}.md").write_text(md, encoding="utf-8")
        children.append({
            "slug": sec["slug"],
            "title": sec["title"],
            "level": sec["level"],
            "file": f"{doc_slug}/{sec['slug']}.md",
            "imageCount": sum(1 for b in sec.get("content_blocks", []) if b["type"] == "image"),
        })

    meta = {
        "order": catalog_entry["order"],
        "slug": doc_slug,
        "title": catalog_entry["title"],
        "source": catalog_entry["file"],
        "totalImages": total_images,
        "children": children,
    }
    (out_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def section_to_markdown(section: dict) -> str:
    level = section["level"]
    prefix = {"h1": "#", "h2": "##", "h3": "###"}.get(level, "##")
    lines = [f"{prefix} {section['title']}", ""]
    for block in section.get("content_blocks", []):
        if block["type"] == "text":
            lines.append(block["text"])
            lines.append("")
        elif block["type"] == "image":
            lines.append(f'![]({block["path"]})')
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def extract_collection(collection_id: str):
    cfg = COLLECTIONS[collection_id]
    source_dir = cfg["source_dir"]
    content_dir = cfg["content_dir"]
    content_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for entry in cfg["catalog"]:
        path = source_dir / entry["file"]
        if not path.exists():
            print(f"  ⚠ Bỏ qua (không tìm thấy): {entry['file']}")
            continue
        print(f"[DOCX/{collection_id}] [{entry['order']}] {entry['title']}...")
        meta = extract_docx(path, collection_id, entry, content_dir)
        results.append(meta)
        print(f"  → {len(meta['children'])} sections, {meta['totalImages']} ảnh")

    manifest_path = content_dir / "manifest.json"
    manifest = sorted(results, key=lambda x: x["order"])
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Manifest → {manifest_path}\n")


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(COLLECTIONS.keys())
    for col in targets:
        if col not in COLLECTIONS:
            print(f"Collection không hợp lệ: {col}")
            continue
        extract_collection(col)


if __name__ == "__main__":
    main()
