# -*- coding: utf-8 -*-
"""유형 배정 재추출을 사전등록 기준으로 채점한다 — `../../docs/spec/prereg-07-type-assignment.md`.

**기준은 이 파일이 아니라 `prereg-07` 이 정한다.** 여기는 그걸 계산할 뿐이다.

주 지표      은행권 A군 11건이 사람이 읽은 유형과 일치하는가   임계 >= 9/11
부 지표      저축은행 A군 9건 (홀드아웃)                    임계 >= 3/9
회귀 가드    커버리지 게이트 · 닫힘률 -2%p · `기타` 비율 · 항목 0개 비율

**확정률은 판정에 쓰지 않는다**(`prereg-07` §4). 유형이 바뀌면 질문 순위가 바뀌고
예산 12개 경계에서 밀리는 것만으로 값이 흔들린다. 같이 보고는 한다.

사용법:
    python src/analysis/score_type_assignment.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate as C  # noqa: E402
from extract_llm import CONDITION_TYPES, load_pairs  # noqa: E402
from ask_budget import COVERAGE_FLOOR  # noqa: E402
from finlife_rules import TOLERANCE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# 사람이 표본을 읽고 정한 정답 (`prereg-06` §1.8). **재추출 전에 확정된 값이다.**
#   은행권 = 주 지표 (프롬프트를 이 11건 보고 고쳤다)
#   저축은행 = 홀드아웃 (읽지 않은 셈 치고 일반화를 잰다)
GOLD_BANK = {
    "아파트관리비 이체": "자동이체",
    "개인사업자 계좌 실적 :1.0%p": "급여_연금이체",
    "전자명함을 통한 신규 시 0.2%": "쿠폰_코드_추천인",
    "고향사랑기부금 납부고객 우대 : 0.5%p": "실천_미션_인증",
    "고향사랑기부금 납부고객 우대 : 0.3%p": "실천_미션_인증",
}
GOLD_HOLDOUT = {
    "올해의 띠": "고객군_자격",
    "착한운전마일리지 신청자, 저공해차량 운전자, 전기차운전자, 수소차운전자, 장애인차량운전자":
        "고객군_자격",
    "출산예정인자-배우자 포함": "고객군_자격",
    "당해연도 출생한 부모": "고객군_자격",
    "미성년자 자녀가 있는 한부모 가정의 부모": "고객군_자격",
    "적금 가입 시점 예금주 신용평점에 따라 우대 : 최대 연 3.0%p, "
    "신용평점 350점 이하 ~ 1점 이상(연 3.0%p)": "고객군_자격",
    "가입기간12개월이상 계약금액 10억이상 0.10%p": "잔액_평잔_가입금액",
}

SOURCES = [("bank", "20260826", "은행권", GOLD_BANK, COVERAGE_FLOOR[("bank", 12)]),
           ("savingsbank", "20260825", "저축은행", GOLD_HOLDOUT,
            COVERAGE_FLOOR[("savingsbank", 12)])]


def load(group: str, stamp: str, label: str) -> dict:
    suffix = "" if group == "bank" else f"_{group}"
    tag = f"_{label}" if label else ""
    path = C.OUT_DIR / f"extract_llm{tag}{suffix}_{stamp}.json"
    if not path.exists():
        raise SystemExit(f"없다: {path.relative_to(REPO_ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def items_of(llm: dict) -> list[dict]:
    return [it for p in llm["pairs"]
            for it in (p.get("parsed") or {}).get("items", []) or []]


def closure(llm: dict, rows: list[dict]) -> float:
    """닫힘률 — 뽑은 우대금리 합이 공시 폭과 맞는 행의 비율 (`0012` 와 같은 정의)."""
    by = {p["pair_id"]: p for p in llm["pairs"]}
    live, ok = 0, 0
    for r in rows:
        if abs(r["gap"]) <= TOLERANCE:
            continue                       # 폭 0 행은 분모에서 뺀다 (`0006`)
        got = by.get(r["pair_id"])
        parsed = got["parsed"] if (got and got["schema_ok"]) else None
        its = [i for i in (parsed or {}).get("items", []) or [] if i.get("applies_to_term")]
        s = sum(C.sane_rate(i) for i in its)
        cap = (parsed or {}).get("cap")
        if cap is not None and its:
            s = min(s, cap)
        live += 1
        ok += abs(r["gap"] - s) <= TOLERANCE
    return ok / live * 100 if live else 0.0


def at_budget(group: str, stamp: str, llm: dict) -> tuple[float, int, int]:
    """예산 12개 시점의 커버리지·확정. 보고용이고 판정에는 커버리지만 쓴다."""
    tax = C.load_tax()
    rows = [r for r in load_pairs(stamp, group)[0] if r["term"] == 12]
    llm, _ = C.unify_types(json.loads(json.dumps(llm)))
    by = {p["pair_id"]: p for p in llm["pairs"]}
    state: dict = {}
    scored: list[dict] = []
    for k in range(C.ASK_BUDGET + 1):
        scored = [C.evaluate(r, (by[r["pair_id"]]["parsed"]
                  if by.get(r["pair_id"]) and by[r["pair_id"]]["schema_ok"] else None),
                  state, tax) for r in rows]
        left = C.rank_questions(scored)
        if k == C.ASK_BUDGET or not left:
            break
        key, slot = left[0]
        if slot["needs"]:
            state[key] = max(slot["needs"])
            state.setdefault(key.rpartition("_")[0], True)
        else:
            state[key] = True
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    return (len(main) / len(rows) * 100, len(main),
            sum(1 for s in main if s["tier"] == "확정"))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    verdicts = []
    for group, stamp, lab, gold, floor in SOURCES:
        # v2 를 정식으로 채택했으므로(0021) 비교 대상이 뒤집혔다 — 옛것이 `_v1` 이다
        old, new = load(group, stamp, "v1"), load(group, stamp, "")
        rows = load_pairs(stamp, group)[0]
        oi, ni = items_of(old), items_of(new)
        print(f"\n{'=' * 74}\n{lab}  ({'주 지표' if group == 'bank' else '홀드아웃'})\n{'=' * 74}")

        # 주/부 지표 — 사람이 읽은 정답과 맞는가
        #
        # **사전등록이 예상하지 못한 것** — v2 가 항목을 쪼갠다.
        # `"착한운전마일리지 신청자, 저공해차량 운전자, 전기차운전자, ..."` 한 항목이
        # 다섯으로 갈렸다. 그래서 `prereg-07` 이 적은 분모(11건 · 9건)가 1:1 로
        # 대응하지 않는다. 기준을 결과 보고 고른 게 아니라 **분모가 사라진 것**이라,
        # 두 가지로 다 세어 둘 중 나쁜 쪽을 숨기지 않는다.
        #
        #   문구 종 단위   그 문구를 덮는 항목들의 **다수 유형**으로 판정. 쪼개짐에 안 흔들린다
        #   항목 단위      사전등록이 쓴 단위. 쪼개지면 분모가 커진다
        hit_kind = miss_kind = 0
        hit_item = miss_item = 0
        print(f"{'':<3}{'예측(다수)':<20}{'정답':<20}근거 문구")
        for ev, want in gold.items():
            cov = [i for i in ni
                   if (i.get("evidence") or "").strip()
                   and ((i.get("evidence") or "").strip() in ev
                        or ev in (i.get("evidence") or "").strip())]
            if not cov:
                print(f"{'?':<3}{'(못 찾음)':<20}{want:<20}{ev[:38]}")
                miss_kind += 1
                continue
            got = Counter(i.get("condition_type") for i in cov)
            top = got.most_common(1)[0][0]
            ok = top == want
            hit_kind += ok
            miss_kind += not ok
            hit_item += got.get(want, 0)
            miss_item += sum(n for k, n in got.items() if k != want)
            detail = "" if len(got) == 1 else "  " + str(dict(got))
            print(f"{'O' if ok else 'X':<3}{top:<20}{want:<20}{ev[:38]}"
                  f"  x{sum(got.values())}{detail}")
        nk = hit_kind + miss_kind
        n_it = hit_item + miss_item
        print()
        print(f"  문구 종 단위  {hit_kind}/{nk}"
              + (f" = {hit_kind / nk * 100:.0f}%" if nk else ""))
        print(f"  항목 단위     {hit_item}/{n_it}"
              + (f" = {hit_item / n_it * 100:.0f}%" if n_it else "")
              + "   (v2 가 항목을 쪼개 분모가 사전등록과 다르다)")

        # 회귀 가드
        o_etc = sum(1 for i in oi if i.get("condition_type") == "기타") / len(oi) * 100
        n_etc = sum(1 for i in ni if i.get("condition_type") == "기타") / len(ni) * 100
        o_zero = sum(1 for p in old["pairs"]
                     if p["schema_ok"] and not (p["parsed"] or {}).get("items")) / len(old["pairs"]) * 100
        n_zero = sum(1 for p in new["pairs"]
                     if p["schema_ok"] and not (p["parsed"] or {}).get("items")) / len(new["pairs"]) * 100
        o_cl, n_cl = closure(old, rows), closure(new, rows)
        o_cov, _, o_fix = at_budget(group, stamp, old)
        n_cov, n_main, n_fix = at_budget(group, stamp, new)

        print(f"\n  {'회귀 가드':<20}{'전':>10}{'후':>10}   판정")
        checks = [
            ("닫힘률 %", o_cl, n_cl, n_cl >= o_cl - 2.0, "-2%p 이상 하락 불가"),
            ("`기타` 비율 %", o_etc, n_etc, n_etc <= o_etc, "늘면 불가"),
            ("항목 0개 %", o_zero, n_zero, n_zero <= o_zero, "늘면 불가"),
            ("커버리지 %", o_cov, n_cov, n_cov >= floor - 0.05, f"게이트 {floor:.1f}%"),
        ]
        for name, a, b, ok, why in checks:
            print(f"  {name:<20}{a:>10.1f}{b:>10.1f}   {'통과' if ok else '**불통과**'}  ({why})")
            verdicts.append(ok)
        print(f"  {'(참고) 확정':<20}{o_fix:>10}{n_fix:>10}   판정에 쓰지 않는다 "
              f"(메인 {n_main})")

    print(f"\n{'=' * 74}")
    print("회귀 가드 " + ("전부 통과" if all(verdicts) else "**불통과 있음 — 채택하지 않는다**"))
    print("주/부 지표 임계는 prereg-07 §3 — 은행권 >= 9/11 · 홀드아웃 >= 3/9")
    print()
    print("[2026-08-27] 위 판정은 사전등록 기준 그대로다. **사람이 그걸 알고 v2 를 채택했다**")
    print("             (decisions/0021). 판정을 고쳐서 통과시키지 않는다 — 게이트가 낸 신호를")
    print("             쫓아가서 `exclusive_group` 을 절반쯤 못 믿는다는 것을 찾았기 때문이다.")


if __name__ == "__main__":
    main()
