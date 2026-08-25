# -*- coding: utf-8 -*-
"""추출 품질을 gold 라벨 없이 채점한다 — 공시가 스스로 주는 신호를 쓴다.

핵심 아이디어
    항목 합계(상한 적용) == 최고금리 − 기본금리   →  추출이 맞을 가능성이 높다
    불일치                                      →  추출 실패 또는 진짜 "설명 불가" 상품

한 행만 보면 둘을 구분할 수 없다. 그래서 **절대 정확도가 아니라 추출기 버전 간 비교
지표**로 쓴다. 진짜 설명 불가 상품의 비율은 고정이므로, 닫힘률이 오르면 추출이 나아진 것이다.

**게임 방지 (중요)**: 추출기에는 `spcl_cnd` 텍스트만 준다. 기본금리·최고금리는 채점기만
갖는다. 추출기가 목표값을 보면 거기에 맞춰 값을 만들어낼 수 있다 — 특히 LLM 추출기.

사용법:
    python src/analysis/score_extraction.py [YYYYMMDD] [--label rules-v1]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finlife_rules import (TOLERANCE, is_no_condition_literal,  # noqa: E402
                           parse_bonus_items)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "pilot"


def load_rows(stamp: str) -> list[dict]:
    """옵션 단위 행. 추출 입력(text)과 채점 정보(base/max)를 분리해 담는다."""
    rows = []
    for kind, label in (("deposit", "예금"), ("saving", "적금")):
        payload = json.loads((RAW_DIR / f"{kind}_{stamp}.json").read_text(encoding="utf-8"))
        base = {b["fin_prdt_cd"]: b for b in payload["baseList"]}
        for opt in payload["optionList"]:
            product = base.get(opt["fin_prdt_cd"])
            r1, r2 = opt.get("intr_rate"), opt.get("intr_rate2")
            if not product or r1 is None or r2 is None:
                continue
            rows.append({"kind": label, "code": opt["fin_prdt_cd"],
                         "name": " ".join(product["fin_prdt_nm"].split()),
                         "term": opt["save_trm"],
                         "text": product.get("spcl_cnd") or "",      # 추출기가 보는 것
                         "base": r1, "max": r2, "gap": round(r2 - r1, 3)})   # 채점기만
    return rows


def extract_rules(text: str, term: int) -> dict:
    """규칙 파서 추출기. 입력은 조건문 텍스트와 가입기간뿐이다 (금리를 보지 않는다)."""
    items, cap = parse_bonus_items(text, term)
    total = sum(items)
    return {"items": items, "cap": cap,
            "declared": min(total, cap) if (items and cap is not None) else total}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    label = "rules"
    if "--label" in argv:
        i = argv.index("--label")
        label = argv[i + 1] if i + 1 < len(argv) else label
        argv = argv[:i] + argv[i + 2:]
    stamp = argv[0] if argv else "20260824"

    rows = load_rows(stamp)
    scored, buckets = [], Counter()
    for row in rows:
        if is_no_condition_literal(row["text"]):
            buckets["조건없음"] += 1
            continue
        got = extract_rules(row["text"], int(row["term"]) if str(row["term"]).isdigit() else 12)
        if not got["items"]:
            buckets["항목 0개"] += 1
            diff = None
        else:
            diff = round(abs(got["declared"] - row["gap"]), 3)
            buckets["닫힘" if diff <= TOLERANCE else "불일치"] += 1
        scored.append({**{k: row[k] for k in ("kind", "name", "term", "base", "max", "gap")},
                       "declared": got["declared"], "cap": got["cap"],
                       "n_items": len(got["items"]), "diff": diff})

    with_cond = [s for s in scored]
    closed = [s for s in with_cond if s["diff"] is not None and s["diff"] <= TOLERANCE]
    print(f"추출 채점 [{label}] · 스냅샷 {stamp}")
    print(f"  옵션 행 {len(rows)} · 조건 있는 행 {len(with_cond)} · 조건없음 {buckets['조건없음']}")
    print()
    print(f"  ■ 닫힘률  {len(closed)}/{len(with_cond)} = {len(closed)/max(len(with_cond),1)*100:.1f}%"
          f"   ← 추출기 버전 간 비교 지표 (높을수록 좋다)")
    print(f"     불일치   {buckets['불일치']}")
    print(f"     항목 0개 {buckets['항목 0개']}   ← 추출이 아무것도 못 뽑은 행")
    print()
    print("  불일치 폭 분포 (|합계 − 실제폭|)")
    for lo, hi in ((0.0, 0.06), (0.06, 0.3), (0.3, 1.0), (1.0, 3.0), (3.0, 99.0)):
        n = sum(1 for s in with_cond if s["diff"] is not None and lo < s["diff"] <= hi)
        if n:
            print(f"     {lo:>4.2f} < d <= {hi:<5.2f}  {n:3d}")
    print()
    print("  상한(cap) 인식 여부별 닫힘률")
    for has_cap in (True, False):
        sub = [s for s in with_cond if (s["cap"] is not None) == has_cap and s["diff"] is not None]
        ok = [s for s in sub if s["diff"] <= TOLERANCE]
        if sub:
            print(f"     cap {'있음' if has_cap else '없음'}  {len(ok):3d}/{len(sub):3d} "
                  f"= {len(ok)/len(sub)*100:5.1f}%")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"extraction_{label}_{stamp}.json"
    out.write_text(json.dumps({"label": label, "snapshot": stamp,
                               "closure_rate": len(closed) / max(len(with_cond), 1),
                               "n_with_condition": len(with_cond), "n_closed": len(closed),
                               "buckets": dict(buckets), "rows": scored},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out.relative_to(REPO_ROOT)} (git 제외)")
    print("  다른 추출기와 비교할 때는 --label 을 바꿔 저장하고 닫힘률을 나란히 본다")


if __name__ == "__main__":
    main()
