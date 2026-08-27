# -*- coding: utf-8 -*-
"""사람이 직접 읽어야 하는 표본을 뽑아 검토용 문서로 만든다.

이 파일이 채우는 자리
    추출 결과 1,051개 중 **사람 눈이 필요한 두 덩어리**가 있다
    (`../../docs/spec/prereg-06-matching-and-judgment.md` §1.1·§1.4).

    부정 조건 6건    금융위 소비자 경보가 지목한 유형인데 데이터에는 0.6%뿐이고
                    전부 같은 문구다. **AI 가 "없어야 한다"를 "해야 한다"로 잘못
                    읽고 있는지** 확인해야 한다. 방향이 뒤집히면 사용자에게
                    반대로 계산된 금리를 보여준다
    기타 40건        어느 상태 변수에도 대응하지 않는다. 되물을 질문을 만들 수 없거나,
                    17종 중 하나로 갔어야 하는데 AI 가 포기한 것이다

**자동으로 판정하지 않는다.** 뽑아서 원문 옆에 나란히 놓는 것까지가 이 스크립트의 일이고,
맞았는지 틀렸는지는 사람이 적는다. 판정을 코드가 하면 그건 또 하나의 추출기일 뿐이다.

사용법:
    python src/analysis/review_sample.py            # 두 권역 전부
    python src/analysis/review_sample.py --only 부정조건
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_llm import load_pairs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "pilot"

# 검토 대상 스냅샷 — 폴백 채택(`decisions/0012`) 시점의 추출 결과와 같은 파일이다
SOURCES = [("bank", "20260826", "은행권"), ("savingsbank", "20260825", "저축은행")]


def institutions(group: str, stamp: str) -> dict[str, str]:
    """상품코드 → 기관명. `load_pairs` 가 안 담는 값이라 원본에서 직접 읽는다."""
    suffix = "" if group == "bank" else f"_{group}"
    out = {}
    for kind in ("deposit", "saving"):
        path = REPO_ROOT / "data" / "raw" / f"{kind}{suffix}_{stamp}.json"
        if not path.exists():
            continue
        for b in json.loads(path.read_text(encoding="utf-8"))["baseList"]:
            out[b["fin_prdt_cd"]] = b.get("kor_co_nm") or ""
    return out


def collect(group: str, stamp: str) -> list[dict]:
    """항목 하나하나를 상품 이름·원문과 함께 편다."""
    suffix = "" if group == "bank" else f"_{group}"
    path = OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    if not path.exists():
        raise SystemExit(f"추출 결과가 없다: {path.relative_to(REPO_ROOT)}")
    rows, _ = load_pairs(stamp, group)
    banks = institutions(group, stamp)
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[r["pair_id"]].append(r)
    out = []
    for p in json.loads(path.read_text(encoding="utf-8"))["pairs"]:
        rs = by_pair.get(p["pair_id"], [])
        name = rs[0]["name"] if rs else "(상품명 없음)"
        for it in (p.get("parsed") or {}).get("items", []) or []:
            out.append({"상품": name, "기관": banks.get(rs[0]["code"], "") if rs else "",
                        "코드": rs[0]["code"] if rs else "", "기간": sorted({r["term"] for r in rs}),
                        "pair_id": p["pair_id"], "원문": p["text"], **it})
    return out


def block(items: list[dict], show_source: bool) -> list[str]:
    """항목 하나를 원문과 나란히 놓는다. 판정란은 비워 둔다."""
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"#### {i}. {it['기관']} · {it['상품']}".rstrip(" ·"))
        lines.append("")
        lines.append(f"- **AI 가 뽑은 것** — 유형 `{it.get('condition_type')}` · "
                     f"금리 `{it.get('rate')}` · 방향 `{it.get('polarity')}` · "
                     f"이 기간에 적용 `{it.get('applies_to_term')}`")
        lines.append(f"- **근거로 든 문구** — {it.get('evidence') or '(없음)'}")
        if show_source:
            src = (it["원문"] or "").strip().replace("\n", "\n  > ")
            lines.append("- **공시 원문 전체**")
            lines.append("")
            lines.append(f"  > {src}")
        lines.append("")
        lines.append("- 판정 ( 맞음 / 틀림 / 애매 ) — ")
        lines.append("- 틀렸다면 무엇이어야 하나 — ")
        lines.append("")
    return lines


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1] if i + 1 < len(argv) else None

    everything: list[dict] = []
    for group, stamp, label in SOURCES:
        got = collect(group, stamp)
        for g in got:
            g["권역"] = label
        everything += got

    neg = [x for x in everything if x.get("polarity") == "must_not_have"]
    etc = [x for x in everything if x.get("condition_type") == "기타"]

    md = ["# 사람이 직접 읽을 표본 — 부정 조건과 `기타`",
          "",
          "> 자동 생성: `python src/analysis/review_sample.py` · "
          "**판정은 사람이 적는다.**",
          "",
          f"추출 항목 {len(everything)}개 기준 — 부정 조건 **{len(neg)}건** · "
          f"`기타` **{len(etc)}건**.", ""]

    if only in (None, "부정조건"):
        md += ["## 1부 · 부정 조건 (`must_not_have`)", "",
               "**무엇을 확인하나** — AI 가 \"없어야 한다\"를 \"해야 한다\"로 뒤집어 "
               "읽고 있는지다. 방향이 뒤집히면 사용자에게 **반대로 계산된 금리**를 보여준다.",
               "",
               "금융위 소비자 경보가 지목한 유형인데(*\"가입 이전 6개월간 카드 사용실적이 "
               "있어 우대금리를 못 받았다\"*) 데이터에는 0.6%뿐이라, **정말 드문 것인지 "
               "AI 가 놓치고 있는 것인지**를 같이 본다.", ""]
        seen = Counter(x.get("evidence") for x in neg)
        md += [f"근거 문구 {len(seen)}종 — " +
               " · ".join(f"`{k[:40]}` {v}건" for k, v in seen.most_common()), ""]
        md += block(neg, show_source=True)

    if only in (None, "기타"):
        md += ["## 2부 · `기타` 로 분류된 항목", "",
               "**무엇을 확인하나** — 17종 중 하나로 갔어야 하는데 AI 가 포기한 것인지, "
               "아니면 정말 어디에도 안 맞는 것인지다. 전자면 되물을 질문을 만들 수 있고, "
               "후자면 그 조건은 영원히 판정 불가로 남는다.", ""]
        by_ev = defaultdict(list)
        for x in etc:
            by_ev[(x.get("evidence") or "").strip()].append(x)
        dup = {k: v for k, v in by_ev.items() if len(v) > 1}
        if dup:
            md += [f"**같은 문구가 여러 번 나온 것 {len(dup)}종** — 한 번 판정하면 "
                   "나머지도 같이 정해진다", ""]
            for k, v in sorted(dup.items(), key=lambda kv: -len(kv[1])):
                md.append(f"- {len(v)}건 · `{k[:70]}`")
            md.append("")
        md += block(etc, show_source=True)

    out = OUT_DIR / "review_sample.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"부정 조건 {len(neg)}건 · 기타 {len(etc)}건 → "
          f"{out.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
