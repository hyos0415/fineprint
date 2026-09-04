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
    python src/analysis/ask_loop.py 20260826 --answers "국민은행|신한은행,예,예"   # 목록 답
    python src/analysis/ask_loop.py 20260826 --company 우리 --kind 적금   # 후보 집합
    python src/analysis/ask_loop.py 20260826 --prefs 확실성=많이         # 선호 가중치
    python src/analysis/ask_loop.py 20260826 --survey                  # 설문 문항만 본다
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
import view as V  # noqa: E402  — 뷰 모델. `view` 는 `ask_loop` 을 함수 안에서만 부른다
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402

# 무한 루프 방어. **F6 이 이 값을 넘겼다** — 조건을 기관별로 가르니 "전 기관과
# 거래한다" 는 페르소나의 질문이 은행권 84개가 되어, 옛 값 80 에서 루프가 잘렸는데
# 화면은 **"완주"** 라고 적었다(남은 질문 4개인 채로). 방어값이 지표를 조용히
# 바꾸는 자리였다. 실측 상한은 은행권 90 · 저축은행 45 다
MAX_STEPS = 400

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


# ── 목록 질문의 답 (F6 · `prereg-15`)
#
# **답 셋(예/아니오/모름)의 유일한 예외다** (`0027`). 기관 상대 조건을 기관마다
# 예/아니오로 물으면 은행권에서 56개가 되는데, 목록 하나로 물으면 안 고른 기관이
# 전부 유도되어 거래 은행 1곳 사용자는 16개로 끝난다.
#
# **"모름" 은 남긴다.** 목록을 안 고르면 유도가 안 걸리고 기관 상대 조건이 기관마다
# 질문으로 나간다 — 질문은 늘지만 우리가 사용자 대신 정하지는 않는다(`0016`).
NONE_IN = {"없음", "없다", "-", "0", "none"}


def parse_banks(raw: str, banks: list[str]) -> list[str] | None:
    """`"1,3"` · `"국민은행|케이뱅크"` · `"없음"` 을 기관 목록으로. 못 읽으면 None.

    번호와 이름을 둘 다 받는다 — 번호는 한글 입력이 깨지는 콘솔을 위한 것이고
    (`YES`/`NO` 약자와 같은 이유), 이름은 화면에서 그대로 옮겨 적는 사용자를 위한 것이다.

    **구분자로 `|` 도 받는다.** `--answers` 가 이미 쉼표로 답을 가르기 때문에, 대본으로
    기관 여럿을 주려면 쉼표가 아닌 구분자가 하나 필요하다 — 없으면 대본이 목록 질문에
    한 곳만 줄 수 있고 회귀를 그 경로로 못 돌린다.
    """
    text = raw.strip().replace("|", ",")
    if text.lower() in NONE_IN:
        return []
    out: list[str] = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit():
            i = int(tok)
            if not 1 <= i <= len(banks):
                return None
            pick = banks[i - 1]
        else:
            hit = [b for b in banks if b == tok] or [b for b in banks if tok in b]
            if len(hit) != 1:
                return None            # 없거나 여럿이면 **추측하지 않는다**
            pick = hit[0]
        if pick not in out:
            out.append(pick)
    return out


def fmt_need(value: float, unit: str) -> str:
    if unit != "금액":
        return f"{value:,.0f}회"
    return f"{value / 10000:,.0f}만원" if value >= 10000 else f"{value:,.0f}원"


# 화면 맨 위 두 줄. **문자열을 여기 한 곳에 두고 검사기가 같은 상수를 읽는다** —
# 렌더와 검사가 따로 문구를 갖고 있으면 한쪽만 고쳐도 통과한다.
#
# `NOTICE` 는 **A안**이다 (이슈 #31 · `0035`) — 우리는 금융상품판매업자가 아니고,
# 법 §22① 이 판매업자등이 아닌 자의 "광고" 를 금지한다. 그래서 이 화면이 무엇인지를
# 화면 안에서 말한다. **법적 판정을 우리가 내리지 않는다** — "광고가 아니다" 라고
# 선언하는 대신 **우리가 하는 일과 안 하는 일**을 적는다. 그게 사실이고, 판정은
# 사실 위에서 남이 한다.
#
# `tax_label` 은 **B안**이다 — 공정위 예규 「금융상품 등의 표시·광고에 관한 심사지침」
# Ⅴ.1.마 가 *"수익률(이자율) 표기시 '세전'인지 '세후'인지를 누락하여 표시·광고하는
# 것은 부당한 표시·광고에 해당할 수 있다"* 고 적는다. 우리는 규제 적용 대상인지가
# 아직 안 갈렸지만(#31) **판매업자에게 요구되는 수준을 그대로 지킨다**.
#
# **`calculate.py` 목록에는 헤더에 `세후`·`세전` 이 있었는데 이 화면에는 없었다**
# (2026-08-31 · `0035`). 그리고 사용자가 실제로 보는 것은 이 화면이다.
NOTICE = C.NOTICE          # 사본을 두지 않는다 — 문구는 `calculate` 에 하나뿐이다


def tax_label(scored: list[dict]) -> str:
    """세후 라벨. **세율을 문자열에 박지 않고 계산에 쓴 값을 그대로 읽는다.**

    `config/tax-2026.json` 이 바뀌면 이 줄도 같이 바뀐다 — 우리가 손으로 적은
    `15.4%` 가 config 와 어긋나는 자리를 만들지 않는다(`0032` 가 세율을 조문에
    핀으로 박은 것과 같은 이유다).
    """
    rates = {s.get("tax_rate", 0.0) for s in scored}
    if len(rates) != 1:                     # 상품별로 세율이 갈리면 뭉뚱그리면 안 된다
        return "금리는 모두 세후입니다 — 세율이 상품마다 다릅니다"
    r = rates.pop()
    if r <= 1e-9:
        return "금리는 모두 세후입니다 — 비과세 대상이라 세금 0%"
    return f"금리는 모두 세후입니다 — 이자소득세 등 {r * 100:.1f}% 를 뗀 값입니다"


def screen_header(scored: list[dict]) -> list[str]:
    """화면 맨 위 두 줄 — 화면 계약 A12(세후 라벨) · A13(성격 고지)."""
    return [f"  {tax_label(scored)}", f"  {NOTICE}"]


def span_of(lo: float, hi: float) -> str:
    """값 두 개로 범위 문자열. **상태바는 상품 dict 가 아니라 사실만 보고 만든다**
    (F4-0 · 이슈 #36) — 그래야 웹 렌더러도 같은 문자열을 만들 수 있다."""
    if abs(hi - lo) < 1e-9:
        return f"{lo:.2f}%"
    return f"{lo:.2f}~{hi:.2f}%"


def span(s: dict) -> str:
    """**범위는 범위로 보여준다** — `design.md` 화면 계약 1번. 같을 때만 숫자 하나다."""
    return span_of(s["net_lo"], s["net_hi"])


def ranked(scored: list[dict], prefs: dict | None = None,
           order: str = "hi") -> list[dict]:
    """메인 층을 줄 세운다 (`decisions/0017`). 규칙은 `prefs.sorter()` 한 곳에 있다.

    **`prefs` 를 주면 세후 가중합 순이 된다** (`prereg-12` §3 · 이슈 #24). 안 주면
    조정이 전부 0 이라 `net_hi` 순과 **소수점까지 같다** — 기본값을 우리가 정하지
    않는 자리다(`0024` P2).
    """
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    P.annotate(main, prefs or {})
    return sorted(main, key=P.sorter(order, prefs))


def product_line(i: int, s: dict, prev: list[str] | None = None) -> str:
    """상품 한 줄. **금리 옆에 남은 조건 수와 사유를 같이 놓는다** (화면 계약 1·4번).

    화면 계약 검사(`check_screen_contract.py`)가 **이 함수의 출력을 그대로** 읽는다.
    렌더가 한 곳에만 있어야 "화면에서 과대 진술이 된다" 를 코드로 막을 수 있다.
    """
    move = ""
    if prev is not None:
        # 화살표가 가리키는 것은 **이 줄**이다 — 같은 상품의 단리·복리가 각각
        # 한 줄이므로 `code` 로 찾으면 남의 줄을 가리킨다 (`prereg-13`).
        me = C.row_key(s)
        was = prev.index(me) + 1 if me in prev else None
        if was is None:
            move = " NEW"
        elif was != i:
            move = f" {was}->{i}"
    # **표시 결정은 `view.display()` 가 한다** (F4-2) — 웹 템플릿도 같은 것을 읽는다.
    # 여기서 따로 정하면 CLI 와 웹이 서로 다른 말을 하게 된다(`0035` 가 찾은 실패)
    d = V.display(s)
    left = d["남은"]
    note = ("  주의:" + "·".join(d["주의"])) if d["주의"] else ""
    # 가입 채널 — 편의성 축 1번(이슈 #22). 선호 가중치(#24)가 들어오기 전까지는 표시만
    # 했다. 지금은 사용자가 `--prefs 영업점=...` 을 준 **그때만** 점수에 들어간다 —
    # 우리가 정한 값이 아니다(`problem.md` §6 · `0024` P2).
    ch = f"  [{d['채널']}]" if d["채널"] else ""
    # 선호 조정 — **금리 칸이 아니라 별도 칸이다.** 점수를 금리처럼 보여주면 공시에
    # 없는 숫자를 사용자에게 보여주는 것이다 (`prereg-12` §3 · 화면 계약 A11).
    adj = f"  {d['조정']}" if d["조정"] else ""
    line = (f"  {i:>2}. {s['name'][:24]:<25}{d['범위']:>15}{ch:<16}{left:<22}"
            f"{adj}{move}{note}")
    # 같은 상품의 다른 행 (`prereg-18` §2.3 · A16) — 웹도 같은 문자열을 그린다
    lines = [line] + [f"      └ {v}" for v in d["다른_행"]]
    # 기관 홈페이지·대표전화 (F3 · A17) — 웹의 `href`·`tel:` 과 **같은 칸**을 읽는다. 있는 것만
    # 적고 없는 칸은 비운다(`prereg-20` §4). 여기서 "은행에 확인해 보세요" 가 갈 곳을 얻는다
    contact = " · ".join(x for x in (d["홈페이지"], d["전화"]) if x)
    if contact:
        lines.append(f"      ↳ {contact}")
    return "\n".join(lines)


def show_list(items: list[dict], top: int | None, prev: list[str] | None = None) -> None:
    for line in [product_line(i, s, prev) for i, s in enumerate(items[:top], 1)]:
        print(line)


def status_facts(plan: dict, state: dict, scored: list[dict], total: int,
                 start: dict | None = None, prefs: dict | None = None,
                 order: str = "hi") -> dict:
    """상태바가 말하는 **사실**만 만든다 — 문자열을 만들지 않는다 (F4-0 · 이슈 #36).

    렌더와 사실을 가르는 이유는 웹이다. 화면 계약 A4·A6 은 이미 이 dict 를 읽고
    있었는데(`st`), 나머지 계약은 렌더된 문자열을 grep 하고 있었다. 웹 렌더러가
    생기면 그쪽이 무의미해지므로 **사실을 먼저 꺼낸다**(`ui-plan.md` F4-0).

    **"답한 질문" 은 실제로 답한 수다.** 옛 화면은 `전체 - 남은` 을 답한 수로 표시해
    11개 답한 사람에게 "22개" 라고 말했다 — 거짓이었다(`calculate.questions_answered`).
    줄어드는 것은 **전체(분모)** 다.

    **성과는 "내 금리 범위" 다** (`0029`). `0024` P4 는 확정 상품 수를 성과로 놨는데,
    사람 세션에서 *"진행 바밖에 안 보인다"* 가 나왔다 — 후보 4개짜리 스코프에서는
    확정 수가 6개 질문 동안 **0으로 고정**돼 있었다(폭은 1.18 → 0.51 로 움직였다).
    확정 수는 후보 집합 크기에 종속이고, 범위 폭은 그렇지 않다.

    **확정 수를 버리지는 않는다** — "모르겠다" 와 "아니오" 를 가르는 유일한 숫자라
    부 지표로 남긴다.
    """
    left = C.questions_left(plan, state)
    answered = C.questions_answered(plan, state)
    now_total = answered + left
    main = [s for s in scored if s["tier"] in C.MAIN_TIERS]
    fixed = sum(1 for s in main if s["tier"] == "확정")
    # **1위는 화면 목록의 1위여야 한다** — 선호가 걸리면 목록 순서가 바뀌므로 여기도
    # 같은 정렬을 써야 한다. 안 그러면 화면 계약 A8(성과 줄 = 1위 상품)이 깨진다
    top = ranked(scored, prefs, order)[0] if main else None
    return {"left": left, "answered": answered, "total_now": now_total,
            "done": answered, "fixed": fixed, "main": len(main),
            "top1": top["net_hi"] if top else 0.0,
            "top1_lo": top["net_lo"] if top else 0.0,
            "top1_name": top["name"] if top else "",
            "width": round(top["net_hi"] - top["net_lo"], 4) if top else 0.0,
            # 성과 줄의 낱말. **선호가 걸리면 1위가 최고 금리가 아니다** (`0030`)
            "성과_라벨": ("1위" if prefs else
                       # `lo` 로 세우면 1위는 **최고 금리가 아니다** — 확정 금리가
                       # 가장 높은 상품이다. 낱말이 그것을 말해야 한다(`0030`)
                       "확실히 받는 것 중 최고" if order == "lo" else "최고"),
            "폭_시작": (start or {}).get("width"),
            "처음_총": total}


def status_lines(plan: dict, state: dict, scored: list[dict], total: int,
                 start: dict | None = None,
                 prefs: dict | None = None,
                 order: str = "hi") -> tuple[list[str], dict]:
    """상태바 — 진행 · 성과(내 금리 범위) · 확정 수 (`0024` P4 → `0029` 개정).

    **사실은 `status_facts()` 가 만들고 여기서는 그리기만 한다** (F4-0). 그래서 이
    함수는 `st` 밖의 값을 읽지 않는다 — 웹 렌더러가 같은 `st` 로 같은 말을 할 수 있다.
    """
    st = status_facts(plan, state, scored, total, start, prefs, order)
    bar_w = 32
    filled = 0 if not st["total_now"] else round(st["answered"] / st["total_now"] * bar_w)
    shrunk = (f"  (전체 {total}→{st['total_now']}개)"
              if st["total_now"] < total else "")
    lines = [f"\n  진행  [{'#' * filled}{'.' * (bar_w - filled)}]  "
             f"답한 질문 {st['answered']}/{st['total_now']}개 · "
             f"남은 질문 {st['left']}개{shrunk}"]
    if st["top1_name"]:
        # 성과 — 사용자가 실제로 얻는 것. A8 이 이 줄과 상품 목록의 일치를 검사한다.
        # **말 한 단어가 거짓말을 만든다** — 실측으로 우리은행 스코프에서 1위가 2.88%
        # 인데 목록 3위가 3.26% 였다(`0030`). 그래서 라벨도 사실로 취급해 `st` 에 둔다
        moved = ""
        if st["폭_시작"] is not None and abs(st["폭_시작"] - st["width"]) > 1e-9:
            moved = f"  (폭 {st['폭_시작']:.2f} → {st['width']:.2f}%p)"
        span_txt = span_of(st["top1_lo"], st["top1"])
        lines.append(f"  성과  {st['성과_라벨']} {span_txt}  "
                     f"{st['top1_name'][:20]}{moved}")
        lines.append(f"        금리가 정해진 상품 {st['fixed']}/{st['main']}개")
    return lines, st


def status_bar(plan: dict, state: dict, scored: list[dict], total: int,
               start: dict | None = None, prefs: dict | None = None) -> dict:
    lines, st = status_lines(plan, state, scored, total, start, prefs)
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
HARD_CAVEATS = ("조건불명", "중복우대불명", "추첨", "단계불명", "모름", "이행필요", "뜻없음")


def render_final_screen(scored: list[dict], plan: dict, state: dict, total: int,
                        top: int | None, outside: dict | None = None,
                        total_all: int | None = None,
                        start: dict | None = None,
                        prefs: dict | None = None,
                        order: str = "hi") -> tuple[str, dict]:
    """**중단하거나 끝냈을 때 사용자가 보는 화면 전체**를 문자열로 만든다.

    루프의 3단계가 이 함수를 출력하고, 화면 계약 검사가 **같은 함수**를 모든 중간
    상태에 대해 읽는다. 사용자가 12번째 질문에서 그만두면 보는 것이 정확히 이 화면이다.

    **뷰 모델을 거쳐 그린다** (F4-0 · 이슈 #36). 이 함수가 직접 `scored` 를 뒤지지
    않고 `view.build()` 가 모은 것만 읽는다 — 웹 렌더러가 **같은 뷰 모델**을 받으므로,
    여기서 그리는 것과 웹에서 그리는 것이 같은 사실 위에 선다. 뷰 모델이 칸을 빠뜨리면
    `view.check_model()` 이, 그려야 할 것을 안 그리면 화면 계약 검사가 잡는다.
    """
    import view as V

    vm = V.build(scored, plan, state, total, top, outside, total_all, start, prefs,
                 order)
    st = vm["progress"]
    # A12·A13 — 세후 라벨과 성격 고지는 **금리보다 위**에 둔다 (`0035`)
    lines = [f"  {vm['meta']['세후_라벨']}", f"  {vm['meta']['고지']}"]
    lines += [product_line(i, s) for i, s in enumerate(vm["products"], 1)]
    lines += status_lines(plan, state, scored, total, start, prefs, order)[0]
    # A10 — 옮긴 가중치를 전부 보여주고 고치는 방법을 적는다 (`problem.md` §3)
    lines += P.lines(prefs or {}, vm["prefs"]["막힌_상품"])
    if vm["메인밖"]["수"]:
        # **`메인 밖` 은 우리 말이었다** (F5 · 이슈 #45). 층 이름도 라벨로 낸다
        tally = vm["메인밖"]["층별"]
        lines.append(f"\n  계산할 수 없는 상품 {vm['메인밖']['수']}개 — "
                     + " · ".join(f"{C.tier_label(t)} {n}"
                                  for t, n in sorted(tally.items())))
    out = vm["notices"]["스코프밖"]
    if out:                                        # A7 — 좁히는 대가를 숨기지 않는다
        wider = ("" if vm["notices"]["넓히면_질문"] is None
                 else f" · 넓히면 질문이 {vm['notices']['넓히면_질문']}개로 늘어납니다")
        lines.append(f"\n  ⚠ 지금 고른 범위 밖에 {out['net_hi']:.2f}% 가 있습니다 "
                     f"({out['company']} {out['name'][:22]} · "
                     f"+{out['gap']:.2f}%p · [{out['channel']}] · "
                     f"조건 다 채웠을 때){wider}")
    shown = {r["코드"] for r in vm["notices"]["사유"]}
    for header, codes in (("답하면 없어지는 것", ASKABLE_CAVEATS),
                          ("답해도 못 채우는 것", HARD_CAVEATS)):
        hit = [c for c in codes if c in shown]
        if hit:
            lines.append(f"\n  {header}")
            for c in hit:
                # 코드가 아니라 라벨을 앞에 세운다 (F5) — 코드는 로그·검사가 쓴다
                lines.append(f'    {C.caveat_label(c):<20}"{C.CAVEAT[c]}"')
    return "\n".join(lines), st


def prompt_for(key: str, slot: dict) -> tuple[str, list[str]]:
    """질문 한 개를 화면 문장으로.

    **문구 질문은 공시 문구가 질문 문장 자체다** (`prereg-10`). 임계가 붙은 조건에
    "금액이 얼마입니까" 를 물으면, 한 유형 아래 대상이 다른 문구가 섞여 있어 답이
    존재하지 않는다 — 적립식예금 잔액·펀드 보유액·정기예금 가입액은 같은 축이 아니다.
    문구를 그대로 묻고 예/아니오/모름을 받으면 사용자는 자기 상황을 대조만 하면 된다.

    문구를 **자르지 않는다.** 질문 문장을 자르면 조건이 달라진다.
    """
    # **웹과 같은 카드를 읽는다** (`0039` 반증 조건 1 — 한쪽만 쓰는 칸을 만들지 않는다).
    # 그래서 기관도, 질문 문장도 여기 같이 나온다
    card = V.question_card(key, slot)
    문구 = card["문구"] if card else []

    if card and card["다중"]:                       # 목록 질문 (F6)
        banks = card["선택지"]
        lines = [f"      {card['설명']}"]
        for i, b in enumerate(banks, 1):
            lines.append(f"      {i:>2}. {b}")
        # 버튼 라벨은 웹과 같은 것을 읽는다 (이슈 #48) — 한쪽만 쓰는 낱말을 안 만든다
        라벨 = {b["값"]: b["라벨"] for b in card["버튼"]}
        lines.append(f"      번호나 이름을 쉼표로 여럿 · [없음] {라벨['없음']} · "
                     f"[모름] {라벨['모름']} · [그만]")
        return card["질문"], lines

    def _quote(f: dict, cut: int | None = None) -> str:
        """기관 — 문구. 기관이 없으면 문구만."""
        ev = f["문구"][:cut] if cut else f["문구"]
        return f'{f["기관"]} — "{ev}"' if f["기관"] else f'"{ev}"'

    if "#" in key:                             # 문구 단위 질문
        head = _quote(문구[0]) if 문구 else "(문구 없음)"
        lines = [f"      {card['질문']}"]
    else:                                      # 조건 유형 질문
        head = card["질문"]
        lines = [f"      공시 문구  {_quote(f, 74)}" for f in 문구[:3]]
    return head, lines + ["      [예] [아니오] [모름] · [그만]"]


def bad_answer_hint(slot: dict, kind: str) -> str:
    """못 읽은 답에 **무엇이 문제인지** 말해준다.

    옛 메시지는 `"[예] [아니오] [모름] 또는 숫자를 입력하세요"` 였는데 수치 질문에서
    `예` 는 유효한 답이 아니었다 — **메시지가 거짓이었다.** 실측 세션에서 사용자가 `예` 를
    세 번 넣고 같은 거절을 세 번 받은 뒤 사실과 다른 `아니오` 로 답했다(`prereg-09` §8).
    `prereg-10` 이 수치 질문 자체를 없앴으므로 이제 답은 셋뿐이다.
    """
    if slot.get("unit") == C.LIST_UNIT:
        return ("      못 읽었습니다. 위 번호나 은행 이름을 쉼표로 적어 주세요 "
                "(거래한 곳이 없으면 '없음')")
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
    목록 = slot.get("unit") == C.LIST_UNIT
    if auto:                                   # 사람 없이 도는 모드 — 회귀 확인용
        if 목록:
            # 페르소나를 목록 질문으로 옮긴다 — **예는 "전부 거래했다"** 다.
            # 그러면 유도가 하나도 안 걸려 질문이 가장 많은 경로가 되고, 아니오는
            # 가장 적은 경로가 된다. 검사가 두 극단을 다 걷는다
            banks = slot.get("기관") or []
            return ({"예": (",".join(banks), "list"),
                     "아니오": ("없음", "list"),
                     "모름": ("모름", "unsure")}[auto])
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
    if 목록:                                    # 목록 질문 — 예/아니오가 아니다 (F6)
        if low in UNSURE_IN:
            return raw, "unsure"
        return raw, ("list" if parse_banks(raw, slot.get("기관") or []) is not None
                     else "bad")
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
    if kind == "list":                              # 목록 질문 (F6)
        picked = parse_banks(raw, slot.get("기관") or [])
        if picked is None:
            return "bad"
        state[key] = picked
    elif kind == "yes":
        state[key] = True
    elif kind == "no":
        state[key] = False
    elif kind == "unsure":
        state[key] = C.UNSURE
    else:
        return "bad"
    return kind


def run(stamp: str, group: str, term: int, top: int,
        scripted: list[str] | None, auto: str | None,
        company: str | None = None, kinds: str | None = None,
        prefs: dict | None = None, prefs_arg: str | None = None,
        resume: dict | None = None) -> dict:
    """`resume` 는 이어받을 세션 로그다 (D9 · 이슈 #67 · `prereg-24`). 그 `state` 로 시작해
    **다음 질문부터** 묻는다. 서버가 무상태인 것과 같은 모양이다 — 답은 사용자(로그)가 들고
    온다(`0040`). 이어받은 로그의 답을 다시 묻지 않는다."""
    tax = C.load_tax()
    rows_all, by_pair = AB.load(stamp, group, term)
    if not rows_all:
        raise SystemExit(f"{term}개월 상품이 없다. --term 을 바꿔본다")
    # 0단계 — 후보 집합을 자른다 (`decisions/0028`). 질문은 이 집합에서만 나온다
    rows = C.scope_rows(rows_all, company, kinds)
    if not rows:
        cos = sorted({r["company"] for r in rows_all if r["company"]})
        raise SystemExit(f"찾는 범위에 맞는 상품이 없다 (은행={company} 예금/적금={kinds})\n"
                         f"가능한 은행: {', '.join(cos)}")
    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    total_all = C.questions_left(C.question_plan(rows_all, by_pair), {})
    state: dict = dict((resume or {}).get("state") or {})
    steps: list[dict] = []
    scoped = len(rows) < len(rows_all)

    print(f"\n=== 되묻기 질문 루프 · {group} {term}개월 · 스냅샷 {stamp} ===")
    if resume:
        # 이어받은 답이 후보에 없는 은행을 가리키면 조용히 "거래 없음" 으로 유도된다 — 서버와 같은 검사
        bad_banks = C.unknown_banks(state, rows)
        if bad_banks:
            raise SystemExit(f"이어받은 답에 후보에 없는 은행이 있다: {bad_banks} — 스코프가 다른 로그다")
        print(f"이어하기     {resume.get('_path', '세션 로그')} 에서 답 {len(state)}개를 이어받았다 · "
              f"다음 질문부터 묻는다")
    if scoped:
        print(f"찾는 범위   은행 {company or '전체'} · 예금/적금 {kinds or '전체'} "
              f"— 카탈로그 {len(rows_all)}개 중 {len(rows)}개 (질문 {total_all}→{total}개)")
    print(f"상품 {len(rows)}개 · 전부 답하면 질문 {total}개입니다. "
          f"언제든 '그만' 을 입력하면 멈춥니다.")
    print("'아니오'·'모르겠다' 로 답하면 그 조건에 딸린 문구 질문까지 같이 사라져 "
          "전체 질문 수가 줄어듭니다.")
    head = "선호 가중합 순" if prefs else "조건을 다 채웠을 때 순"
    print(f"\n■ 1단계 — 아무것도 묻지 않은 첫 화면 ({head})")
    scored = AB.score_all(rows, by_pair, state, tax)
    show_list(ranked(scored, prefs), top)
    st = status_bar(plan, state, scored, total, None, prefs)
    for line in P.lines(prefs or {},
                        sum(1 for s in ranked(scored, prefs) if s.get("_blocked"))):
        print(line)
    # 첫 화면을 기준으로 폭 변화를 보여준다 (`0029`). **이어받은 세션은 원 세션의 첫 화면이 기준이다** —
    # 폭 변화는 사용자의 여정에 대한 말이고, 여정은 로그가 시작한 곳에서 시작했다 (`prereg-24` P1 이 잡았다)
    start = dict((resume or {}).get("start") or st)
    out0 = V.outside_best(rows_all, rows, by_pair, state, tax) if scoped else None
    if out0:                                       # A7 — 첫 화면에서도 대가를 보여준다
        print(f"\n  ⚠ 지금 고른 범위 밖에 {out0['net_hi']:.2f}% 가 있습니다 "
              f"({out0['company']} {out0['name'][:22]} · +{out0['gap']:.2f}%p · "
              f"[{out0['channel']}] · 조건 다 채웠을 때) · "
              f"넓히면 질문이 {total_all}개로 늘어납니다")
    start_top1 = (resume or {}).get("top1_start", st["top1"])
    print("\n" + "-" * 92)
    print("■ 2단계 — 질문 루프. 많은 상품을 여는 질문부터 묻습니다 (순서는 고정입니다)")

    quit_at, quit_why, tick = None, "", time.monotonic()
    for step in range(1, MAX_STEPS + 1):
        # **뷰 모델과 같은 함수로 다음 질문을 고른다** (F4-1 · `0039` 반증 조건).
        # 여기서 따로 골랐더니 웹이 붙는 순간 순서 규칙이 두 군데가 됐다
        key, slot = V.next_question(scored, state)
        if key is None:
            break
        if step == MAX_STEPS:                  # 방어값에 닿았다 — **완주가 아니다**
            quit_at, quit_why = step, f"방어값 MAX_STEPS={MAX_STEPS} 에 닿았다"
            break
        head, lines = prompt_for(key, slot)
        print(f"\n  [{step}] {head}")
        print(f"      이 답 하나로 상품 {len(slot['products'])}개의 금리를 "
              f"계산할 수 있게 됩니다")
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
        prev = [C.row_key(s) for s in ranked(scored, prefs)]
        scored = AB.score_all(rows, by_pair, state, tax)
        print(f"\n      → '{raw}' 로 받았습니다")
        show_list(ranked(scored, prefs), 3, prev)
        st = status_bar(plan, state, scored, total, start, prefs)
        steps.append({"step": step, "key": key, "kind": slot["kind"],
                      "unit": slot["unit"], "products": len(slot["products"]),
                      "answer_kind": kind, "answer": raw,
                      "seconds": round(time.monotonic() - tick, 1), **st})
        tick = time.monotonic()

    print("\n" + "-" * 92)
    print("■ 3단계 — 결과")
    scored = AB.score_all(rows, by_pair, state, tax)
    outside = V.outside_best(rows_all, rows, by_pair, state, tax) if scoped else None
    screen, st = render_final_screen(scored, plan, state, total, top,
                                     outside, total_all if scoped else None, start,
                                     prefs)
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
            # 스코프와 선호 원문 — 이어하기(`--resume`)가 같은 후보 집합에서 이어지려면 필요하다 (D9)
            "company": company, "kinds": kinds, "prefs_arg": prefs_arg,
            "resumed_from": (resume or {}).get("_path"),
            "started": datetime.now().isoformat(timespec="seconds"),
            "questions_total": total, "mode": auto or ("scripted" if scripted is not None
                                                       else "interactive"),
            "quit_at": quit_at, "quit_why": quit_why, "answered": len(steps), "unsure": n_unsure,
            "state": {k: v for k, v in state.items()}, "steps": steps,
            "prefs": {k: v for k, v in (prefs or {}).items()},
            # `start` 는 첫 화면의 사실 — 이어받는 세션이 폭 변화의 기준으로 쓴다 (D9)
            "final": st, "top1_start": start_top1, "start": start}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if "--survey" in argv:               # 설문 문항과 고정 표를 그대로 보여준다
        print(P.survey())
        return
    group, term, top, auto, answers = "bank", 12, 10, None, None
    company, kinds, prefs_arg, resume_path = None, None, None, None
    for flag in ("--group", "--term", "--top", "--auto", "--answers",
                 "--company", "--kind", "--prefs", "--resume"):
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
            company = v if flag == "--company" else company
            kinds = v if flag == "--kind" else kinds
            prefs_arg = v if flag == "--prefs" else prefs_arg
            resume_path = v if flag == "--resume" else resume_path
            argv = argv[:i] + argv[i + 2:]
    # 이어하기 (D9) — 로그가 스냅샷·권역·기간·스코프·선호를 다 들고 있어 날짜 인자가 필요 없다.
    # 명령줄에 준 값이 있으면 그것이 이긴다 (같은 답으로 다른 정렬·top 을 보는 데 쓴다)
    resume: dict | None = None
    if resume_path:
        resume = json.loads(Path(resume_path).read_text(encoding="utf-8"))
        resume["_path"] = resume_path
        if not argv:
            argv = [resume["snapshot"]]
        if "--group" not in sys.argv:
            group = resume.get("group", group)
        if "--term" not in sys.argv:
            term = int(resume.get("term", term))
        if "company" not in resume:
            print("[경고] 옛 로그다 — 스코프(company·kinds)가 없어 전체 후보에서 이어진다. "
                  "같은 스코프를 --company · --kind 로 다시 주는 것이 맞다")
        company = company if "--company" in sys.argv else resume.get("company")
        kinds = kinds if "--kind" in sys.argv else resume.get("kinds")
        prefs_arg = prefs_arg if "--prefs" in sys.argv else resume.get("prefs_arg")
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/ask_loop.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--top 10] "
                         "[--company 우리,농협] [--kind 적금] "
                         "[--auto 예|아니오|모름] [--answers 예,아니오,모름]\n"
                         f"        [--prefs ...]  [--survey]  [--resume data/pilot/ask_session_*.json]\n"
                         f"        {P.USAGE}")
    if auto and auto not in ("예", "아니오", "모름"):
        raise SystemExit("--auto 는 예 · 아니오 · 모름 중 하나다")
    scripted = [a.strip() for a in answers.split(",")] if answers else None
    stamp = argv[0]
    log = run(stamp, group, term, top, scripted, auto, company, kinds,
              P.parse(prefs_arg), prefs_arg, resume)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = C.OUT_DIR / f"ask_session_{group}_{stamp}_{term}m_{ts}.json"
    out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
