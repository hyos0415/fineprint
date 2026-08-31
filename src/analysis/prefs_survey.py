# -*- coding: utf-8 -*-
"""선호 가중치가 순위를 실제로 바꾸는가 — `prereg-12` 의 M9·M10 과 예측 4·6.

이 파일이 채우는 자리
    가중치를 넣으면 순위가 바뀌는데 **그게 나아진 건지 확인할 방법이 없다**
    (`prereg-12` §1). 그래서 "좋아졌다" 를 재지 않고, 잴 수 있는 것만 잰다.

      M9   지표 무변동 — 선호가 확정률·커버리지에 새지 않았나. **주 판정이다**
      M10  순위 교체 수 — 가중치가 실제로 순위를 바꾸나. 안 바꾸면 없어도 되는 기능이다
      예측 4  `확실성=많이` 정렬 == `--sort lo` 정렬 (항등식이라 검산된다)
      예측 6  `--prefs` 없음 == 지금 `net_hi` 정렬 (기본값이 새지 않았나)

    **M10 은 방향이 없는 지표다.** 크면 "가중치가 작동한다", 작으면 "이 기능은
    없어도 된다" 는 뜻일 뿐이고 둘 다 결과다 (`prereg-12` §1-4).

사용법:
    python src/analysis/prefs_survey.py 20260826 --group bank --term 12
    python src/analysis/prefs_survey.py 20260825 --group savingsbank --term 12
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import ask_loop as L  # noqa: E402
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402

TOP_K = 10          # 순위 교체를 보는 창. `prereg-12` §7 에 재기 전에 못 박았다

# `prereg-12` §7 이 **재기 전에** 못 박은 선호 조합 여섯. 결과를 보고 고치지 않는다.
COMBOS: list[tuple[str, str | None]] = [
    ("1 (없음)", None),
    ("2 영업점=못간다", "영업점=못간다"),
    ("3 영업점=되도록안간다", "영업점=되도록안간다"),
    ("4 거래기관+처음기관=많이", f"거래기관=우리{P.LIST_SEP}농협,처음기관=많이"),
    ("5 확실성=많이", "확실성=많이"),
    ("6 이행=많이", "이행=많이"),
]


def persona_state(rows: list[dict], by_pair: dict, tax: dict, answer: str) -> dict:
    """질문에 전부 같은 답을 해서 끝까지 간 상태. `check_screen_contract` 와 같은 방식."""
    want = {"예": True, "아니오": False, "모름": C.UNSURE}[answer]
    state: dict = {}
    for _ in range(200):
        scored = AB.score_all(rows, by_pair, state, tax)
        ordered = [(k, s) for k, s in C.rank_questions(scored) if k not in state]
        if not ordered:
            break
        state[ordered[0][0]] = want
    return state


def order_of(scored: list[dict], prefs: dict) -> list[int]:
    """메인 층의 순서. 화면 목록과 **같은 함수**(`ranked`)를 쓴다.

    **상품 코드로 줄을 세우면 안 된다** — 유일하지 않다. 은행권 12개월에서 6개
    코드가 두 행씩이고(적립유형만 다르다) 기본금리가 갈린다. 여기서 비교하는 것은
    전부 같은 `scored` 리스트의 같은 dict 들이므로 `id()` 가 안전한 신원이다.
    """
    return [id(s) for s in L.ranked(scored, prefs)]


def churn(base: list[int], new: list[int], k: int = TOP_K) -> dict:
    """상위 k 의 교체를 센다 — 1위 교체 · 진입 · 이탈 · 자리 바꾼 쌍.

    `자리바꾼쌍` 은 **기준 상위 k 중 새 목록에도 남아 있는 것들 사이**에서 상대
    순서가 뒤집힌 쌍의 수다. 진입·이탈과 겹치지 않게 세려는 것이다.
    """
    b, n = base[:k], new[:k]
    keep = [c for c in b if c in new]
    pos = {c: i for i, c in enumerate(new)}
    flips = sum(1 for i in range(len(keep)) for j in range(i + 1, len(keep))
                if pos[keep[i]] > pos[keep[j]])
    return {"1위교체": bool(base and new and base[0] != new[0]),
            "진입": len([c for c in n if c not in b]),
            "이탈": len([c for c in b if c not in n]),
            "자리바꾼쌍": flips}


def guard_metric_isolation() -> tuple[bool, str]:
    """M9 가드 — 지표 코드가 선호를 아예 모르는가 (`prereg-12` §6).

    숫자를 대조하기 **전에** 구조를 본다. `ask_budget.py`(기준선·게이트·예산 12개)가
    `prefs` 를 import 하면 그 순간 선호로 확정률을 좋게 만드는 길이 열린다(`0018`).
    """
    src = (Path(__file__).resolve().parent / "ask_budget.py").read_text(encoding="utf-8")
    hit = [ln for ln in src.splitlines()
           if "prefs" in ln and not ln.lstrip().startswith("#")]
    return (not hit), ("통과 — ask_budget.py 는 prefs 를 한 번도 안 쓴다" if not hit
                       else f"**불통과** — {hit[:3]}")


def run(stamp: str, group: str, term: int) -> dict:
    tax = C.load_tax()
    rows, by_pair = AB.load(stamp, group, term)
    if not rows:
        raise SystemExit(f"{term}개월 상품이 없다")
    print(f"\n=== 선호 가중치 조사 · {group} {term}개월 · 스냅샷 {stamp} ===")
    print(f"카탈로그 {len(rows)}개 · 상위 {TOP_K} 로 교체를 본다 (prereg-12 §7 고정)\n")

    ok, msg = guard_metric_isolation()
    print(f"M9 가드   지표에 선호를 쓰지 않는다 — {msg}")

    report: dict = {"snapshot": stamp, "group": group, "term": term,
                    "top_k": TOP_K, "metric_isolated": ok, "personas": {}}

    for answer in ("예", "아니오", "모름"):
        state = persona_state(rows, by_pair, tax, answer)
        scored = AB.score_all(rows, by_pair, state, tax)
        main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
        base = order_of(scored, {})
        print("\n" + "-" * 92)
        print(f"페르소나 '{answer}' · 메인 {len(main)}개 · 답한 유형 {len(state)}개")
        print(f"  {'조합':<24}{'1위교체':>8}{'진입':>6}{'이탈':>6}{'자리바꾼쌍':>10}"
              f"{'맨아래':>8}  1위 상품")
        rows_out = []
        for label, arg in COMBOS:
            pf = P.parse(arg)
            new = order_of(scored, pf)
            ch = churn(base, new)
            ranked = L.ranked(scored, pf)
            n_block = sum(1 for s in ranked if s.get("_blocked"))
            top1 = ranked[0]["name"][:26] if ranked else "-"
            print(f"  {label:<24}{'예' if ch['1위교체'] else '-':>8}"
                  f"{ch['진입']:>6}{ch['이탈']:>6}{ch['자리바꾼쌍']:>10}"
                  f"{n_block:>8}  {top1}")
            rows_out.append({"combo": label, "arg": arg, **ch,
                             "blocked": n_block, "top1": top1})

        # ── 예측 4 — `확실성=많이` 는 `--sort lo` 와 **항등식으로** 같아야 한다
        #     점수 = net_hi - 1.0 x (net_hi - net_lo) = net_lo
        lo_order = [id(s) for s in
                    sorted(main, key=lambda x: (-x["net_lo"], -x["net_hi"], x["name"]))]
        cert = order_of(scored, P.parse("확실성=많이"))
        same4 = cert == lo_order
        # ── 예측 6 — 선호가 없으면 지금 `net_hi` 정렬과 같아야 한다
        hi_order = [id(s) for s in
                    sorted(main, key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))]
        same6 = base == hi_order
        print(f"  예측 4  확실성=많이 == --sort lo : "
              f"{'적중 (순서가 완전히 같다)' if same4 else '**빗나감**'}")
        print(f"  예측 6  선호 없음 == 지금 net_hi 정렬 : "
              f"{'적중' if same6 else '**빗나감**'}")
        report["personas"][answer] = {"main": len(main), "answered": len(state),
                                      "combos": rows_out,
                                      "pred4_same_as_sort_lo": same4,
                                      "pred6_same_as_now": same6}
    return report


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
        raise SystemExit("사용법: python src/analysis/prefs_survey.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12]")
    report = run(argv[0], group, term)
    out = C.OUT_DIR / f"prefs_survey_{group}_{argv[0]}_{term}m.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
