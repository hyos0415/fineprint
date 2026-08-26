# -*- coding: utf-8 -*-
"""상품설명서 PDF에서 텍스트와 표를 뽑는다.

왜 pdfplumber 인가 — 이 저장소의 무의존 관행을 여기서만 깬다
    `fetch_finlife.py` 주석대로 이 저장소는 표준 라이브러리만 써 왔다. PDF는 예외로 둔다.

    직접 만든 파서(`pdf_text.py`, 삭제됨)로도 텍스트는 뽑혔지만 **표가 뭉개졌다.**
    그런데 상품설명서에서 우리가 원하는 것이 정확히 표다 — 기본이자율표·중도해지이자율표·
    우대조건표. 뭉개진 문자열에서 금리를 자동으로 뽑을 수 없다.

        직접 만든 파서   "기 간기본이자율만기지급식1개월이상 3개월미만1.403개월이상..."
        pdfplumber      ["1개월이상 3개월미만", "1.40"] · ["3개월이상 6개월미만", "1.70"]

    라이선스도 이유다. PyMuPDF 는 AGPL 이라 공개 저장소에 올리면 결합저작물 문제가
    생긴다. pdfplumber 는 MIT 다.

한계
    * 스캔 이미지 PDF는 못 뽑는다 (OCR 필요). 글자 수가 적으면 경고를 낸다
    * 셀 병합이 많은 표는 구조가 흐트러질 수 있다

사용법:
    python src/ingest/pdf_extract.py <파일.pdf>                전체
    python src/ingest/pdf_extract.py <파일.pdf> --tables       표만
    python src/ingest/pdf_extract.py <파일.pdf> --grep 우대     해당 줄만
    python src/ingest/pdf_extract.py <파일.pdf> --json out.json 구조화 저장
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:                                    # pragma: no cover
    raise SystemExit("pdfplumber 가 필요하다: pip install -r requirements.txt")


def clean(cell: object) -> str:
    """셀 안의 줄바꿈·중복 공백을 정리한다. 표 안에서는 줄바꿈이 의미를 갖지 않는다."""
    return re.sub(r"\s+", " ", str(cell or "")).strip()


def extract(path: Path) -> dict:
    """페이지마다 텍스트와 표를 뽑는다."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            tables = [[[clean(c) for c in row] for row in tbl]
                      for tbl in (page.extract_tables() or [])]
            pages.append({"page": i, "text": text, "tables": tables})
    chars = sum(len(p["text"]) for p in pages)
    return {
        "source": path.name,
        "n_pages": len(pages),
        "n_chars": chars,
        "n_tables": sum(len(p["tables"]) for p in pages),
        "scanned_suspect": chars < 200 * len(pages),   # 페이지당 200자 미만이면 의심
        "pages": pages,
    }


def find_rate_rows(doc: dict) -> list[dict]:
    """표에서 '기간 -> 금리' 로 보이는 행만 골라낸다.

    상품설명서의 기본이자율표를 자동으로 집어내기 위한 것이다. 완벽하지 않으니
    결과는 사람이 확인한다 — 이 저장소의 다른 추출기와 같은 방침이다.
    """
    TERM = re.compile(r"\d+\s*(개월|년)")
    RATE = re.compile(r"^\d+\.?\d*\s*%?$")
    out = []
    for p in doc["pages"]:
        for ti, tbl in enumerate(p["tables"]):
            for row in tbl:
                cells = [c for c in row if c]
                if len(cells) < 2:
                    continue
                if TERM.search(cells[0]) and any(RATE.match(c) for c in cells[1:]):
                    out.append({"page": p["page"], "table": ti,
                                "term": cells[0], "values": cells[1:]})
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    mode, pattern, out_path = "all", None, None
    for flag in ("--tables", "--grep", "--json", "--rates"):
        if flag in argv:
            i = argv.index(flag)
            if flag in ("--tables", "--rates"):
                mode = flag.lstrip("-")
                argv = argv[:i] + argv[i + 1:]
            else:
                value = argv[i + 1] if i + 1 < len(argv) else None
                if value is None:
                    raise SystemExit(f"{flag} 값이 없다")
                pattern, out_path = ((value, out_path) if flag == "--grep"
                                     else (pattern, value))
                argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/ingest/pdf_extract.py <파일.pdf> "
                         "[--tables|--rates] [--grep 패턴] [--json 출력경로]")

    doc = extract(Path(argv[0]))
    print(f"[pdf] {doc['source']} · 페이지 {doc['n_pages']} · "
          f"글자 {doc['n_chars']:,} · 표 {doc['n_tables']}")
    if doc["scanned_suspect"]:
        print("[warn] 글자가 적다 — 스캔 이미지 PDF 일 수 있다. OCR 이 필요하다")
    print()

    if out_path:
        Path(out_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"→ {out_path}")
        return

    if mode == "rates":
        rows = find_rate_rows(doc)
        print(f"기간별 금리로 보이는 행 {len(rows)}개")
        for r in rows:
            print(f"  p{r['page']}  {r['term']:<24} {' · '.join(r['values'])}")
        return

    for p in doc["pages"]:
        if pattern:
            for line in p["text"].splitlines():
                if re.search(pattern, line):
                    print(f"  p{p['page']}  {line.strip()}")
            for tbl in p["tables"]:
                for row in tbl:
                    joined = " | ".join(c for c in row if c)
                    if re.search(pattern, joined):
                        print(f"  p{p['page']}  [표] {joined[:150]}")
            continue
        print(f"───── p{p['page']} " + "─" * 52)
        if mode != "tables":
            print(p["text"].strip())
        for ti, tbl in enumerate(p["tables"]):
            print(f"\n  [표 {ti + 1}]")
            for row in tbl:
                print("    | " + " | ".join(c[:30] for c in row))
        print()


if __name__ == "__main__":
    main()
