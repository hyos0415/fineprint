# -*- coding: utf-8 -*-
"""사용자 상태로 상품별 실수령 금리를 계산한다 — `../../docs/spec/design.md` §2 계산기.

이 파일이 채우는 자리
    추출(R1)은 되는데 그걸로 **사용자별 금리를 계산하는 코드가 없었다.** 이슈 #2다.
    계산기 5단계 중 3번(사용자 상태로 충족 여부 판정)이 여기서 처음 구현된다.

    1. applies_to_term 이 false 인 항목 제거
    2. exclusive_group 은 합이 아니라 그룹 최댓값
    3. 사용자 상태로 충족 여부 판정          ← 이 파일
    4. 충족분 합계에 cap 적용
    5. 기본금리 + 위 값                     = 세전
    6. 세율 적용                            = 세후

**모르는 것을 추측하지 않는다.** 판정할 수 없는 조건이 있으면 하나의 숫자가 아니라
**범위**를 낸다 — 최소(확실히 충족되는 것만) ~ 최대(모르는 것을 다 충족으로 가정).
세금에서 두 시나리오를 보여주기로 한 것과 같은 방침이다.

## 공시 최고금리를 상한으로 건다 — 그리고 그게 무엇을 가리는지 적어둔다

계산값이 공시 최고금리를 넘으면 **공시 값으로 자른다.** 사용자가 공시보다 많이 받을
수는 없으므로 이 상한은 항상 참이다.

**왜 필요한가** — 우리 추출기가 공시보다 **많이** 뽑는 경우가 주된 실패다.
저축은행 12개월 297개 중 **넘침 181 · 모자람 7**이었다. 상한이 없으면 공시에 없는
금리를 사용자에게 보여준다(관측된 최악 +3.50%p).

**그런데 이 상한은 증상만 막는다.** 넘치는 181건은 상품 문제가 아니라 **우리가 잘못
읽은 것**이고, 상한은 그걸 사용자 화면에서만 가린다. 그래서 두 가지를 함께 한다.

```
사용자에게      상한을 적용한 값을 보여준다        과대 진술이 불가능해진다
측정에는        상한 전 원값을 남긴다 (raw_hi)     추출이 나아졌는지 계속 잴 수 있다
```

닫는 것만 남기고 문제를 버리면 닫힘률이 자동으로 100%가 되어 개선을 측정할 수 없다.
그래서 **상품을 제외하지 않고 층 라벨을 붙인다**(아래 `TIERS`).

사용법:
    python src/analysis/calculate.py 20260825 --group savingsbank --top 10
    python src/analysis/calculate.py 20260826 --state 급여_연금이체,카드실적 --term 12
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_llm import CONDITION_TYPES, load_pairs  # noqa: E402
from finlife_rules import TOLERANCE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PATH = REPO_ROOT / "config" / "tax-2026.json"
OUT_DIR = REPO_ROOT / "data" / "pilot"

# 사용자가 O/X 로 답할 수 없는 유형 — `decisions/0005` 의 층 2
ALWAYS_MET = {"무조건_특판_이벤트"}      # 가입고객 모두에게 적용된다
UNDECIDABLE = {"판정불가_불특정"}         # 랜덤 지급 등. 공시로 판정할 수 없다

# 층 라벨 — 제외하지 않고 라벨로 가른다. 메인 화면은 이 라벨로 자른다
TIERS = {
    "확정":       "조건 합계가 공시와 맞고, 사용자가 모든 조건에 답했다",
    "범위":       "합계는 맞지만 사용자가 답하지 않은 조건이 있다",
    "설명부족":    "공시 최고금리의 일부가 조건으로 설명되지 않는다 — 광고 금리 근거 없음",
    "추출불확실":  "우리가 공시보다 많이 뽑았다 — 조건별 배분을 신뢰할 수 없다",
    "계산불가":    "조건 항목을 하나도 뽑지 못했다",
}
MAIN_TIERS = ("확정", "범위")            # 메인 화면에 올리는 층


def load_tax() -> dict:
    """세율표를 읽는다. 코드에 박지 않는 이유는 세법이 매년 바뀌기 때문이다."""
    return json.loads(TAX_PATH.read_text(encoding="utf-8"))


def condition_met(item: dict, state: dict) -> bool | None:
    """이 조건을 사용자가 충족하는가. 모르면 None 을 낸다 — 추측하지 않는다."""
    kind = item.get("condition_type")
    if kind in ALWAYS_MET:
        return True
    if kind in UNDECIDABLE:
        return None
    value = state.get(kind)
    if value is None:
        return None
    return (not value) if item.get("polarity") == "must_not_have" else bool(value)


def bonus_range(items: list[dict], cap: float | None, state: dict) -> dict:
    """충족분 합계의 최소~최대. exclusive_group 은 합이 아니라 그룹 최댓값이다."""
    live = [it for it in items if it.get("applies_to_term")]
    met, unmet, unknown = [], [], []
    for it in live:
        verdict = condition_met(it, state)
        (met if verdict is True else unmet if verdict is False else unknown).append(it)

    def total(chosen: list[dict]) -> float:
        plain, groups = 0.0, {}
        for it in chosen:
            rate = float(it.get("rate") or 0)
            gid = it.get("exclusive_group")
            if gid:
                groups[gid] = max(groups.get(gid, 0.0), rate)
            else:
                plain += rate
        return round(plain + sum(groups.values()), 4)

    lo, hi = total(met), total(met + unknown)
    if cap is not None and live:
        lo, hi = min(lo, cap), min(hi, cap)
    return {"lo": lo, "hi": hi, "met": met, "unmet": unmet, "unknown": unknown}


def after_tax(rate: float, tax: dict, exempt: bool = False) -> tuple[float, float]:
    """세후 금리와 적용 세율. 1층(원천징수)·2층(비과세) 까지만 다룬다."""
    r = 0.0 if exempt else tax["일반과세"]["합계"]
    return round(rate * (1 - r), 4), r


def evaluate(row: dict, extracted: dict, state: dict, tax: dict) -> dict:
    """상품 한 행을 사용자 상태로 채점한다."""
    items = extracted.get("items", []) if extracted else []
    cap = extracted.get("cap") if extracted else None
    rng = bonus_range(items, cap, state)
    base = row["base"]
    gross_lo, gross_hi = round(base + rng["lo"], 4), round(base + rng["hi"], 4)
    exempt = bool(state.get("_비과세종합저축_대상"))

    # 공시 최고금리를 조건으로 설명할 수 있는가 (닫힘률과 같은 판정)
    declared_all = min(sum(float(i.get("rate") or 0)
                          for i in items if i.get("applies_to_term")), cap) \
        if (cap is not None and items) else sum(float(i.get("rate") or 0)
                                                for i in items if i.get("applies_to_term"))
    unexplained = round(row["gap"] - declared_all, 3)

    # 공시 최고금리 상한. 사용자가 공시보다 많이 받을 수는 없다
    raw_lo, raw_hi = gross_lo, gross_hi
    gross_lo = min(gross_lo, row["max"])
    gross_hi = min(gross_hi, row["max"])
    net_lo, rate_used = after_tax(gross_lo, tax, exempt)
    net_hi, _ = after_tax(gross_hi, tax, exempt)

    if not items:
        tier = "계산불가" if abs(row["gap"]) > TOLERANCE else "확정"
    elif unexplained < -TOLERANCE:
        tier = "추출불확실"
    elif unexplained > TOLERANCE:
        tier = "설명부족"
    else:
        tier = "범위" if rng["unknown"] else "확정"

    return {
        "tier": tier,
        "raw_hi": raw_hi, "clamped": raw_hi > row["max"] + 0.001,
        "name": row["name"], "kind": row["kind"], "code": row["code"], "term": row["term"],
        "base": base, "disclosed_max": row["max"],
        "gross_lo": gross_lo, "gross_hi": gross_hi,
        "net_lo": net_lo, "net_hi": net_hi, "tax_rate": rate_used,
        "n_met": len(rng["met"]), "n_unmet": len(rng["unmet"]), "n_unknown": len(rng["unknown"]),
        "met": [i["condition_type"] for i in rng["met"]],
        "unmet": [i["condition_type"] for i in rng["unmet"]],
        "unknown": [i["condition_type"] for i in rng["unknown"]],
        "cap": cap,
        "explainable": abs(unexplained) <= TOLERANCE,
        "unexplained_pp": unexplained,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, top, state_arg = "bank", 12, 10, ""
    for flag in ("--group", "--term", "--top", "--state"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            v = argv[i + 1]
            group = v if flag == "--group" else group
            term = int(v) if flag == "--term" else term
            top = int(v) if flag == "--top" else top
            state_arg = v if flag == "--state" else state_arg
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/calculate.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--state 유형,유형] [--top 10]")
    stamp = argv[0]
    suffix = "" if group == "bank" else f"_{group}"

    # 사용자 상태: --state 에 적은 유형만 true, 나머지는 모름(None)
    picked = [s.strip() for s in state_arg.split(",") if s.strip()]
    unknown_names = [p for p in picked if p not in CONDITION_TYPES]
    if unknown_names:
        raise SystemExit(f"모르는 조건 유형: {unknown_names}\n가능한 값: {CONDITION_TYPES}")
    state = {t: True for t in picked}
    tax = load_tax()

    rows, pairs = load_pairs(stamp, group)
    llm_path = OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    if not llm_path.exists():
        raise SystemExit(f"추출 결과가 없다: {llm_path.relative_to(REPO_ROOT)}\n"
                         f"먼저 extract_llm.py 를 돌린다")
    llm = json.loads(llm_path.read_text(encoding="utf-8"))
    by_pair = {p["pair_id"]: p for p in llm["pairs"]}

    scored = []
    for row in rows:
        if row["term"] != term:
            continue
        got = by_pair.get(row["pair_id"])
        parsed = got["parsed"] if (got and got["schema_ok"]) else None
        scored.append(evaluate(row, parsed, state, tax))

    print(f"사용자 상태  {picked or '(아무 것도 답하지 않음)'}")
    print(f"가입기간     {term}개월 · 스냅샷 {stamp} ({group})")
    print(f"세율         {tax['일반과세']['합계'] * 100:.1f}% · {tax['적용_시점']} "
          f"· 확인 상태 {tax['확인_상태']}")
    print(f"대상 상품    {len(scored)}\n")
    if not scored:
        raise SystemExit(f"{term}개월 상품이 없다. --term 을 바꿔본다")

    # 정렬은 세후 최소값 기준 — 확정된 값으로 줄을 세운다
    scored.sort(key=lambda x: (-x["net_lo"], -x["net_hi"]))
    main = [s for s in scored if s["tier"] in MAIN_TIERS]
    rest = [s for s in scored if s["tier"] not in MAIN_TIERS]

    def show(items: list[dict], label: str) -> None:
        if not items:
            return
        print(f"\n■ {label} ({len(items)})")
        print(f"{'순':>3} {'상품':<26}{'세후':>15}{'세전':>14}  {'층':<11}조건")
        print("-" * 102)
        for i, s in enumerate(items[:top], 1):
            span = (f"{s['net_lo']:.2f}" if s["net_lo"] == s["net_hi"]
                    else f"{s['net_lo']:.2f}~{s['net_hi']:.2f}")
            gspan = (f"{s['gross_lo']:.2f}" if s["gross_lo"] == s["gross_hi"]
                     else f"{s['gross_lo']:.2f}~{s['gross_hi']:.2f}")
            note = ""
            if s["tier"] == "설명부족":
                note = f" 근거없음 {s['unexplained_pp']:+.2f}%p"
            elif s["tier"] == "추출불확실":
                note = f" 과다 {s['unexplained_pp']:+.2f}%p"
            if s["clamped"]:
                note += f" [상한 {s['raw_hi']:.2f}->{s['gross_hi']:.2f}]"
            print(f"{i:>3} {s['name'][:25]:<26}{span:>14}%{gspan:>13}%  {s['tier']:<11}"
                  f"충족{s['n_met']} 미충족{s['n_unmet']} 모름{s['n_unknown']}{note}")

    show(main, "메인 - 계산할 수 있는 상품")
    show(rest, "아래 섹션 - 주의가 붙는 상품")

    tiers = Counter(s["tier"] for s in scored)
    n_clamped = sum(1 for s in scored if s["clamped"])
    print("\n" + "-" * 102)
    print("층 분포")
    for name, desc in TIERS.items():
        if tiers[name]:
            mark = "메인" if name in MAIN_TIERS else "  "
            print(f"  {mark} {name:<11}{tiers[name]:>4}  {desc}")
    print(f"\n공시 최고금리 상한에 걸린 상품 {n_clamped}/{len(scored)}"
          f"   <- 상한이 없으면 공시에 없는 금리를 보여준다")
    print("상한은 증상만 막는다. 넘치는 상품은 우리 추출 문제이고 raw_hi 로 남겨 측정에 쓴다")

    out = OUT_DIR / f"recommend{suffix}_{stamp}_{term}m.json"
    out.write_text(json.dumps({"snapshot": stamp, "group": group, "term": term,
                               "state": state, "tax": tax["적용_시점"],
                               "products": scored}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
