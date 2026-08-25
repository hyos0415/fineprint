# -*- coding: utf-8 -*-
"""파일럿 표본 30문항을 결정론적으로 만든다 (`docs/spec/prereg-02-pilot.md` §2·§3).

난수를 쓰지 않는다. 같은 스냅샷이면 누가 돌려도 같은 30문항이 나온다.
  1) 12개월 만기 상품을 세 층으로 나눈다 — 닫힘 / 안닫힘 / 조건없음
     ("공시된 최고금리가 명시된 우대조건 합계로 설명되는가")
  2) 층별로 상품명 오름차순 정렬 후 len//n 간격으로 균등 추출
  3) 사용자 상태 3패턴(많음/일부/없음)을 층 안에서 순환 배정

출력: data/pilot/sample_<stamp>.json (git에 커밋하지 않는다) + 콘솔 요약표

사용법: python src/analysis/build_pilot_sample.py [YYYYMMDD]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "pilot"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finlife_rules import classify, declared_bonus  # noqa: E402  (사전등록 §2 규칙 A~D)

TERM = "12"                       # 만기 12개월 고정 (prereg §3)
QUOTA = {"닫힘": 15, "안닫힘": 10, "조건없음": 5}

# prereg §3 — 사용자 상태 7변수 3패턴 (수치 명시). 값 선정 근거는 prereg §3.1
PATTERNS = {
    "P-많음": {"급여_월입금액": 2_500_000, "급여_개월수": 12,
               "자동이체_월건수": 2, "자동이체_기간비율": 1.0,
               "카드_월결제액": 1_200_000, "첫거래": True, "비대면가입": True,
               "청약보유": True, "기존예치잔액": 1_000_000},
    "P-일부": {"급여_월입금액": 2_500_000, "급여_개월수": 12,
               "자동이체_월건수": 2, "자동이체_기간비율": 1.0,
               "카드_월결제액": 0, "첫거래": False, "비대면가입": True,
               "청약보유": False, "기존예치잔액": 1_000_000},
    "P-없음": {"급여_월입금액": 0, "급여_개월수": 0,
               "자동이체_월건수": 0, "자동이체_기간비율": 0.0,
               "카드_월결제액": 0, "첫거래": False, "비대면가입": False,
               "청약보유": False, "기존예치잔액": 0},
}
PATTERN_ORDER = ["P-많음", "P-일부", "P-없음"]


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def collect(stamp: str) -> dict[str, list[dict]]:
    strata: dict[str, list[dict]] = {k: [] for k in QUOTA}
    for kind, label in (("deposit", "예금"), ("saving", "적금")):
        path = RAW_DIR / f"{kind}_{stamp}.json"
        if not path.exists():
            raise SystemExit(f"스냅샷이 없다: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        base = {b["fin_prdt_cd"]: b for b in payload["baseList"]}
        for opt in payload["optionList"]:
            if opt["save_trm"] != TERM:
                continue
            product = base.get(opt["fin_prdt_cd"])
            r1, r2 = opt.get("intr_rate"), opt.get("intr_rate2")
            if not product or r1 is None or r2 is None:
                continue
            text = product.get("spcl_cnd") or ""
            gap = round(r2 - r1, 3)
            declared, cap = declared_bonus(text)
            strata[classify(text, gap)].append({
                "product_kind": label,
                "product_code": opt["fin_prdt_cd"],
                "product_name": " ".join(product["fin_prdt_nm"].split()),
                "bank": product.get("kor_co_nm", ""),
                "base_rate": r1,
                "max_rate": r2,
                "gap": gap,
                "declared_bonus": round(declared, 3),
                "cap": cap,
                "spcl_cnd": text,
            })
    return strata


def pick(rows: list[dict], n: int) -> list[dict]:
    """상품명 정렬 후 균등 간격 추출 — 난수 없음."""
    ordered = sorted(rows, key=lambda r: (r["product_name"], r["product_code"]))
    if len(ordered) <= n:
        return ordered
    step = len(ordered) // n
    return [ordered[i * step] for i in range(n)]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    stamp = sys.argv[1] if len(sys.argv) > 1 else "20260824"
    strata = collect(stamp)

    print(f"스냅샷 {stamp} · 만기 {TERM}개월")
    for name in QUOTA:
        print(f"   {name:6s} 전체 {len(strata[name]):2d}건 → 파일럿 {QUOTA[name]:2d}문항")

    items, qid = [], 0
    for name, quota in QUOTA.items():
        chosen = pick(strata[name], quota)
        if len(chosen) < quota:
            print(f"[warn] {name} 층이 {len(chosen)}건뿐이다 (목표 {quota}) — 부족분은 채우지 않는다")
        for i, row in enumerate(chosen):
            qid += 1
            pattern = PATTERN_ORDER[i % len(PATTERN_ORDER)]
            items.append({"qid": f"Q{qid:02d}", "stratum": name,
                          "state_pattern": pattern, "state": PATTERNS[pattern], **row})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"sample_{stamp}.json"
    out.write_text(json.dumps({"snapshot": stamp, "term_months": int(TERM),
                               "amount_krw": 10_000_000, "items": items},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'qid':4s} {'층':6s} {'상태':6s} {'상품':32s} {'은행':10s} {'기본':>6s} {'최고':>6s} {'조건합':>6s}")
    for it in items:
        print(f"{it['qid']:4s} {it['stratum']:6s} {it['state_pattern']:6s} "
              f"{it['product_name'][:32]:32s} {it['bank'][:10]:10s} "
              f"{it['base_rate']:6} {it['max_rate']:6} {it['declared_bonus']:6}")
    print(f"\n{len(items)}문항 → {out.relative_to(REPO_ROOT)} (git에 커밋하지 않는다)")


if __name__ == "__main__":
    main()
