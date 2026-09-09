# -*- coding: utf-8 -*-
"""교차판매 조건의 모양 실측 (`prereg-32`) — 그래프(D5)가 필요한가를 **구조를 짓기 전에** 잰다.

무엇을 하나
    추출 결과(`data/pilot/extract_llm_*.json` · `pairs[].parsed.items`)에서 다른 상품을 가리키는 조건(카드실적 · 타상품_보유동시가입)을
    세고, 부류(카드·펀드·청약…) · AND 조합 · 두 홉 · 임계 · 역인덱스 크기를 낸다. 모델·GPU 를 쓰지 않는다 — 정규식과 집계뿐이다.
    부류 분류는 **어림(정규식)** 이고 판정에 쓰지 않는다. 사람이 읽을 분포다.

사용법
    python src/analysis/cross_sell_survey.py            (은행권 20260826 · 저축은행 20260825)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FILES = {"bank": REPO / "data/pilot/extract_llm_20260826.json",
         "savingsbank": REPO / "data/pilot/extract_llm_savingsbank_20260825.json"}
EXTERNAL = ("카드실적", "타상품_보유동시가입")

# 부류 어림 — 순서대로 먼저 맞는 것. 판정용이 아니다
KINDS = [
    ("특정 카드명", re.compile(r"(NH채움|zgm|롯데카드|삼성카드|현대카드|신한카드|KB국민카드|하나카드|우리카드|BC카드|비씨카드)")),
    ("카드(일반)", re.compile(r"카드")),
    ("펀드/수익증권", re.compile(r"펀드|수익증권|투자상품")),
    ("청약", re.compile(r"청약")),
    ("보험", re.compile(r"보험|방카")),
    ("대출", re.compile(r"대출|여신")),
    ("연금/ISA/신탁", re.compile(r"연금|ISA|신탁|퇴직")),
    ("다른 예적금", re.compile(r"예금|적금|입출금|통장|계좌")),
    ("외환/증권/기타 금융", re.compile(r"외화|환전|증권|주식|골드")),
]


def classify(ev: str) -> str:
    for name, rx in KINDS:
        if rx.search(ev):
            return name
    return "기타"


def survey(group: str) -> dict:
    d = json.loads(FILES[group].read_text(encoding="utf-8"))
    pairs = d["pairs"]
    rows = d["rows"]
    rows_by_pair = defaultdict(list)
    for r in rows:
        rows_by_pair[r["pair_id"]].append(r)
    names_in_data = {r["name"] for r in rows}

    items_all, ext = [], []
    and_pairs, and_pairs_nonexcl = 0, 0
    two_hop = 0
    for p in pairs:
        its = (p.get("parsed") or {}).get("items") or []
        items_all += its
        e = [it for it in its if it["condition_type"] in EXTERNAL]
        ext += [(p["pair_id"], it) for it in e]
        if len(e) >= 2:
            and_pairs += 1
            groups = [it.get("exclusive_group") for it in e]
            # 전부 같은 배타 그룹이면 "둘 중 하나" 지 동시 요구가 아니다
            if len(set(groups)) > 1 or any(g is None for g in groups):
                and_pairs_nonexcl += 1
        # 두 홉 — 가리킨 것이 우리 데이터 안의 다른 예적금 **이름**과 맞고 그 상품에 자기 조건이 있나
        for it in e:
            for nm in names_in_data:
                if len(nm) >= 4 and nm in it.get("evidence", ""):
                    tgt_pairs = {r["pair_id"] for r in rows if r["name"] == nm}
                    if any((pp.get("parsed") or {}).get("items") for pp in pairs if pp["pair_id"] in tgt_pairs):
                        two_hop += 1
                    break

    by_type = Counter(it["condition_type"] for _, it in ext)
    kinds = Counter(classify(it.get("evidence", "")) for _, it in ext)
    card = [it for _, it in ext if it["condition_type"] == "카드실적"]
    thr = sum(1 for it in card if re.search(r"\d+\s*만\s*원|\d+\s*원\s*이상|\d+\s*회|\d+\s*건", it.get("evidence", "")))
    # 역인덱스 — 조건 유형 → 오르는 상품(행) 수 · %p 분포
    inv = {}
    for t in EXTERNAL:
        prods, pps = set(), []
        for pid, it in ext:
            if it["condition_type"] != t:
                continue
            for r in rows_by_pair[pid]:
                prods.add((r["code"], r["name"]))
            if isinstance(it.get("rate"), (int, float)) and 0 < it["rate"] < 5:
                pps.append(it["rate"])
        pps.sort()
        inv[t] = {"상품": len(prods), "행_문구": sum(1 for pid, it in ext if it["condition_type"] == t),
                  "%p 중앙값": pps[len(pps) // 2] if pps else None, "%p 최소": pps[0] if pps else None, "%p 최대": pps[-1] if pps else None}
    return {"권역": group, "조건 항목": len(items_all), "문구": len(pairs), "행": len(rows),
            "A 외부 참조": {"항목": len(ext), "비율": round(len(ext) / len(items_all), 3), "유형별": dict(by_type)},
            "B 부류": dict(kinds.most_common()),
            "C AND 조합": {"외부 참조 2개 이상 문구": and_pairs, "그중 동시 요구(배타 아님)": and_pairs_nonexcl},
            "D 두 홉": two_hop,
            "E 카드 임계": {"카드실적": len(card), "임계 있음": thr, "비율": round(thr / len(card), 2) if card else None},
            "F 역인덱스": inv}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = {g: survey(g) for g in FILES}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    dst = REPO / "data/pilot/cross_sell_survey.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {dst.relative_to(REPO)} (git 제외)")


if __name__ == "__main__":
    main()
