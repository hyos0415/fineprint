# -*- coding: utf-8 -*-
"""사전등록 01(`docs/spec/prereg-01-savings-scope.md`) P1~P7을 측정한다.

세는 규칙은 사전등록 §6에 고정된 것을 그대로 쓴다.
  · 참조 판정: `cross-product-conditions.md` §1.1과 같은 키워드 집합
    ('예금'·'저축'은 자기참조 오탐이 많아 제외)
  · 사슬 인정: 지목된 이름이 보유 레코드(예금 38 + 적금 59)에서 조회되어야 한 홉
  · 카드는 잎사귀로 분류해 이름 지목에서 제외 (API 엔드포인트가 없다)

입력은 `data/raw/{deposit,saving}_YYYYMMDD.json` (git에 커밋하지 않는다).
출력은 숫자만 표준출력으로 낸다 — 원본 문구는 찍지 않는다.

사용법: python src/analysis/count_cross_references.py [YYYYMMDD]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"

# 사전등록 §6 — §1.1과 동일한 키워드 집합
REF_KEYWORDS = ["적금", "카드", "통장", "청약", "오픈뱅킹", "타행", "다른 은행", "타은행",
                "펀드", "수익증권", "연금", "대출", "보험", "신탁", "외화", "ISA"]
NO_CONDITION = {"", "없음", "해당없음", "해당사항없음", "해당 없음", "-", "."}
QUANT_PATTERNS = [r"\d+\s*회", r"\d+\s*개월\s*이상", r"매월", r"자동이체", r"\d+\s*년\s*이상", r"\d+\s*회차"]
BULLET = re.compile(r"(^|\n)\s*(?:[①-⑳]|\d{1,2}\s*[.)]|[-*·]|[가-하]\s*[.)])")
NAME_TOKEN = re.compile(r"[가-힣A-Za-z0-9()\[\]!.+_]{2,24}?(?:적금|예금|통장|저축)")
GENERIC_NAMES = {"정기예금", "자유적금", "정기적금", "자유적립식적금", "적립식예금", "예적금",
                 "원화정기예금", "거치식예금", "입출금통장", "종이통장", "당행입출금통장",
                 "수시입출금통장", "저축예금", "이내예적금", "자유저축예금", "기업자유예금"}


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def load(kind: str, stamp: str) -> list[dict]:
    path = RAW_DIR / f"{kind}_{stamp}.json"
    if not path.exists():
        raise SystemExit(f"스냅샷이 없다: {path} — 먼저 src/ingest/fetch_finlife.py를 돌린다")
    payload = json.loads(path.read_text(encoding="utf-8"))
    label = "예금" if kind == "deposit" else "적금"
    return [{"nm": x["fin_prdt_nm"], "co": x.get("kor_co_nm", ""), "cd": x["fin_prdt_cd"],
             "txt": x.get("spcl_cnd") or "", "kind": label} for x in payload["baseList"]]


def has_condition(text: str) -> bool:
    return squash(text) not in {squash(x) for x in NO_CONDITION}


def named_targets(row: dict) -> set[str]:
    found = {squash(x) for x in NAME_TOKEN.findall(row["txt"])}
    found -= GENERIC_NAMES
    return {x for x in found
            if len(x) >= 5 and x != squash(row["nm"])
            and not re.fullmatch(r"(?:이|본|당행|해당|위|아래)?(?:적금|예금|통장|저축)", x)}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔 기본 코드페이지 회피
        sys.stdout.reconfigure(encoding="utf-8")
    stamp = sys.argv[1] if len(sys.argv) > 1 else "20260824"
    deposits, savings = load("deposit", stamp), load("saving", stamp)
    universe = deposits + savings
    by_name = {squash(r["nm"]): r for r in universe}

    print(f"스냅샷 {stamp} — 예금 {len(deposits)}건 · 적금 {len(savings)}건 (보유 레코드 {len(universe)})")
    print()
    for label, rows in (("적금", savings), ("예금", deposits)):
        cond = [r for r in rows if has_condition(r["txt"])]
        ref = [r for r in cond if any(k in r["txt"] for k in REF_KEYWORDS)]
        quant = [r for r in cond if any(re.search(p, r["txt"]) for p in QUANT_PATTERNS)]
        multi = [r for r in cond if len(BULLET.findall(r["txt"])) >= 2]
        named = [r for r in cond if named_targets(r)]
        print(f"[{label}] 전체 {len(rows)}")
        print(f"   우대조건 있음      {len(cond):3d}  ({len(cond)/len(rows)*100:5.1f}%)")
        print(f"   외부 참조          {len(ref):3d}  ({len(ref)/len(cond)*100:5.1f}% of 조건보유)")
        print(f"   상품 이름 지목      {len(named):3d}  ({len(named)/len(cond)*100:5.1f}%)")
        print(f"   횟수·기간 조건      {len(quant):3d}  ({len(quant)/len(cond)*100:5.1f}%)")
        print(f"   조건 항목 2개 이상  {len(multi):3d}  ({len(multi)/len(cond)*100:5.1f}%)")
        print()

    print("사슬 — 전수 교차 매칭 (조건문에 다른 상품의 이름이 등장하고, 그 상품이 보유 레코드에 있는 경우)")
    chains = []
    for src in universe:
        squashed = squash(src["txt"])
        if not squashed:
            continue
        for name, tgt in by_name.items():
            if len(name) >= 5 and name in squashed and squash(src["nm"]) != name:
                chains.append((src, tgt))
    for src, tgt in chains:
        print(f"   [{src['kind']}] {src['nm'][:28]:28s} → [{tgt['kind']}] {tgt['nm'][:28]:28s} ({src['co'][:8]})")
    print(f"\n   한 홉으로 인정되는 사슬: {len(chains)}건")
    print("   사전등록 §5 임계: 6건 미만이면 2단계(사슬 순회) 폐기")


if __name__ == "__main__":
    main()
