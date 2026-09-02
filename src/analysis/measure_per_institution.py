# -*- coding: utf-8 -*-
"""조건을 기관별로 가른 것이 무엇을 바꿨나 — `prereg-15` 의 예측 P1~P7 을 잰다.

이 파일이 채우는 자리
    F6(이슈 #44)이 **정확성 결함**을 고쳤다. 사용자의 답이 기관과 무관한 전역 값이라
    답 하나가 여러 기관 상품을 한꺼번에 올렸고, "첫거래" 와 "주거래" 를 한 은행에서
    동시에 줘서 **확정 금리를 실제보다 높게** 말했다.

    고친 것이 얼마나 움직였는지를 사전등록한 예측과 대조한다. **예측은 구현 전에
    커밋했다**(`docs/spec/prereg-15-conditions-are-per-institution.md` · 커밋 4b8349e).

무엇을 재나 — 페르소나 정의는 `prereg-15` §3.1 에 **측정 전에** 못 박았다
    지금(기준선)   유형 질문을 전역으로 전부 "예"
    새 동작 · N곳  거래 은행 = 상품 커버리지 상위 N곳 · 나머지 질문은 전부 "예"
    P1·P2·P3      기관 **하나씩 전부**를 "거래 1곳" 으로 둔 페르소나를 다 재고 중앙값

    "평균 확정 금리" 는 **메인 상품의 `net_lo` 평균**이다(§3.1). 확정 층만 평균하면
    다른 숫자가 나오는데, §2 기준선이 쓴 정의가 앞의 것이다.

돈은 안 든다. LLM 을 부르지 않는다 — 추출 결과를 읽어 계산만 한다.

사용법:
    python src/analysis/measure_per_institution.py 20260826 --group bank --term 12
    python src/analysis/measure_per_institution.py 20260825 --group savingsbank
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402
import view as V  # noqa: E402


def companies_by_coverage(rows: list[dict]) -> list[str]:
    """기관을 **상품 수** 순으로. 동점은 이름 순 — 내용에 무관한 기준이다(`0018`)."""
    tally: dict[str, set] = {}
    for r in rows:
        co = r.get("company") or ""
        if co:
            tally.setdefault(co, set()).add(C.product_key({"co_no": r.get("co_no"),
                                                           "code": r["code"]}))
    return sorted(tally, key=lambda c: (-len(tally[c]), c))


def type_keys(plan: dict) -> list[str]:
    """유형 질문 키만. 목록 키와 문구 단위 후속은 뺀다 (`prereg-15` §3.1)."""
    return [k for k in plan if k != C.TRADED_KEY]


def state_now(plan: dict) -> dict:
    """**지금 동작** — 유형 질문을 전역으로 전부 "예".

    기관이 붙은 키를 전역 유형 키로 되돌려 넣는다. 그러면 `answer_of()` 가 목록을
    보기 전에 그 값을 못 찾으므로... 가 아니다 — 기관 상대 유형은 기관 키만 읽는다.
    그래서 **여기서는 기관 키 전부에 "예"** 를 넣어 옛 동작(답 하나가 전 기관에 걸리는
    것)을 재현한다. 목록 질문에는 답하지 않는다.
    """
    return {k: True for k in type_keys(plan)}


def state_new(plan: dict, banks: list[str]) -> dict:
    """**새 동작** — 목록에 `banks` 를 답하고, 나머지 유형 질문은 전부 "예".

    유도가 걸리는 자리에는 답을 넣지 않는다 — 넣으면 유도를 덮어써 측정이 무의미해진다.
    `첫거래`·`주거래` 는 한 기관에서 배타이므로 **커버리지 순으로 먼저 오는 쪽**만
    "예" 가 되고 다른 쪽은 유도로 "아니오" 가 된다.
    """
    state: dict = {C.TRADED_KEY: list(banks)}
    for key in type_keys(plan):
        kind, _at, co = key.partition("@")
        if C.answer_of(kind, co, state) is None:
            state[key] = True
    return state


def n_types(plan: dict) -> int:
    """**옛 동작의 질문 수** — 기관을 뺀 조건 유형의 종수다.

    기관별로 갈리기 전에는 유형 하나가 질문 하나였다(은행권 15 · 저축은행 13 ·
    `prereg-15` §2). 새 코드의 `plan` 은 기관까지 갈라 65개가 되므로, 기준선의
    질문 수를 `len(plan)` 으로 세면 **옛 동작이 안 물었던 질문까지 세는 것**이 된다.
    """
    return len({k.partition("@")[0] for k in type_keys(plan)})


def top3_swaps(rows: list[dict], by_pair: dict, tax: dict,
               banks: list[str] | None) -> dict:
    """질문에 하나씩 답할 때 **상위 3위가 몇 개 바뀌나** — P7 이 보는 값.

    `0017` 이 *"전 구간 0"* 이라고 적은 것과 같은 측정이다(`ask_budget` 곡선의
    `상위3교체` 열). 기준선과 최종 상태를 한 번 비교하는 것이 아니라 **답마다** 본다 —
    `0017` 의 반증 조건이 *"답마다 2개 이상 계속 일어나면"* 이기 때문이다.
    """
    state: dict = {}
    prev = None
    swaps = []
    for _ in range(400):
        scored = AB.score_all(rows, by_pair, state, tax)
        main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
        top3 = [C.row_key(s) for s in
                sorted(main, key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))[:3]]
        if prev is not None:
            swaps.append(len(set(prev) - set(top3)))
        prev = top3
        key, _slot = V.next_question(scored, state)
        if key is None:
            break
        if key == C.TRADED_KEY:
            state[key] = list(banks) if banks is not None else C.UNSURE
        else:
            state[key] = True
    return {"단계": len(swaps), "최대": max(swaps, default=0),
            "합계": sum(swaps), "2이상_단계수": sum(1 for x in swaps if x >= 2),
            "열": swaps}


def snap(rows: list[dict], by_pair: dict, plan: dict, state: dict, tax: dict) -> dict:
    """한 상태의 숫자들. **정의는 `prereg-15` §3.1 에 못 박은 것을 쓴다.**"""
    scored = AB.score_all(rows, by_pair, state, tax)
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    fixed = [s for s in main if s["tier"] == "확정"]
    widths = [s["net_hi"] - s["net_lo"] for s in main]
    n_q = sum(1 for k in type_keys(plan) if k in state)
    if C.TRADED_KEY in plan and C.TRADED_KEY in state:
        n_q += 1
    return {
        "메인": len(main), "확정": len(fixed),
        "확정률": round(len(fixed) / len(main) * 100, 1) if main else 0.0,
        "폭평균": round(sum(widths) / len(widths), 4) if widths else 0.0,
        "폭최대": round(max(widths), 4) if widths else 0.0,
        "평균확정금리": round(sum(s["net_lo"] for s in main) / len(main), 4) if main else 0.0,
        "질문수": n_q,
        "_net_lo": {C.row_key(s): s["net_lo"] for s in main},
        "_top3": [C.row_key(s) for s in
                  sorted(main, key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))[:3]],
        "_products": {C.row_key(s): (s["name"], s.get("company") or "") for s in main},
    }


def budget_state(rows: list[dict], by_pair: dict, tax: dict, banks: list[str] | None,
                 budget: int) -> dict:
    """예산 N개 시점의 상태 — **화면이 묻는 순서 그대로** 앞에서 N개를 답한다.

    목록 질문은 순서상 맨 앞이라, `banks` 를 주면 그 답으로 첫 질문이 소비된다.
    """
    state: dict = {}
    for _ in range(budget):
        scored = AB.score_all(rows, by_pair, state, tax)
        key, slot = V.next_question(scored, state)
        if key is None:
            break
        if key == C.TRADED_KEY:
            state[key] = list(banks) if banks is not None else C.UNSURE
        else:
            state[key] = True
        del slot
    return state


def exclusive_both(rows: list[dict], by_pair: dict, state: dict, tax: dict) -> list[dict]:
    """**첫거래와 주거래를 동시에 받는 상품** — P4 가 0 이라고 예측한 것.

    `why.met` 에 두 유형이 같이 있으면 그 상품은 "신규 고객이면서 주거래" 로 계산된
    것이다. 한 사람이 그럴 수는 없다.
    """
    out = []
    for s in AB.score_all(rows, by_pair, state, tax):
        met = {d["type"] for d in (s.get("why") or {}).get("met", [])}
        if C.FIRST_DEAL in met and C.MAIN_DEAL in met:
            pp = {d["type"]: d["pp"] for d in s["why"]["met"]}
            out.append({"상품": s["name"], "기관": s.get("company") or "",
                        "첫거래": pp[C.FIRST_DEAL], "주거래": pp[C.MAIN_DEAL]})
    return out


def run(stamp: str, group: str, term: int) -> dict:
    tax = C.load_tax()
    rows, by_pair = AB.load(stamp, group, term)
    if not rows:
        raise SystemExit(f"{term}개월 상품이 없다")
    plan = C.question_plan(rows, by_pair)
    order = companies_by_coverage(rows)

    print(f"\n=== F6 측정 · {group} {term}개월 · 스냅샷 {stamp} ===")
    print(f"상품 {len(rows)}행 · 기관 {len(order)}곳 · 유형 질문 {len(type_keys(plan))}개 "
          f"(기관 상대가 갈린 뒤) · 목록 질문 {'있다' if C.TRADED_KEY in plan else '없다'}")
    print(f"기관 커버리지 순 상위 5곳: {', '.join(order[:5])}")

    now = snap(rows, by_pair, plan, state_now(plan), tax)
    now["질문수"] = n_types(plan)        # 옛 동작이 실제로 물었던 수 (기관을 뺀 유형 종수)
    print("\n■ 지금(기준선) — 유형 질문을 전역으로 전부 '예'")
    print(f"    확정 {now['확정']}/{now['메인']} ({now['확정률']}%) · "
          f"폭평균 {now['폭평균']:.3f} · 폭최대 {now['폭최대']:.3f} · "
          f"평균확정금리 {now['평균확정금리']:.3f}% · 유형질문 {now['질문수']}개")
    print("    ↑ `prereg-15` §2 의 '전부 답한 시점' 과 같은 값이어야 한다 "
          "(은행권 39/67 · 0.172 · 1.861 · 2.975 · 15개)")

    # ── P5 — 거래 은행 수별 질문 수
    print("\n■ P5 — 거래 은행 수별 질문 수 (유형 질문 + 목록 질문 1개)")
    by_n = {}
    for n in (0, 1, 2, 3, len(order)):
        st = state_new(plan, order[:n])
        s = snap(rows, by_pair, plan, st, tax)
        by_n[n] = s
        print(f"    {n:>2}곳   질문 {s['질문수']:>3}개 (지금 {now['질문수']}개 대비 "
              f"{s['질문수'] - now['질문수']:+d}) · 확정 {s['확정']}/{s['메인']} "
              f"({s['확정률']}%) · 폭평균 {s['폭평균']:.3f} · "
              f"평균확정금리 {s['평균확정금리']:.3f}%")

    # ── P1·P2·P3 — 기관 하나씩 전부를 "거래 1곳" 으로
    print("\n■ P1·P2·P3 — 기관 하나씩을 '거래 1곳' 으로 둔 페르소나 "
          f"{len(order)}개 (중앙값으로 판정 · §3.1)")
    one = []
    for co in order:
        st = state_new(plan, [co])
        s = snap(rows, by_pair, plan, st, tax)
        over = [(now["_net_lo"][k] - s["_net_lo"][k], k)
                for k in s["_net_lo"] if k in now["_net_lo"]
                and now["_net_lo"][k] - s["_net_lo"][k] > 1e-9]
        swap = len(set(now["_top3"]) - set(s["_top3"]))
        one.append({"기관": co, "확정": s["확정"], "메인": s["메인"],
                    "확정률": s["확정률"], "평균확정금리": s["평균확정금리"],
                    "폭평균": s["폭평균"], "질문수": s["질문수"],
                    "과대_상품수": len(over),
                    "과대_평균": round(sum(d for d, _ in over) / len(over), 4) if over else 0.0,
                    "과대_최대": round(max((d for d, _ in over), default=0.0), 4),
                    "상위3교체": swap})
    def mid(field):
        return round(statistics.median(x[field] for x in one), 4)
    print(f"    {'기관':<16}{'확정':>8}{'확정률':>8}{'평균확정':>9}{'질문':>6}"
          f"{'과대수':>7}{'과대평균':>9}{'과대최대':>9}{'상위3교체':>9}")
    for x in one:
        print(f"    {x['기관'][:15]:<16}{x['확정']:>4}/{x['메인']:<3}{x['확정률']:>7.1f}%"
              f"{x['평균확정금리']:>9.3f}{x['질문수']:>6}{x['과대_상품수']:>7}"
              f"{x['과대_평균']:>9.3f}{x['과대_최대']:>9.3f}{x['상위3교체']:>9}")
    print(f"    {'중앙값':<16}{'':>8}{mid('확정률'):>7.1f}%{mid('평균확정금리'):>9.3f}"
          f"{mid('질문수'):>6.0f}{mid('과대_상품수'):>7.0f}{mid('과대_평균'):>9.3f}"
          f"{mid('과대_최대'):>9.3f}{mid('상위3교체'):>9.0f}")

    # ── P4 — 첫거래·주거래 동시
    print("\n■ P4 — 첫거래와 주거래를 동시에 받는 상품")
    both_now = exclusive_both(rows, by_pair, state_now(plan), tax)
    both_new = {}
    for n in (1, 2, 3, len(order)):
        both_new[n] = exclusive_both(rows, by_pair, state_new(plan, order[:n]), tax)
    print(f"    지금       {len(both_now)}개")
    for b in both_now:
        print(f"        {b['기관']} {b['상품'][:24]}  "
              f"첫거래 +{b['첫거래']:.2f}%p · 주거래 +{b['주거래']:.2f}%p "
              f"→ +{b['첫거래'] + b['주거래']:.2f}%p 를 다 준다")
    for n, lst in both_new.items():
        print(f"    새 동작·{n}곳  {len(lst)}개" + ("" if not lst else f"  {lst}"))

    # ── P6 — 예산 12개 시점
    print(f"\n■ P6 — 예산 {C.ASK_BUDGET}개 시점 (`0018`) — "
          f"기준선은 {'0.185' if group == 'bank' else '0.449'} (§2)")
    b_now = snap(rows, by_pair, plan,
                 budget_state(rows, by_pair, tax, None, C.ASK_BUDGET), tax)
    print(f"    새 동작·목록 모름   확정 {b_now['확정']}/{b_now['메인']} "
          f"({b_now['확정률']}%) · 폭평균 {b_now['폭평균']:.3f} · "
          f"폭최대 {b_now['폭최대']:.3f}")
    budgets = {}
    for n in (0, 1, 2, 3):
        s = snap(rows, by_pair, plan,
                 budget_state(rows, by_pair, tax, order[:n], C.ASK_BUDGET), tax)
        budgets[n] = s
        print(f"    새 동작·{n}곳        확정 {s['확정']}/{s['메인']} ({s['확정률']}%) · "
              f"폭평균 {s['폭평균']:.3f} · 폭최대 {s['폭최대']:.3f}")

    # ── P7 — 답마다 상위 3위가 몇 개 바뀌나
    print("\n■ P7 — 상위 3위 교체 (답마다 · `0017` 반증 조건과 같은 측정)")
    swaps = {}
    for label, banks in (("0곳", []), ("1곳", order[:1]), ("2곳", order[:2]),
                         ("3곳", order[:3]), ("전부", order), ("목록 모름", None)):
        s = top3_swaps(rows, by_pair, tax, banks)
        swaps[label] = s
        print(f"    {label:<8}단계 {s['단계']:>3}개 · 교체 합계 {s['합계']:>3} · "
              f"최대 {s['최대']} · 2개 이상인 단계 {s['2이상_단계수']}개")

    strip = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}   # noqa: E731
    return {
        "snapshot": stamp, "group": group, "term": term,
        "기관_커버리지순": order,
        "지금": strip(now),
        "거래은행수별": {str(k): strip(v) for k, v in by_n.items()},
        "거래1곳_전수": one,
        "거래1곳_중앙값": {f: mid(f) for f in
                       ("확정률", "평균확정금리", "폭평균", "질문수",
                        "과대_상품수", "과대_평균", "과대_최대", "상위3교체")},
        "첫거래주거래_동시": {"지금": both_now,
                        **{f"새_{k}곳": v for k, v in both_new.items()}},
        f"예산{C.ASK_BUDGET}": {"목록모름": strip(b_now),
                              **{f"{k}곳": strip(v) for k, v in budgets.items()}},
        "상위3교체": swaps,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term = "bank", 12
    for flag in ("--group", "--term"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            v = argv[i + 1]
            group = v if flag == "--group" else group
            term = int(v) if flag == "--term" else term
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/measure_per_institution.py "
                         "YYYYMMDD [--group bank|savingsbank] [--term 12]")
    out = run(argv[0], group, term)
    path = C.OUT_DIR / f"f6_measure_{group}_{argv[0]}_{term}m.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    print(f"\n→ {path.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
