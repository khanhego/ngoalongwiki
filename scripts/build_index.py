#!/usr/bin/env python3
"""Xây dựng site config, tree navigation và search index cho tất cả collections."""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

WIKI_ROOT = Path(__file__).resolve().parent.parent
CONTENT_ROOT = WIKI_ROOT / "content"
DATA_DIR = WIKI_ROOT / "data"

WIKI_VERSION = "1.0.0"

SITE_COLLECTIONS = [
    {
        "id": "ban-mem",
        "title": "Nội dung chung",
        "description": "Bản Word gốc — tổng hợp đầy đủ theo giai đoạn chơi",
        "icon": "📄",
        "contentPath": "content/ban-mem",
    },
    {
        "id": "cam-nang-thuc-quoc",
        "title": "Cẩm Nang Thục Quốc",
        "description": "Tổng hợp từ các file PDF — hướng dẫn chi tiết từng chủ đề",
        "icon": "📕",
        "contentPath": "content/cam-nang-thuc-quoc",
    },
    {
        "id": "cam-nang-nang-cao",
        "title": "Cẩm Nang Nâng Cao",
        "description": "Kiến thức nâng cao cho thành chủ kinh nghiệm",
        "icon": "📗",
        "contentPath": "content/cam-nang-nang-cao",
    },
]


def remove_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def tokenize(text: str) -> list:
    text = remove_accents(text.lower())
    tokens = re.findall(r"[a-z0-9]+", text)
    words = text.split()
    return list(set(tokens + words))


def extract_keywords(text: str, max_kw: int = 30) -> list:
    stops = {
        "va", "cua", "cho", "la", "mot", "cac", "co", "duoc", "trong",
        "neu", "thi", "nay", "hay", "voi", "den", "tu", "se", "khi",
        "theo", "nhu", "rat", "nhung", "cung", "ban", "nguoi", "choi",
    }
    tokens = tokenize(text)
    freq = {}
    for t in tokens:
        if len(t) >= 2 and t not in stops:
            freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in ranked[:max_kw]]


def parse_markdown(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    title_match = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem
    body = re.sub(r"^#+\s+.+$", "", text, flags=re.MULTILINE).strip()
    return {"title": title, "body": body}


def build_tree(collection_id: str, collection_title: str, manifest: list) -> dict:
    tree = {
        "id": collection_id,
        "title": collection_title,
        "type": "root",
        "children": [],
    }
    for doc in manifest:
        node = {
            "id": doc["slug"],
            "order": doc["order"],
            "title": doc["title"],
            "type": "document",
            "source": doc.get("source", ""),
            "children": [],
        }
        for child in doc.get("children", []):
            node["children"].append({
                "id": f"{doc['slug']}/{child['slug']}",
                "title": child["title"],
                "type": "section",
                "level": child.get("level", "h2"),
                "file": child["file"],
            })
        tree["children"].append(node)
    return tree


def build_search_index(collection_id: str, collection_title: str, content_path: str, manifest: list) -> list:
    index = []
    base = WIKI_ROOT / content_path

    for doc in manifest:
        doc_slug = doc["slug"]
        for child in doc.get("children", []):
            md_path = base / doc_slug / f"{child['slug']}.md"
            if not md_path.exists():
                continue
            parsed = parse_markdown(md_path)
            searchable = f"{collection_title} {doc['title']} {parsed['title']} {parsed['body']}"
            excerpt = parsed["body"][:300].replace("\n", " ").strip()
            if len(parsed["body"]) > 300:
                excerpt += "..."
            index.append({
                "id": f"{collection_id}/{doc_slug}/{child['slug']}",
                "collection": collection_id,
                "collectionTitle": collection_title,
                "docOrder": doc["order"],
                "docTitle": doc["title"],
                "docSlug": doc_slug,
                "sectionTitle": parsed["title"],
                "sectionSlug": child["slug"],
                "file": f"{content_path}/{doc_slug}/{child['slug']}.md",
                "keywords": extract_keywords(searchable),
                "tokens": tokenize(searchable),
                "excerpt": excerpt,
            })
    return index


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    last_edited = now.strftime("%Y-%m-%d")
    last_edited_display = now.strftime("%d/%m/%Y")

    site = {
        "title": "Wiki Ngoạ Long",
        "tagline": "Cẩm nang cộng đồng",
        "version": WIKI_VERSION,
        "lastEdited": last_edited,
        "lastEditedDisplay": last_edited_display,
        "footer": f"Ngoạ Long VNG · Cẩm nang cộng đồng · Cập nhật {last_edited_display} · v{WIKI_VERSION}",
        "collections": [],
    }
    all_search = []

    for col in SITE_COLLECTIONS:
        col_id = col["id"]
        manifest_path = WIKI_ROOT / col["contentPath"] / "manifest.json"
        if not manifest_path.exists():
            print(f"⚠ Chưa có manifest: {col_id}")
            col["docCount"] = 0
            col["sectionCount"] = 0
            site["collections"].append(col)
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tree = build_tree(col_id, col["title"], manifest)
        tree_path = DATA_DIR / f"tree-{col_id}.json"
        tree_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")

        col_index = build_search_index(col_id, col["title"], col["contentPath"], manifest)
        all_search.extend(col_index)

        section_count = sum(len(d.get("children", [])) for d in manifest)
        col["docCount"] = len(manifest)
        col["sectionCount"] = section_count
        site["collections"].append(col)
        print(f"✓ {col['title']}: {len(manifest)} tài liệu, {section_count} mục, {len(col_index)} index")

    site_path = DATA_DIR / "site.json"
    site_path.write_text(json.dumps(site, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = DATA_DIR / "search-index.json"
    index_path.write_text(json.dumps(all_search, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSite: {site_path}")
    print(f"Search index: {index_path} ({len(all_search)} entries total)")


if __name__ == "__main__":
    main()
