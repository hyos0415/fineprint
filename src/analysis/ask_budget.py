# -*- coding: utf-8 -*-
"""질문을 하나씩 늘려가며 층·확정·범위 폭이 어떻게 움직이는지 잰다.

이 파일이 채우는 자리
    되묻기(`decisions/0015`·`0016`)를 넣은 뒤 은행권 범위가 0이 됐는데, 그게 진짜
    개선인지 **"질문을 많이 만들면 확정이 늘어난다"는 지표 허점**인지 가릴 장치가 없었다.
    `prereg-06` §2.3(1)의 회피 방지 제약식을 정하려면 먼저 이 곡선이 필요하다.

무엇을 재나
    상품 커버리지가 큰 질문부터 하나씩 "예"로 답해 가면서 각 단계의
    메인 층 수 · 확정 수 · 범위 폭 평균/최대 · 상위 3위 교체 수를 찍는다.
    임계가 붙은 질문은 **가장 높은 임계를 넘는 값**으로 답한다(다 충족 페르소나).
    목록 질문(F6)에는 **전 은행과 거래한다**로 답한다 — 같은 페르소나의 연장이고,
    유도가 하나도 안 걸려 질문이 가장 많은 경로다.

읽는 법 — 실측에서 나온 두 가지 (2026-08-27)
    1. **메인 층 수는 질문에 안 변한다.** 은행권 64 · 저축은행 109가 질문 0개에서
       전부 답할 때까지 고정이다. 되묻기는 `범위`를 `확정`으로 옮길 뿐이고, 메인
       안팎은 닫힘률(=추출)이 정한다. 그래서 **메인 비율은 질문 부풀리기를 못 막는다.**
    2. **범위 폭 평균은 질문 수에 단조 감소한다.** 질문을 늘리면 무조건 좋아지므로
       **폭 평균은 질문 부풀리기를 오히려 보상한다.** 단독 지표로 쓰면 안 된다.

사용법:
    python src/analysis/ask_budget.py 20260826 --group bank --term 12
    python src/analysis/ask_budget.py 20260825 --group savingsbank --term 12 --tolerance
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate as C  # noqa: E402
from extract_llm import load_pairs  # noqa: E402

# 무한 루프 방어. F6 뒤로 질문이 기관별로 갈려 은행권 90 · 저축은행 45 다
# (`prereg-15` P5). 옛 값 60 은 곡선을 조용히 잘랐다
MAX_STEPS = 400


def load(stamp: str, group: str, term: int) -> tuple[list[dict], dict]:
    suffix = "" if group == "bank" else f"_{group}"
    llm_path = C.OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    if not llm_path.exists():
        raise SystemExit(f"추출 결과가 없다: {llm_path.relative_to(C.REPO_ROOT)}")
    rows, _ = load_pairs(stamp, group)
    llm, _ = C.unify_types(json.loads(llm_path.read_text(encoding="utf-8")))
    return ([r for r in rows if r["term"] == term],
            {p["pair_id"]: p for p in llm["pairs"]})


def score_all(rows: list[dict], by_pair: dict, state: dict, tax: dict) -> list[dict]:
    out = []
    for row in rows:
        got = by_pair.get(row["pair_id"])
        parsed = got["parsed"] if (got and got["schema_ok"]) else None
        out.append(C.evaluate(row, parsed, state, tax))
    return out


def stats(scored: list[dict]) -> dict:
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    fixed = [s for s in main if s["tier"] == "확정"]
    widths = [s["net_hi"] - s["net_lo"] for s in main]
    # 상위 3위 교체는 **행** 단위다 — 같은 상품의 단리·복리는 화면에서 다른 줄이다
    # (`prereg-13`). `code` 로 세면 저축은행에서 서로 다른 법인의 줄이 합쳐진다.
    top3 = [C.row_key(s) for s in
            sorted(main, key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))[:3]]
    return {"메인": len(main), "확정": len(fixed), "범위": len(main) - len(fixed),
            "폭평균": sum(widths) / len(widths) if widths else 0.0,
            "폭최대": max(widths) if widths else 0.0, "top3": top3}


# ── 기준선 — 제약식이 지켜야 할 하한 (`decisions/0018` · 2026-08-27 실측)
#
# **coverage 는 점수에 더하지 않는다. 통과·불통과를 가르는 게이트로만 쓴다**(사람 결정).
# 더하면 "coverage 를 조금 깎고 다른 지표를 크게 올리는" 거래가 가능해지고, 그게
# 막으려던 도피다.
# 2026-08-27 재등록 (`decisions/0019`). 옛 값 은행권 81.0% · 저축은행 36.7% 은
# **버그가 있던 코드의 값**이다 — 조건 아닌 문구를 조건으로 세고(13건), 그중 4건은
# 항상 충족으로 계산했으며, 금액 임계를 띄어쓰기 없으면 못 잡았다(36건).
# 세 수정은 **전부 확정률을 낮추는 방향**이라, 유리한 기준을 고른 재등록이 아니다.
# 재등록 예고와 편향 방향은 `prereg-06` §2.3(1)에 **고치기 전에** 적었다.
COVERAGE_FLOOR = {("bank", 12): 79.7, ("savingsbank", 12): 36.7}   # 메인 층 비율 %


def pending(scored: list[dict], state: dict | None = None) -> list[tuple[str, dict]]:
    """아직 안 물어본 질문을 **고정된 우선순위**로. 규칙은 `calculate.rank_questions`."""
    return C.rank_questions(scored, state)


def curve(stamp: str, group: str, term: int) -> list[dict]:
    tax = C.load_tax()
    rows, by_pair = load(stamp, group, term)
    if not rows:
        raise SystemExit(f"{term}개월 상품이 없다")
    print(f"\n=== {group} {term}개월 · 상품 {len(rows)}개 · 스냅샷 {stamp} ===")
    print(f"{'답한질문':>8} {'메인':>5} {'확정':>5} {'범위':>5} {'폭평균':>8} {'폭최대':>8}"
          f" {'상위3교체':>9}  다음 질문")
    state: dict = {}
    prev_top3: list[str] | None = None
    log = []
    for k in range(MAX_STEPS + 1):
        scored = score_all(rows, by_pair, state, tax)
        st = stats(scored)
        swap = "-" if prev_top3 is None else str(len(set(prev_top3) - set(st["top3"])))
        left = pending(scored, state)
        nxt = (f"{left[0][0]} ({len(left[0][1]['products'])}상품 · 남은질문 {len(left)})"
               if left else "— 없음")
        print(f"{k:>8} {st['메인']:>5} {st['확정']:>5} {st['범위']:>5} "
              f"{st['폭평균']:>8.3f} {st['폭최대']:>8.3f} {swap:>9}  {nxt}")
        log.append({"답한질문": k, "남은질문": len(left),
                    **{x: st[x] for x in ("메인", "확정", "범위", "폭평균", "폭최대")}})
        prev_top3 = st["top3"]
        if k == C.ASK_BUDGET:
            print(f"{'':>8} {'-' * 62}  <- 평가 예산 {C.ASK_BUDGET}개까지")
        if not left:
            break
        key, slot = left[0]
        if slot["unit"] == C.LIST_UNIT:
            # **목록 질문은 `True` 로 답할 수 없다** (F6). 그렇게 넣으면 모양이 틀린
            # 값이라 `answer_of()` 가 "안 물어본 것" 으로 보고, 곡선이 조용히
            # **목록에 "모름" 으로 답한 경로**를 재게 된다 — 실측으로 예산 12개 시점
            # 확정이 14/67(20.9%)로 떨어졌다. 이 파일의 전제는 *"다 충족 페르소나"*
            # 이므로 **전 은행과 거래한다**로 답한다(질문이 가장 많은 경로이기도 하다).
            state[key] = sorted(slot["기관"])
        else:
            state[key] = True                 # 유형이든 문구든 "예" 다 (`prereg-10`)

    at = next((r for r in log if r["답한질문"] == C.ASK_BUDGET), log[-1])
    total = len(rows)
    cover = at["메인"] / total * 100
    floor = COVERAGE_FLOOR.get((group, term))
    print()
    print(f"예산 {at['답한질문']}개 시점 — 확정 {at['확정']}/{at['메인']} "
          f"({at['확정'] / at['메인'] * 100:.1f}%) · 폭 평균 {at['폭평균']:.3f}%p")
    # **어느 페르소나의 값인지 적는다** (F6 뒤로 갈린다). 이 곡선은 다 충족 페르소나 —
    # 목록 질문에 **전 은행과 거래한다**로 답하므로 유도가 하나도 안 걸리고, 질문 하나가
    # 은행 하나만 연다. 거래 은행이 적은 사용자는 훨씬 빨리 확정된다
    print("    페르소나 — 다 충족(전 은행과 거래). 거래 은행 수별 값은 "
          "measure_per_institution.py 가 낸다")
    if floor is None:
        print(f"coverage {cover:.1f}% ({at['메인']}/{total}) · 이 조합의 기준선은 아직 없다")
    else:
        ok = "통과" if cover >= floor - 0.05 else "불통과"
        print(f"coverage {cover:.1f}% ({at['메인']}/{total}) · 기준선 {floor:.1f}% "
              f"→ **{ok}**   (게이트다. 점수에 더하지 않는다)")
    return log


def tolerance_sweep(stamp: str, group: str, term: int) -> None:
    """허용 오차를 넓혀 메인 층을 부풀릴 수 있는지 — 우회로 점검.

    없다. 넓힐수록 **줄어든다** — 공시 최고금리 = 기본금리인 행이 `공시미반영` 층으로
    빠지기 때문이다. 이 방향은 막을 필요가 없다.
    """
    tax = C.load_tax()
    rows, by_pair = load(stamp, group, term)
    original = C.TOLERANCE
    print(f"\n--- 허용 오차 우회로 점검 · {group} {term}개월 ---")
    print(f"{'허용오차%p':>10} {'메인':>5} {'비율':>7}")
    try:
        for tol in (0.0, 0.06, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0):
            C.TOLERANCE = tol
            n = sum(1 for s in score_all(rows, by_pair, {}, tax)
                    if s["tier"] in C.MAIN_TIERS)
            mark = "  <- 지금 값" if tol == original else ""
            print(f"{tol:>10.2f} {n:>5} {n / len(rows) * 100:>6.1f}%{mark}")
    finally:
        C.TOLERANCE = original


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, sweep = "bank", 12, False
    if "--tolerance" in argv:
        sweep = True
        argv.remove("--tolerance")
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
        raise SystemExit("사용법: python src/analysis/ask_budget.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--tolerance]")
    stamp = argv[0]
    log = curve(stamp, group, term)
    if sweep:
        tolerance_sweep(stamp, group, term)
    out = C.OUT_DIR / f"ask_budget_{group}_{stamp}_{term}m.json"
    out.write_text(json.dumps({"snapshot": stamp, "group": group, "term": term,
                               "curve": log}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
