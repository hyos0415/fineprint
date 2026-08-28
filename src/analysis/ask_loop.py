# -*- coding: utf-8 -*-
"""되묻기 2단계 질문 루프 — 질문을 하나씩 던지고 답을 받는다.

이 파일이 채우는 자리
    `decisions/0024` 가 되묻기 흐름을 정의했고 계산기·상태바·`아니오` 경로까지 다
    들어갔는데, **질문을 하나씩 던지고 답을 받는 루프가 없었다.** 지금까지는
    `--state` 에 답을 미리 다 적어 넣는 방식이라 "사용자가 22개를 실제로 답하는가" 를
    확인할 수가 없었다. `design.md` §되묻기 흐름의 2단계가 여기서 처음 구현된다.

무엇을 재나 — `decisions/0024` 의 반증 조건 넷을 이 루프가 관측한다
    1. **어디서 그만두는가.** 22~27개 중간에 그만두면 P2(질문 수 제한 없음)가 틀렸다.
       그때는 상위 N개만 묻고 나머지를 `미응답` 사유로 내는 쪽을 본다
    2. **분모가 시작 자체를 막는가.** 0번째 질문 앞에서 그만두면 22개를 처음부터
       보여주는 것이 역효과다 → B안(2단계 분할)으로 돌아간다
    3. **"모르겠다" 비율이 절반을 넘는가.** 넘으면 질문이 답할 수 없는 형태라는 뜻이고
       P1(공시 문구 원문)을 다시 봐야 한다
    4. **확정 상품 수가 성과로 읽히는가.** 상태바 둘째 숫자가 제 일을 하는지다
    세션 로그(`ask_session_*.json`)에 질문마다 답·경과 시간·남은 수·확정 수를 남긴다.

돈은 안 든다. LLM 을 부르지 않는다 — 추출 결과를 읽어 계산만 한다.

사용법:
    python src/analysis/ask_loop.py 20260826 --group bank --term 12
    python src/analysis/ask_loop.py 20260826 --auto 예            # 사람 없이 전부 "예"
    python src/analysis/ask_loop.py 20260826 --answers 예,아니오,모름
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402

MAX_STEPS = 80          # 무한 루프 방어. 실제 질문 수는 은행권 22 · 저축은행 27 이다

# 답을 읽는 표 — 한글과 영문 약자를 둘 다 받는다.
# **약자를 넣은 이유는 콘솔 인코딩이다.** Windows 터미널에서 한글 입력이 깨지는 환경이
# 있는데, 그것 때문에 사용자가 답을 못 하면 루프 자체를 못 재게 된다.
YES = {"예", "네", "y", "yes", "o", "1"}
NO = {"아니오", "아니요", "n", "no", "x", "2"}
UNSURE_IN = {"모름", "모르겠다", "모르겠습니다", "u", "?", "3"}
QUIT = {"그만", "중단", "q", "quit", "exit"}
# 대본 모드(`--answers`) 전용 — 수치 질문에 "가장 높은 임계를 넘겨 답한다".
# 사람은 이런 답을 못 하지만, 대본으로 회귀를 돌릴 때 `ask_budget.py` 의 페르소나와
# 같은 답을 재현하려면 필요하다.
MAXOUT = {"최대", "max"}

MONEY_IN = re.compile(r"^(\d[\d,]*)\s*(억원|억|만원|만|천원|천|원)?$")
# 횟수 질문에 `"6회"` 처럼 단위를 붙여 답하는 것을 받는다 — 안 받으면 사용자가
# 화면의 임계 표기(`6회`)를 그대로 옮겨 적었을 때 거절당한다 (2026-08-28 실측)
COUNT_IN = re.compile(r"^(\d[\d,]*)\s*(회|건|명|개|일|좌|번)?$")


def parse_number(raw: str, unit: str) -> float | None:
    """`"50만원"` · `"6"` · `"6회"` · `"300,000"` 을 숫자로. 못 읽으면 None 이다."""
    if unit != "금액":
        m = COUNT_IN.match(raw.replace(" ", ""))
        return None if not m else float(int(m.group(1).replace(",", "")))
    m = MONEY_IN.match(raw.replace(" ", ""))
    if not m:
        return None
    n = float(int(m.group(1).replace(",", "")))
    suffix = (m.group(2) or "원").replace("억", "억원").replace("만", "만원")
    suffix = suffix.replace("천", "천원").replace("원원", "원")
    return n * C.MONEY_UNIT.get(suffix, 1)


def fmt_need(value: float, unit: str) -> str:
    if unit != "금액":
        return f"{value:,.0f}회"
    return f"{value / 10000:,.0f}만원" if value >= 10000 else f"{value:,.0f}원"


def span(s: dict) -> str:
    """**범위는 범위로 보여준다** — `design.md` 화면 계약 1번. 같을 때만 숫자 하나다."""
    if abs(s["net_hi"] - s["net_lo"]) < 1e-9:
        return f"{s['net_lo']:.2f}%"
    return f"{s['net_lo']:.2f}~{s['net_hi']:.2f}%"


def ranked(scored: list[dict]) -> list[dict]:
    """메인 층을 최대 금리 순으로 (`decisions/0017`). 정렬 규칙은 `calculate.main` 과 같다."""
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    return sorted(main, key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))


def product_line(i: int, s: dict, prev: list[str] | None = None) -> str:
    """상품 한 줄. **금리 옆에 남은 조건 수와 사유를 같이 놓는다** (화면 계약 1·4번).

    화면 계약 검사(`check_screen_contract.py`)가 **이 함수의 출력을 그대로** 읽는다.
    렌더가 한 곳에만 있어야 "화면에서 과대 진술이 된다" 를 코드로 막을 수 있다.
    """
    move = ""
    if prev is not None:
        was = prev.index(s["code"]) + 1 if s["code"] in prev else None
        if was is None:
            move = " NEW"
        elif was != i:
            move = f" {was}->{i}"
    if s["net_hi"] > s["net_lo"]:
        left = f"남은 {s['n_unknown']}개"
    elif s["n_unknown"]:
        left = f"남은 {s['n_unknown']}개 (금리 영향 없음)"
    else:
        left = "확정"
    note = ("  주의:" + "·".join(s["caveats"])) if s.get("caveats") else ""
    return f"  {i:>2}. {s['name'][:24]:<25}{span(s):>15}  {left:<22}{move}{note}"


def show_list(items: list[dict], top: int | None, prev: list[str] | None = None) -> None:
    for line in [product_line(i, s, prev) for i, s in enumerate(items[:top], 1)]:
        print(line)


def status_lines(plan: dict, state: dict, scored: list[dict],
                 total: int) -> tuple[list[str], dict]:
    """상태바 — 숫자 둘을 나란히 (`decisions/0024` P4).

    진행만 보여주면 "모르겠다" 가 "아니오" 와 똑같이 진전으로 보인다. 둘 다 질문을
    지우는데 "모르겠다" 는 금리를 하나도 좁히지 못한다. 확정 상품 수가 그 차이를 가른다.
    """
    left = C.questions_left(plan, state)
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    fixed = sum(1 for s in main if s["tier"] == "확정")
    done = total - left
    bar_w = 32
    filled = 0 if not total else round(done / total * bar_w)
    lines = [f"\n  진행  [{'#' * filled}{'.' * (bar_w - filled)}]  "
             f"답한 질문 {done}/{total} · 남은 질문 {left}개",
             f"  성과  금리가 정해진 상품 {fixed}/{len(main)}개"]
    return lines, {"left": left, "done": done, "fixed": fixed, "main": len(main),
                   "top1": main and ranked(scored)[0]["net_hi"] or 0.0}


def status_bar(plan: dict, state: dict, scored: list[dict], total: int) -> dict:
    lines, st = status_lines(plan, state, scored, total)
    for line in lines:
        print(line)
    return st


# 사유 문장을 두 블록으로 나눠 **전부** 보여준다 (`decisions/0016` · `prereg-09` A3)
#
# 처음에는 아래 `HARD` 여섯 개만 문장으로 냈고, `미응답`·`수치필요`는 상품 줄의 코드
# (`주의:미응답`)와 `남은 N개` 로만 나갔다. **화면 계약 검사가 그걸 A3 위반으로 잡았고**
# 사람이 "문장도 보여준다" 를 골랐다 — `0019` 의 부산은행이 정확히 "코드는 있는데
# 사용자가 못 읽은" 자리였다.
#
# 두 블록으로 가르는 이유는 `CAVEAT` 자체가 두 종류이기 때문이다 — 답하면 없어지는
# 것과 되물어도 안 없어지는 것을 한 제목 아래 놓으면 사용자가 무엇을 할 수 있는지
# 알 수 없다.
ASKABLE_CAVEATS = ("미응답",)      # `수치필요` 는 `prereg-10` 에서 사라졌다
HARD_CAVEATS = ("조건불명", "중복우대불명", "추첨", "단계불명", "모름", "이행필요")


def render_final_screen(scored: list[dict], plan: dict, state: dict, total: int,
                        top: int | None) -> tuple[str, dict]:
    """**중단하거나 끝냈을 때 사용자가 보는 화면 전체**를 문자열로 만든다.

    루프의 3단계가 이 함수를 출력하고, 화면 계약 검사가 **같은 함수**를 모든 중간
    상태에 대해 읽는다. 사용자가 12번째 질문에서 그만두면 보는 것이 정확히 이 화면이다.
    """
    main = ranked(scored)
    rest = [s for s in scored if s["tier"] not in C.MAIN_TIERS]
    lines = [product_line(i, s) for i, s in enumerate(main[:top], 1)]
    bar, st = status_lines(plan, state, scored, total)
    lines += bar
    if rest:
        tally = {t: sum(1 for x in rest if x["tier"] == t) for t in
                 {s["tier"] for s in rest}}
        lines.append(f"\n  메인 밖 {len(rest)}개 — "
                     + " · ".join(f"{t} {n}" for t, n in sorted(tally.items())))
    shown = {c for s in main for c in s.get("caveats", [])}
    for header, codes in (("답하면 없어지는 사유", ASKABLE_CAVEATS),
                          ("되물어도 못 채우는 사유", HARD_CAVEATS)):
        hit = [c for c in codes if c in shown]
        if hit:
            lines.append(f"\n  {header} — 이 문장을 사용자에게 보여준다")
            for c in hit:
                lines.append(f'    {c:<10}"{C.CAVEAT[c]}"')
    return "\n".join(lines), st


def prompt_for(key: str, slot: dict) -> tuple[str, list[str]]:
    """질문 한 개를 화면 문장으로.

    **문구 질문은 공시 문구가 질문 문장 자체다** (`prereg-10`). 임계가 붙은 조건에
    "금액이 얼마입니까" 를 물으면, 한 유형 아래 대상이 다른 문구가 섞여 있어 답이
    존재하지 않는다 — 적립식예금 잔액·펀드 보유액·정기예금 가입액은 같은 축이 아니다.
    문구를 그대로 묻고 예/아니오/모름을 받으면 사용자는 자기 상황을 대조만 하면 된다.

    문구를 **자르지 않는다.** 질문 문장을 자르면 조건이 달라진다.
    """
    if "#" in key:                             # 문구 단위 질문
        ev = sorted(slot["evidence"])[0] if slot["evidence"] else "(문구 없음)"
        head = f'"{ev}"'
        lines = [f"      위는 공시 문구 원문입니다 — 충족하십니까? "
                 f"(조건 유형 {slot['kind']})"]
    else:                                      # 조건 유형 질문
        head = f"{key} — 이 조건을 충족하십니까?"
        lines = [f'      공시 문구  "{ev[:74]}"' for ev in sorted(slot["evidence"])[:3]]
    return head, lines + ["      [예] [아니오] [모름] · [그만]"]


def bad_answer_hint(slot: dict, kind: str) -> str:
    """못 읽은 답에 **무엇이 문제인지** 말해준다.

    옛 메시지는 `"[예] [아니오] [모름] 또는 숫자를 입력하세요"` 였는데 수치 질문에서
    `예` 는 유효한 답이 아니었다 — **메시지가 거짓이었다.** 실측 세션에서 사용자가 `예` 를
    세 번 넣고 같은 거절을 세 번 받은 뒤 사실과 다른 `아니오` 로 답했다(`prereg-09` §8).
    `prereg-10` 이 수치 질문 자체를 없앴으므로 이제 답은 셋뿐이다.
    """
    if kind == "number":
        return ("      숫자로는 판정하지 않습니다 — 위 문구를 충족하시는지 "
                "[예] [아니오] [모름] 으로 답해 주세요")
    return "      못 읽었습니다. [예] [아니오] [모름] 중에서 입력하세요"


def read_answer(scripted: list[str] | None, auto: str | None,
                slot: dict) -> tuple[str, str]:
    """(원문, 종류). 종류는 yes·no·unsure·quit·number·bad 다.

    `number` 는 **오답 안내용**으로만 남긴다 — `prereg-10` 뒤로 수치 질문이 없으므로
    숫자를 넣은 사용자에게 "문구에 예/아니오로 답해 주세요" 라고 말해야 한다.
    숫자를 조용히 "예" 로 받으면 사용자가 하지 않은 답을 우리가 만든 것이 된다.
    """
    if auto:                                   # 사람 없이 도는 모드 — 회귀 확인용
        return {"예": ("예", "yes"), "아니오": ("아니오", "no"),
                "모름": ("모름", "unsure")}[auto]
    if scripted is not None:
        if not scripted:
            return "", "quit"                  # 답이 떨어지면 중단으로 기록한다
        raw = scripted.pop(0)
    else:
        try:
            raw = input("      > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "", "quit"
    low = raw.lower()
    if low in QUIT:
        return raw, "quit"
    if low in MAXOUT or low in YES:            # `최대` 는 옛 대본 호환 — 이제 그냥 예다
        return raw, "yes"
    if low in NO:
        return raw, "no"
    if low in UNSURE_IN:
        return raw, "unsure"
    if parse_number(raw, "횟수") is not None or parse_number(raw, "금액") is not None:
        return raw, "number"                   # 숫자다 — 위 안내 문장으로 되묻는다
    return raw, "bad"


def apply_answer(state: dict, key: str, slot: dict, raw: str, kind: str) -> str:
    """답을 상태에 넣는다. 넣은 답의 종류를 돌려준다.

    `prereg-10` 뒤로 유형 질문과 문구 질문이 **같은 모양**이다 — 셋 중 하나로 답하고,
    유형에 "아니오"·"모름" 이면 그 유형의 문구 질문이 전부 사라진다(`0024` P4).
    """
    if kind == "yes":
        state[key] = True
    elif kind == "no":
        state[key] = False
    elif kind == "unsure":
        state[key] = C.UNSURE
    else:
        return "bad"
    return kind


def run(stamp: str, group: str, term: int, top: int,
        scripted: list[str] | None, auto: str | None) -> dict:
    tax = C.load_tax()
    rows, by_pair = AB.load(stamp, group, term)
    if not rows:
        raise SystemExit(f"{term}개월 상품이 없다. --term 을 바꿔본다")
    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    state: dict = {}
    steps: list[dict] = []

    print(f"\n=== 되묻기 질문 루프 · {group} {term}개월 · 스냅샷 {stamp} ===")
    print(f"상품 {len(rows)}개 · 전부 답하면 질문 {total}개입니다. "
          f"언제든 '그만' 을 입력하면 멈춥니다.")
    print("\n■ 1단계 — 아무것도 묻지 않은 첫 화면 (조건을 다 채웠을 때 순)")
    scored = AB.score_all(rows, by_pair, state, tax)
    show_list(ranked(scored), top)
    st = status_bar(plan, state, scored, total)
    start_top1 = st["top1"]
    print("\n" + "-" * 92)
    print("■ 2단계 — 질문 루프. 커버리지가 큰 질문부터 묻습니다 (decisions/0018 고정 순서)")

    quit_at, quit_why, tick = None, "", time.monotonic()
    for step in range(1, MAX_STEPS + 1):
        ordered = [(k, s) for k, s in C.rank_questions(scored) if k not in state]
        if not ordered:
            break
        key, slot = ordered[0]
        head, lines = prompt_for(key, slot)
        print(f"\n  [{step}] {head}")
        print(f"      이 답 하나가 상품 {len(slot['codes'])}개의 판정을 엽니다")
        for line in lines:
            print(line)
        while True:
            raw, kind = read_answer(scripted, auto, slot)
            if kind == "quit":
                quit_at = step
                quit_why = ("대본이 떨어졌다" if scripted is not None and not scripted
                            else "사용자가 그만뒀다")
                break
            given, kind = kind, apply_answer(state, key, slot, raw, kind)
            if kind != "bad":
                break
            print(bad_answer_hint(slot, given))
            if scripted is not None or auto:
                quit_at, quit_why = step, f"읽을 수 없는 답 '{raw}'"   # 사람이 없으면 못 되묻는다
                break
        if quit_at:
            break
        prev = [s["code"] for s in ranked(scored)]
        scored = AB.score_all(rows, by_pair, state, tax)
        print(f"\n      → '{raw}' 로 받았습니다")
        show_list(ranked(scored), 3, prev)
        st = status_bar(plan, state, scored, total)
        steps.append({"step": step, "key": key, "kind": slot["kind"],
                      "unit": slot["unit"], "products": len(slot["codes"]),
                      "answer_kind": kind, "answer": raw,
                      "seconds": round(time.monotonic() - tick, 1), **st})
        tick = time.monotonic()

    print("\n" + "-" * 92)
    print("■ 3단계 — 결과")
    scored = AB.score_all(rows, by_pair, state, tax)
    screen, st = render_final_screen(scored, plan, state, total, top)
    print(screen)

    # ── 반증 조건 확인 (`decisions/0024`)
    n_unsure = sum(1 for s in steps if s["answer_kind"] == "unsure")
    print("\n" + "-" * 92)
    print("질문 루프 결과 — decisions/0024 반증 조건 확인용")
    if quit_at:
        print(f"    중단        {len(steps)}개 답하고 {quit_at}번째 질문에서 멈췄다"
              f" (남은 질문 {st['left']}개) — {quit_why}")
        print("    → P2(질문 수 제한 없음)가 흔들린다. 어디서 그만뒀는지가 로그에 있다")
        if not steps:
            print("    → 0번째에서 그만뒀다. 분모 "
                  f"{total}개가 시작을 막은 것인지 확인해야 한다 (반증 조건 2)")
    else:
        print(f"    완주        질문 {len(steps)}개를 전부 답했다")
    if steps:
        ratio = n_unsure / len(steps) * 100
        mark = "  <- 절반을 넘었다. P1(공시 문구 원문)을 다시 본다" if ratio > 50 else ""
        print(f"    모르겠다     {n_unsure}/{len(steps)} ({ratio:.1f}%){mark}")
        secs = [s["seconds"] for s in steps]
        print(f"    답한 시간    합계 {sum(secs):.0f}초 · 질문당 중앙값 "
              f"{sorted(secs)[len(secs) // 2]:.1f}초")
    print(f"    확정 상품    {st['fixed']}/{st['main']}개")
    print(f"    1위 금리     {start_top1:.2f}% → {st['top1']:.2f}% "
          f"(되묻기가 깎은 폭 {start_top1 - st['top1']:.2f}%p)")
    return {"snapshot": stamp, "group": group, "term": term,
            "started": datetime.now().isoformat(timespec="seconds"),
            "questions_total": total, "mode": auto or ("scripted" if scripted is not None
                                                       else "interactive"),
            "quit_at": quit_at, "quit_why": quit_why, "answered": len(steps), "unsure": n_unsure,
            "state": {k: v for k, v in state.items()}, "steps": steps,
            "final": st, "top1_start": start_top1}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, top, auto, answers = "bank", 12, 10, None, None
    for flag in ("--group", "--term", "--top", "--auto", "--answers"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            v = argv[i + 1]
            group = v if flag == "--group" else group
            term = int(v) if flag == "--term" else term
            top = int(v) if flag == "--top" else top
            auto = v if flag == "--auto" else auto
            answers = v if flag == "--answers" else answers
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/ask_loop.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--top 10] "
                         "[--auto 예|아니오|모름] [--answers 예,아니오,모름]")
    if auto and auto not in ("예", "아니오", "모름"):
        raise SystemExit("--auto 는 예 · 아니오 · 모름 중 하나다")
    scripted = [a.strip() for a in answers.split(",")] if answers else None
    stamp = argv[0]
    log = run(stamp, group, term, top, scripted, auto)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = C.OUT_DIR / f"ask_session_{group}_{stamp}_{term}m_{ts}.json"
    out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
