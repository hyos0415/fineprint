# -*- coding: utf-8 -*-
"""선호 설문 → 고정 가중치 표 → 세후 가중합 정렬.

이 파일이 채우는 자리
    `problem.md` §3 이 받겠다고 적어 둔 **두 입력 중 하나(내 선호)** 가 통째로
    비어 있었다. 정렬은 `net_hi` 단순 내림차순이고(`0017`), 그래서 지금까지 만든
    것은 "추천기" 가 아니라 **계산기 + 되묻기**였다.

    시작할 근거는 2026-08-31 사람 세션이다 — 사용자가 스코프 밖 **+2.67%p** 를
    보고도 후보에 넣지 않았다(`prereg-11` §M4). *"주거래도 아니고, 경남에 연고도
    없고, 실물을 본 적도 없어서"*. **기관 접근성이 금리 2.67%p 보다 앞선 축인데
    시스템에 그 축이 하나도 없었다.**

단위가 왜 "금리 %p 환산" 인가 — `prereg-12` §2
    `problem.md` §3 의 예시는 추상 0~1 가중치(`금리 가중치 0.8`)인데 그 형태를
    안 쓴다. 이유가 둘이다.
      설명할 수 없다      0~1 로 정렬하면 화면에 "왜 이 순서인지" 를 못 적는다.
                        problem.md §3 은 그걸 약속했다
      후보에 종속된다     0~1 정규화는 min·max 가 필요하고 그건 후보 집합에 따라
                        변한다. 후보 4개 스코프에서 확정 카운터가 죽은 것(`0029`)과
                        같은 실패 모양이다
    대신 **"이 축을 금리 몇 %p 와 맞바꾸겠는가"** 로 묻는다. 그러면 화면에
    `영업점만 -0.50%p` 라고 그대로 적을 수 있다.

    **금리 축은 따로 묻지 않는다.** 금리가 기준 단위(계수 1.0 고정)이고 다른 축의
    %p 환산값이 곧 금리 대비 상대 중요도다. 또 물으면 같은 것을 두 번 묻는다.

절대 하지 않는 것 셋
    1. **기본값을 우리가 정하지 않는다.** `--prefs` 가 없으면 조정은 0개이고 정렬은
       지금과 소수점까지 같다. 채워 넣으면 `0024` P2(추측 금지) 위반이다
    2. **가중치를 판정에 안 쓴다.** `evaluate()` 는 이 모듈을 모른다. 층·범위·사유는
       선호와 무관하게 같아야 한다 (화면 계약 **A11** 이 전수로 검사한다)
    3. **정렬 점수를 금리 칸에 안 넣는다.** 화면의 금리는 계속 `net_lo~net_hi` 이고
       조정은 별도 칸으로 나간다. 점수를 금리처럼 보여주면 **공시에 없는 숫자를
       사용자에게 보여주는 것**이다 (`problem.md` §5)

지표에서 격리한다 — `prereg-12` §6
    `ask_budget.py`(기준선·게이트·예산 12개)는 이 모듈을 **import 하지 않는다.**
    선호로 확정률·커버리지를 좋게 만드는 도피를 막는 자리다 (`0018`).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate as C  # noqa: E402

# 답이 숫자가 아니라 "맨 아래로 내린다" 인 경우. 사용자의 사실 진술이라 숫자가 없다.
# **제외가 아니다** — 목록에 남기고 맨 아래로 내린다 (`prereg-12` §3).
BLOCK = "맨아래"

# ── 고정 가중치 표 (`prereg-12` §2)
#
# **다섯 문항 중 숫자에 근거가 붙는 것은 둘뿐이다.** 나머지는 "근거 없음 - 판단"이라고
# 여기 그대로 적는다. 없는 근거를 만들지 않는다 (`CLAUDE.md` 결정 기록 규칙).
#
#   Q3 `많이` = -3.00   **실측 하한 2.67%p** — 2026-08-31 세션에서 사용자가 스코프 밖
#                       +2.67%p 를 보고도 안 옮겼다. 그 사용자에게 페널티는 2.67 보다
#                       크다. 3.00 은 하한 바로 위 값이다. **표본 1이다**
#   Q4 `많이` = -1.00   **`--sort lo` 와 항등식으로 같아지는 값**이다.
#                       점수 = net_hi - 1.0 x (net_hi - net_lo) = net_lo.
#                       계수 0 이면 `--sort hi`(= `0017` 이 채택한 지금 기본).
#                       **두 끝이 이미 결정된 값이라 이 축만은 눈금이 임의가 아니다**
AXES: dict[str, dict] = {
    "영업점": {
        "question": "가입할 때 영업점에 갈 수 있습니까?",
        "choices": {"못간다": BLOCK, "되도록안간다": -0.50, "상관없다": 0.0},
        "basis": {"못간다": "사용자의 사실 진술 — 숫자가 필요 없다",
                  "되도록안간다": "근거 없음 — 판단"},
        "applies": "영업점만 가입되는 상품에",
        "per": "상품",
    },
    "처음기관": {
        "question": "거래해 본 적 없는 기관에 가입하는 것이 부담됩니까?",
        "choices": {"많이": -3.00, "조금": -0.50, "상관없다": 0.0},
        "basis": {"많이": "실측 하한 2.67%p (2026-08-31 세션 · 표본 1)",
                  "조금": "근거 없음 — 판단"},
        "applies": "거래기관 목록 밖 기관의 상품에",
        "per": "상품",
    },
    "확실성": {
        "question": "조건에 따라 금리가 크게 달라지는 상품이 부담됩니까?",
        "choices": {"많이": -1.00, "조금": -0.50, "상관없다": 0.0},
        "basis": {"많이": "--sort lo 와 항등식으로 같아지는 값",
                  "조금": "근거 없음 — 판단 (두 끝의 중간)"},
        "applies": "금리 범위 폭 1%p 당",
        "per": "폭",
    },
    "이행": {
        "question": "가입 후에 계속 해야 하는 조건이 부담됩니까?",
        "choices": {"많이": -0.30, "조금": -0.10, "상관없다": 0.0},
        "basis": {"많이": "근거 없음 — 판단", "조금": "근거 없음 — 판단"},
        "applies": "이행 조건(자동이체·카드실적·급여이체·미션·목표달성) 1개당",
        "per": "이행조건",
    },
}

# 축이 아니라 **목록**이다. `처음기관` 과 짝을 이룬다.
LIST_AXIS = "거래기관"
LIST_SEP = "·"          # `,` 는 축 구분자라 쓸 수 없다. 화면 표기와 같은 기호를 쓴다

USAGE = (f"--prefs 영업점=되도록안간다,{LIST_AXIS}=우리{LIST_SEP}농협,"
         "처음기관=많이,확실성=조금,이행=상관없음")


def survey() -> str:
    """설문 문항을 그대로 화면에 낸다. 사용자가 무엇을 답하는지 먼저 보여준다."""
    out = ["선호 설문 — 답을 고정된 표로 금리 %p 에 옮깁니다 (prereg-12 §2)", ""]
    for key, ax in AXES.items():
        out.append(f"  {key:<6}{ax['question']}")
        for choice, value in ax["choices"].items():
            shown = "맨 아래로" if value is BLOCK else f"{value:+.2f}%p"
            basis = ax["basis"].get(choice, "")
            out.append(f"      {choice:<8}{shown:>12}   {ax['applies']}"
                       + (f"   ← {basis}" if basis else ""))
        out.append("")
    out.append(f"  {LIST_AXIS:<6}거래해 본 기관이 어디입니까? "
               f"(예: {LIST_AXIS}=우리{LIST_SEP}농협) — 처음기관 과 짝입니다")
    out.append("")
    out.append("  금리는 기준 단위입니다(계수 1.0 고정). 위 값들이 곧 금리 대비 중요도라")
    out.append("  따로 묻지 않습니다.")
    out.append(f"  {USAGE}")
    return "\n".join(out)


def parse(arg: str | None) -> dict:
    """`--prefs` 문자열을 조정값 dict 로. **안 주면 빈 dict — 가중치 0개다.**

    값은 두 가지로 적을 수 있다 (`prereg-12` §2 · 화면 계약 A10).
        설문 답 문구   `영업점=되도록안간다`   → 고정 표의 값
        %p 직접       `영업점=-0.8`          → 표를 덮어쓴다
    """
    if not arg:
        return {}
    out: dict = {"_answers": {}}
    for tok in arg.split(","):
        tok = tok.strip()
        if not tok:
            continue
        key, _, raw = tok.partition("=")
        key, raw = key.strip(), raw.strip()
        if key == LIST_AXIS:
            out[LIST_AXIS] = [w.strip() for w in raw.replace("|", LIST_SEP)
                              .split(LIST_SEP) if w.strip()]
            out["_answers"][key] = raw
            continue
        if key not in AXES:
            raise SystemExit(f"모르는 선호 축: {key}\n"
                             f"가능한 값: {', '.join(AXES)}, {LIST_AXIS}\n{USAGE}")
        if raw in AXES[key]["choices"]:
            out[key] = AXES[key]["choices"][raw]
            out["_answers"][key] = raw
            continue
        try:                                  # %p 를 직접 적어 표를 덮어쓴다
            out[key] = float(raw)
            out["_answers"][key] = "(표를 덮어썼다)"
        except ValueError:
            raise SystemExit(
                f"'{key}' 의 답을 읽을 수 없다: '{raw}'\n"
                f"가능한 답: {', '.join(AXES[key]['choices'])} "
                f"또는 %p 숫자(예: {key}=-0.8)")
    return out


def ongoing_count(s: dict) -> int:
    """이 상품의 금리에 들어간 **이행 유형 개수**. 항목 수가 아니라 유형 수다.

    `자동이체` 항목이 셋이어도 사용자가 하는 일은 하나다. `met` 과 `unknown` 을 같이
    세는 이유는 정렬 기준이 `net_hi` 이고 `unknown` 이 거기 들어가 있기 때문이다
    (`아니오` 로 답한 `unmet` 은 `net_hi` 에서 빠지므로 세지 않는다 · `0024`).
    """
    return len({t for t in (s.get("met") or []) + (s.get("unknown") or [])
                if t in C.ONGOING})


def adjust(s: dict, prefs: dict) -> tuple[float, bool, list[str]]:
    """상품 하나의 (조정 %p, 맨아래 여부, 사유 문구들).

    **사유를 같이 내는 것이 이 함수의 절반이다** — `problem.md` §3 이 약속한
    *"왜 이 순서인지가 같이 나온다"* 가 이 문자열들이다.
    """
    if not prefs:
        return 0.0, False, []
    adj, blocked, why = 0.0, False, []

    v = prefs.get("영업점")
    # **`채널미상` 에는 안 붙인다** — 추측하지 않는다 (`channel_label` · 이슈 #22)
    if v is not None and s.get("channel") == "영업점만":
        if v is BLOCK:
            blocked = True
            why.append("영업점만 — 갈 수 없다고 답했습니다")
        elif v:
            adj += v
            why.append(f"영업점만 {v:+.2f}")

    v = prefs.get("처음기관")
    if v:
        known = prefs.get(LIST_AXIS) or []
        co = s.get("company") or ""
        if not any(k and k in co for k in known):
            adj += v
            why.append(f"거래기관 밖 {v:+.2f}")

    v = prefs.get("확실성")
    if v:
        width = s["net_hi"] - s["net_lo"]
        if width > 1e-9:
            adj += v * width
            why.append(f"폭 {width:.2f}%p {v * width:+.2f}")

    v = prefs.get("이행")
    if v:
        n = ongoing_count(s)
        if n:
            adj += v * n
            why.append(f"이행 {n}개 {v * n:+.2f}")

    return round(adj, 4), blocked, why


def annotate(scored: list[dict], prefs: dict) -> list[dict]:
    """각 상품에 `_adj`·`_blocked`·`_why`·`_score` 를 단다. **금리는 안 건드린다.**

    `_score` 는 **정렬에만** 쓴다. 화면의 금리 칸은 계속 `net_lo~net_hi` 다
    (화면 계약 A11 이 이것을 전수로 검사한다).
    """
    for s in scored:
        adj, blocked, why = adjust(s, prefs)
        s["_adj"], s["_blocked"], s["_why"] = adj, blocked, why
        s["_score"] = round(s["net_hi"] + adj, 4)
    return scored


def sort_key(s: dict):
    """정렬 키. `prefs` 가 없으면 `_adj` 가 0 이라 `0017` 의 `net_hi` 순과 같아진다.

    동점 처리도 `0017` 그대로다 — `net_hi` → `net_lo` → 이름.
    """
    return (s.get("_blocked", False), -s.get("_score", s["net_hi"]),
            -s["net_hi"], -s["net_lo"], s["name"])


def lines(prefs: dict, n_blocked: int = 0) -> list[str]:
    """화면 계약 **A10** — 옮긴 가중치 전부를 %p 로 보여주고 고치는 방법을 적는다.

    `problem.md` §3 이 *"옮긴 결과를 사용자에게 보여주고 고칠 수 있게 한다. 이게
    있어야 '시스템이 마음대로 정했다' 가 안 된다"* 고 적어 둔 자리다.
    """
    if not prefs:
        return []
    out = ["\n  선호  답을 금리 %p 로 옮긴 결과입니다 (정렬만 바꿉니다 · 금리는 안 바뀝니다)"]
    known = prefs.get(LIST_AXIS)
    if known is not None:
        tail = "" if known else "  — 목록이 비어 모든 기관이 '처음' 이 됩니다"
        out.append(f"        {LIST_AXIS:<8}"
                   f"{LIST_SEP.join(known) or '(비어 있음)'}{tail}")
    for key, ax in AXES.items():
        if key not in prefs:
            continue
        v = prefs[key]
        ans = prefs.get("_answers", {}).get(key, "")
        shown = "맨 아래로" if v is BLOCK else f"{v:+.2f}%p"
        out.append(f"        {key:<8}{ans:<16}{shown:>10}  {ax['applies']}")
    if n_blocked:
        out.append(f"        맨 아래로 내린 상품 {n_blocked}개 — 목록에서 빼지 않습니다")
    out.append(f"        고치려면 {USAGE}")
    out.append("        %p 를 직접 적어 표를 덮어쓸 수도 있습니다 (예: 영업점=-0.8)")
    return out
