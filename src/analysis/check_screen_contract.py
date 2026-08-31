# -*- coding: utf-8 -*-
"""화면 계약 전수 검사 — 중단해도 화면이 정직한가.

이 파일이 채우는 자리
    `decisions/0026` 이 정한 것 — **완주율은 지표가 아니다.** 중단은 시스템이 지원하는
    상태(안 물은 것은 범위 + `미응답` 사유)이고, 위험은 사용자가 멈추는 것이 아니라
    **멈춘 상태에서 우리 화면이 단정하는 것**이다. 그 실패는 이미 한 번 일어났다 —
    `0019` 의 부산은행 사례(사용자 입력 0개에서 4.80% 가 확정처럼 보였다).

    `design.md` §화면 계약이 *"화면 코드에 assert 를 박는다"* 고 적어 둔 것이 이 파일이다.
    사람이 답할 필요가 없다. 돈도 안 든다.

무엇을 검사하나 — `prereg-09` §3 의 다섯 문장 그대로
    A1  net_lo != net_hi 인 상품을 단일 숫자로 렌더하지 않는다
    A2  tier == "확정" 이면 net_lo == net_hi 여야 한다
    A3  caveats 가 비어 있지 않으면 사유 문장이 화면 문자열에 있어야 한다
    A4  질문에 답할 때마다 "남은 질문 수" 가 늘어나지 않는다
    A5  net_hi 가 공시 최고금리(세후)를 넘지 않는다
    A6  화면의 "답한 질문 N" 이 실제로 답한 횟수와 같다 (`0028` — 나중에 추가했다)
    A7  스코프가 걸린 화면에는 **스코프 밖 최고 금리**가 있어야 한다 (`0028` S4)
    A8  성과 줄의 범위가 실제 1위 상품의 net_lo~net_hi 와 같아야 한다 (`0029`)
    A9  화면의 가입 채널 표시가 원천 `join_way` 와 일치해야 한다 (이슈 #22)

    검사 대상 화면은 `ask_loop.render_final_screen()` 이다 — **사용자가 12번째 질문에서
    그만두면 보는 것이 정확히 그 화면**이므로, 모든 중간 상태에 대해 같은 함수를 읽는다.

표본 — `prereg-09` §4 에서 **재기 전에** 못 박았다
    P1  세 페르소나(전부 예 · 전부 아니오 · 전부 모름)의 모든 단계
    P2  시드 0~199 고정 무작위 혼합 세션 (매 질문 예/아니오/모름/숫자를 무작위)

사용법:
    python src/analysis/check_screen_contract.py 20260826 --group bank --term 12
    python src/analysis/check_screen_contract.py 20260826 --seeds 20    (빠른 점검)
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import ask_loop as L  # noqa: E402
import calculate as C  # noqa: E402

SEEDS = 200          # `prereg-09` §4 에 못 박은 값. 결과를 보고 고치지 않는다
EPS = 1e-6

# A3 에서 "화면에 문장이 있어야 한다" 고 요구하는 사유 코드 — `CAVEAT` 전부다.
# 지금 3단계 화면은 `HARD_CAVEATS` 여섯 개만 문장으로 낸다. 그 차이가 위반으로 잡히면
# **그것이 이 검사가 찾은 것**이다(`prereg-09` §5 가 A3 위반 가능성을 예고했다).
A3_CODES = tuple(C.CAVEAT.keys())


def check_state(screen: str, scored: list[dict], tax: dict) -> list[dict]:
    """한 중간 상태의 화면에 대해 A1·A2·A3·A5 를 본다. A4 는 세션 단위라 따로."""
    bad = []
    main = L.ranked(scored)
    for i, s in enumerate(main, 1):
        line = L.product_line(i, s)
        width = s["net_hi"] - s["net_lo"]
        if width > EPS and "~" not in L.span(s):
            bad.append({"assert": "A1", "product": s["name"], "detail": line})
        if s["tier"] == "확정" and width > EPS:
            bad.append({"assert": "A2", "product": s["name"],
                        "detail": f"확정인데 폭 {width:.4f}%p — {line}"})
        if s.get("channel") != C.channel_label(s.get("join_way", "")):      # A9
            bad.append({"assert": "A9", "product": s["name"],
                        "detail": f"화면 [{s.get('channel')}] ≠ join_way "
                                  f"'{s.get('join_way')}'"})
        net_cap, _ = C.after_tax(s["disclosed_max"], tax)
        if s["net_hi"] > net_cap + EPS:
            bad.append({"assert": "A5", "product": s["name"],
                        "detail": f"net_hi {s['net_hi']:.4f} > 공시 상한(세후) {net_cap:.4f}"})
    shown = {c for s in main for c in s.get("caveats", [])}
    for code in sorted(shown & set(A3_CODES)):
        if C.CAVEAT[code] not in screen:
            bad.append({"assert": "A3", "product": f"사유 {code}",
                        "detail": f'"{C.CAVEAT[code][:40]}…" 가 화면에 없다'})
    return bad


def pick_answer(slot: dict, rng: random.Random | None, persona: str | None) -> tuple[str, str]:
    """(원문, 종류). 페르소나면 고정, 무작위면 시드로 뽑는다.

    `prereg-10` 뒤로 유형 질문과 문구 질문이 같은 모양이라 답은 셋뿐이다 —
    수치 경로가 사라졌다.
    """
    if persona:
        return {"예": ("예", "yes"), "아니오": ("아니오", "no"),
                "모름": ("모름", "unsure")}[persona]
    assert rng is not None
    kind = rng.choice(["yes", "no", "unsure"])
    return ({"yes": "예", "no": "아니오", "unsure": "모름"}[kind], kind)


def walk(rows: list[dict], by_pair: dict, plan: dict, total: int, tax: dict,
         persona: str | None = None, seed: int | None = None,
         rows_all: list[dict] | None = None) -> list[dict]:
    """세션 하나를 끝까지 걸으며 각 중간 상태를 검사한다. 위반 목록을 낸다."""
    rng = random.Random(seed) if seed is not None else None
    state: dict = {}
    bad: list[dict] = []
    prev_left = None
    scoped = rows_all is not None and len(rows_all) > len(rows)
    for step in range(len(plan) * 3 + 5):        # 무한 루프 방어
        scored = AB.score_all(rows, by_pair, state, tax)
        outside = (L.outside_best(rows_all, rows, by_pair, state, tax)
                   if scoped else None)
        screen, st = L.render_final_screen(scored, plan, state, total, None, outside)
        if outside and f"{outside['net_hi']:.2f}%" not in screen:      # A7
            bad.append({"assert": "A7", "product": outside["name"], "session": "-",
                        "step": step,
                        "detail": f"스코프 밖 최고 {outside['net_hi']:.2f}% 가 화면에 없다"})
        tag = persona or f"seed{seed}"
        for v in check_state(screen, scored, tax):
            bad.append({**v, "session": tag, "step": step})
        if prev_left is not None and st["left"] > prev_left:      # A4
            bad.append({"assert": "A4", "product": "-", "session": tag, "step": step,
                        "detail": f"남은 질문 {prev_left} → {st['left']} 로 늘었다"})
        main_now = L.ranked(scored)                               # A8
        if main_now:
            want = L.span(main_now[0])
            if want not in screen or main_now[0]["name"][:20] not in screen:
                bad.append({"assert": "A8", "product": main_now[0]["name"],
                            "session": tag, "step": step,
                            "detail": f"성과 줄에 1위 {want} 가 없다"})
        if st["answered"] != step:                                # A6
            bad.append({"assert": "A6", "product": "-", "session": tag, "step": step,
                        "detail": f"화면의 '답한 질문' {st['answered']} ≠ 실제 답한 수 {step}"})
        prev_left = st["left"]
        ordered = [(k, s) for k, s in C.rank_questions(scored) if k not in state]
        if not ordered:
            break
        key, slot = ordered[0]
        raw, kind = pick_answer(slot, rng, persona)
        if L.apply_answer(state, key, slot, raw, kind) == "bad":
            bad.append({"assert": "검사기", "product": "-", "session": tag, "step": step,
                        "detail": f"답을 못 넣었다: {key} ← '{raw}'"})
            break
    return bad


def run(stamp: str, group: str, term: int, seeds: int,
        company: str | None = None, kinds: str | None = None) -> dict:
    tax = C.load_tax()
    rows_all, by_pair = AB.load(stamp, group, term)
    if not rows_all:
        raise SystemExit(f"{term}개월 상품이 없다")
    rows = C.scope_rows(rows_all, company, kinds)
    if not rows:
        raise SystemExit(f"스코프에 맞는 상품이 없다 (기관={company} 상품군={kinds})")
    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    print(f"\n=== 화면 계약 전수 검사 · {group} {term}개월 · 스냅샷 {stamp} ===")
    print(f"상품 {len(rows)}개 · 전부 답하면 질문 {total}개 · "
          f"세션 {3 + seeds}개 (페르소나 3 + 시드 0~{seeds - 1})")
    if len(rows) < len(rows_all):
        print(f"스코프 기관={company} 상품군={kinds} — 카탈로그 {len(rows_all)}개 중 "
              f"{len(rows)}개. A7 도 검사한다")
    print("검사 대상 화면은 ask_loop.render_final_screen() — 중단하면 보는 그 화면이다\n")

    t0 = time.monotonic()
    bad, n_states = [], 0
    for persona in ("예", "아니오", "모름"):
        out = walk(rows, by_pair, plan, total, tax, persona=persona, rows_all=rows_all)
        n_states += max(s["step"] for s in out) + 1 if out else total + 1
        bad += out
        print(f"  페르소나 {persona:<4} 위반 {len(out)}건")
    for seed in range(seeds):
        bad += walk(rows, by_pair, plan, total, tax, seed=seed, rows_all=rows_all)
        if (seed + 1) % 50 == 0:
            print(f"  시드 {seed + 1:>3}/{seeds} 까지 · 누적 위반 {len(bad)}건 "
                  f"· {time.monotonic() - t0:.0f}초")

    print("\n" + "-" * 92)
    codes = {}
    for v in bad:
        codes.setdefault(v["assert"], []).append(v)
    for name, text in (("A1", "범위를 단일 숫자로 줄이지 않는다"),
                       ("A2", "확정 라벨은 폭이 0일 때만"),
                       ("A3", "사유 문장을 숨기지 않는다"),
                       ("A4", "남은 질문 수가 늘지 않는다"),
                       ("A5", "공시 최고금리 상한"),
                       ("A6", "'답한 질문' 이 실제 답한 수와 같다"),
                       ("A7", "스코프 밖 최고 금리를 보여준다"),
                       ("A8", "성과 줄이 1위 상품과 일치한다"),
                       ("A9", "가입 채널 표시가 원천과 일치한다")):
        hits = codes.get(name, [])
        mark = "통과" if not hits else f"**불통과 {len(hits)}건**"
        print(f"  {name}  {text:<34}{mark}")
        for v in hits[:3]:
            print(f"        {v['session']} 단계{v['step']} · {v['product']} · {v['detail']}")
        if len(hits) > 3:
            uniq = sorted({v["product"] for v in hits})
            print(f"        ... 그리고 {len(hits) - 3}건 더 (대상 {len(uniq)}종: "
                  f"{', '.join(uniq[:6])}{' 등' if len(uniq) > 6 else ''})")
    if codes.get("검사기"):
        print(f"  검사기 자체 오류 {len(codes['검사기'])}건 — 답을 못 넣은 자리다")
    print(f"\n  걸린 시간 {time.monotonic() - t0:.0f}초")
    return {"snapshot": stamp, "group": group, "term": term, "seeds": seeds,
            "questions_total": total, "products": len(rows),
            "violations": bad,
            "summary": {k: len(v) for k, v in sorted(codes.items())}}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, seeds = "bank", 12, SEEDS
    company, kinds = None, None
    for flag in ("--group", "--term", "--seeds", "--company", "--kind"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            v = argv[i + 1]
            group = v if flag == "--group" else group
            term = int(v) if flag == "--term" else term
            seeds = int(v) if flag == "--seeds" else seeds
            company = v if flag == "--company" else company
            kinds = v if flag == "--kind" else kinds
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/check_screen_contract.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--seeds 200]")
    report = run(argv[0], group, term, seeds, company, kinds)
    out = C.OUT_DIR / f"screen_contract_{group}_{argv[0]}_{term}m.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
