# -*- coding: utf-8 -*-
"""스코프별 질문 수와 "좁히는 대가" 를 전수로 잰다 — `prereg-11` M5·M8.

이 파일이 채우는 자리
    `decisions/0028` 이 후보 집합을 1급 개념으로 만들었다. 두 가지를 확인해야 한다.

    M5  스코프를 걸면 질문이 정말 감당할 만한 수로 줄어드나 (예측: 전부 20개 이하)
    M8  좁히면 얼마를 잃나 — 기관별 (전체 최고 − 그 기관 최고). 예측: 중앙값 1.0%p 이상

    M8 이 A7(스코프 밖 최고 금리 표시)의 근거다. 격차가 작으면 A7 은 소음이고,
    크면 안 보여주는 것이 `0017` 이 막은 실패("좋은 상품이 묻힌다")를 되살린다.

**지표가 아니다.** 기준선·게이트는 카탈로그 전체에서만 잰다(`prereg-11` §4). 이 표는
스코프 화면이 어떤 모양이 되는지 보는 것이고, 기준선과 비교하지 않는다.

사용법:
    python src/analysis/scope_survey.py 20260826 --group bank --term 12
    python src/analysis/scope_survey.py 20260825 --group savingsbank --term 12
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402

QUESTION_CAP = 20        # `prereg-11` §3 예측 — 스코프별 질문 수가 이 값을 넘으면 미달


def survey(stamp: str, group: str, term: int) -> dict:
    tax = C.load_tax()
    rows, by_pair = AB.load(stamp, group, term)
    if not rows:
        raise SystemExit(f"{term}개월 상품이 없다")
    # **행으로 짝짓는다** (`prereg-13` · 이슈 #25). 전에는 `code` 를 키로 썼는데
    # 상품코드가 유일하지 않아(저축은행 297행 = 92 code) 같은 코드의 여러 행이
    # **첫 행의 채점 결과**를 함께 썼다. 서로 다른 기본금리를 가진 줄들이다.
    scored = {C.row_key(s): s for s in AB.score_all(rows, by_pair, {}, tax)}
    main = [r for r in rows if scored[C.row_key(r)]["tier"] in C.MAIN_TIERS]
    best_all = max((scored[C.row_key(r)]["net_hi"] for r in main), default=0.0)
    total_q = C.questions_left(C.question_plan(rows, by_pair), {})

    print(f"\n=== 스코프 조사 · {group} {term}개월 · 스냅샷 {stamp} ===")
    print(f"카탈로그 상품 {len(rows)}개 · 메인 {len(main)}개 · 질문 {total_q}개 · "
          f"전체 최고 {best_all:.2f}% (세후, 조건 다 채웠을 때)\n")
    print(f"{'기관':<20}{'상품군':<6}{'상품':>5}{'질문':>5}{'유형':>5}{'문구':>5}"
          f"{'그 기관 최고':>11}{'격차':>8}")
    print("-" * 74)

    out = []
    companies = sorted({r["company"] for r in rows if r["company"]})
    for co in companies:
        for kind in (None, "예금", "적금"):
            sub = C.scope_rows(rows, co, kind)
            if not sub:
                continue
            plan = C.question_plan(sub, by_pair)
            q = C.questions_left(plan, {})
            sub_main = [r for r in sub if scored[C.row_key(r)]["tier"] in C.MAIN_TIERS]
            best = max((scored[C.row_key(r)]["net_hi"] for r in sub_main), default=0.0)
            gap = round(best_all - best, 3)
            row = {"company": co, "kind": kind or "전체", "products": len(sub),
                   "questions": q, "types": len(plan),
                   "clauses": sum(len(v) for v in plan.values()),
                   "best": best, "gap": gap}
            out.append(row)
            if kind is None:                       # 화면은 기관 전체 줄만 찍는다
                mark = "  <- 캡 초과" if q > QUESTION_CAP else ""
                print(f"{co[:19]:<20}{'전체':<6}{len(sub):>5}{q:>5}{len(plan):>5}"
                      f"{sum(len(v) for v in plan.values()):>5}{best:>10.2f}%"
                      f"{gap:>7.2f}p{mark}")

    whole = [r for r in out if r["kind"] == "전체"]
    qs = sorted(r["questions"] for r in whole)
    gaps = sorted(r["gap"] for r in whole)
    over = [r for r in out if r["questions"] > QUESTION_CAP]
    print("-" * 74)
    print(f"M5  스코프별 질문 수 — 중앙값 {qs[len(qs) // 2]}개 · 최대 {qs[-1]}개 · "
          f"{QUESTION_CAP}개 초과 {len(over)}건 "
          f"→ **{'통과' if not over else '미달'}** (예측 {QUESTION_CAP}개 이하)")
    print(f"M8  좁히는 대가 — 격차 중앙값 {gaps[len(gaps) // 2]:.2f}%p · "
          f"1.0%p 초과 {sum(1 for g in gaps if g > 1.0)}/{len(gaps)}곳 "
          f"→ **{'통과' if gaps[len(gaps) // 2] >= 1.0 else '미달'}** (예측 1.0%p 이상)")
    print("    격차가 큰 것이 A7(스코프 밖 최고 금리 표시)의 근거다")
    return {"snapshot": stamp, "group": group, "term": term,
            "catalog": {"products": len(rows), "main": len(main),
                        "questions": total_q, "best": best_all},
            "scopes": out}


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
        raise SystemExit("사용법: python src/analysis/scope_survey.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12]")
    report = survey(argv[0], group, term)
    out = C.OUT_DIR / f"scope_survey_{group}_{argv[0]}_{term}m.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
