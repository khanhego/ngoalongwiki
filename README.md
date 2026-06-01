# Wiki Ngoạ Long

Wiki tổng hợp nội dung game Ngoạ Long VNG.

## Cấu trúc

```
wiki/
├── index.html          # Trang chủ — chọn khu vực
├── viewer.html         # Xem nội dung (tree + search)
├── data/
│   ├── site.json       # Cấu hình 3 khu vực
│   ├── tree-*.json     # Cây navigation từng khu
│   └── search-index.json
├── content/
│   ├── ban-mem/              # Bản Word gốc
│   ├── cam-nang-thuc-quoc/   # PDF đánh số
│   └── cam-nang-nang-cao/    # Cẩm nang nâng cao
└── scripts/
    ├── extract.py        # PDF → markdown + ảnh
    ├── extract_docx.py   # DOCX → markdown + ảnh
    ├── build_index.py    # Tạo site + search index
    └── common.py
```

## 3 khu vực nội dung

| Khu vực | Nguồn | Mô tả |
|---------|-------|-------|
| **Nội dung chung** | `Bản Mềm/*.docx` | Bản Word gốc theo giai đoạn |
| **Cẩm Nang Thục Quốc** | `*.pdf` (0–12, buff) | PDF tổng hợp theo chủ đề |
| **Cẩm Nang Nâng Cao** | `CẨM NANG NÂNG CAO/*.docx` | Kiến thức nâng cao |

## Chạy wiki

```bash
cd wiki
python3 -m http.server 8080
# Mở http://localhost:8080
```

## Trích xuất lại nội dung

```bash
cd wiki/scripts
python3 extract.py              # Tất cả PDF
python3 extract_docx.py         # Tất cả DOCX
python3 build_index.py          # Rebuild index
```
