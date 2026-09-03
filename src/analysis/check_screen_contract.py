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
    A10 `--prefs` 가 걸린 화면에는 옮긴 가중치가 %p 로 보이고 고치는 방법이 있어야
        한다 (`prereg-12` §4 · `problem.md` §3 — "시스템이 마음대로 정했다" 를 막는다)
    A11 `--prefs` 를 걸어도 상품별 `net_lo`·`net_hi`·`tier`·`caveats` 가 안 걸었을
        때와 **완전히 같아야 한다** — 가중치는 정렬만 바꾼다 (`prereg-12` §4)
    A12 금리를 보여주는 화면에는 **`세후` 라벨**이 있어야 한다 (`0034`·`0035` ·
        이슈 #31). 공정위 예규 「금융상품 등의 표시·광고에 관한 심사지침」 Ⅴ.1.마 —
        *"수익률(이자율) 표기시 '세전'인지 '세후'인지를 누락"* 하면 부당한 표시·광고다
    A13 화면에 **이 화면이 무엇인지 밝히는 고지**가 있어야 한다 (`0035` · A안) —
        공시 계산 결과이며 판매·중개하지 않는다는 사실
    A14 **우리가 지은 내부 이름이 화면에 없어야 한다** (F5 · 이슈 #45) —
        `급여_연금이체` · `추출불확실` · `미응답` · `스코프` 처럼 만든 사람만 아는 말.
        목록은 `calculate.internal_words()` 한 곳에서 온다. `0019` 와 다르다 —
        `0019` 는 *뜻을 모르는 남의 낱말*("탑스")에 뜻을 지어내는 것을 막았고, 여기는
        **우리가 지은 낱말**이라 뜻을 정확히 안다
    A15 **"하겠다" 고 답한 조건 위에 선 금리는 그 전제를 말해야 한다** (이슈 #50 ·
        `prereg-17`) — 은행권 확정 50개 중 44개가 자동이체·카드실적 같은 행동 조건에
        기댄다. 리포트와 웹 화면에 `PREMISE_NOTE` 와 그 조건 목록이 있어야 한다

    **비교 리포트도 같은 계약을 진다** (이슈 #33). 목록 화면과 리포트는 렌더가
    다르므로 계약을 두 번 검사한다 — 리포트 쪽 위반은 `detail` 에 `[리포트]` 가
    붙는다. 검사하는 것은 A1(범위) · A3(사유 문장) · A12 · A13 넷이다.

검사는 두 겹이다 (F4-0 · 이슈 #36)
    **모델 겹** `view.check_model(vm)` — 뷰 모델에 **사실이 담겼나**. 렌더러가
        무엇이든 같다. 데이터가 아예 없으면 어떤 렌더러도 계약을 못 지킨다.
        위반은 `detail` 에 `[모델]` 이 붙는다
    **렌더 겹** 아래 문자열 검사들 — 그 사실을 **실제로 출력했나**. 렌더러마다 건다
        **렌더러가 셋이다** — CLI 최종 화면 · 비교 리포트 · **웹 HTML**(F4-3).
        위반은 `detail` 에 `[리포트]`·`[웹]` 이 붙는다

    **두 겹이 잡는 것이 다르다.** 뷰 모델에 `net_lo`·`net_hi` 가 둘 다 있어도
    렌더러가 하나만 출력하면 A1 위반이고 모델 겹은 그것을 못 잡는다. `0035` 가
    찾은 실패가 정확히 그 모양이었다 — **데이터는 있고 한 화면에만 라벨이 없었다.**

    **A11 이 #24 의 핵심 방어선이다.** 가중치가 판정에 새면 사용자의 취향이 "이 상품의
    금리가 얼마인가" 라는 사실을 바꾸는 것이고, 그 순간 `problem.md` §4 의
    "틀릴 수 없는 것 / 틀릴 수 있는 것" 구분이 무너진다.

    검사 대상 화면은 `ask_loop.render_final_screen()` 이다 — **사용자가 12번째 질문에서
    그만두면 보는 것이 정확히 그 화면**이므로, 모든 중간 상태에 대해 같은 함수를 읽는다.

표본 — `prereg-09` §4 에서 **재기 전에** 못 박았다
    P1  세 페르소나(전부 예 · 전부 아니오 · 전부 모름)의 모든 단계
    P2  시드 0~199 고정 무작위 혼합 세션 (매 질문 예/아니오/모름/숫자를 무작위)

사용법:
    python src/analysis/check_screen_contract.py 20260826 --group bank --term 12
    python src/analysis/check_screen_contract.py 20260826 --seeds 20    (빠른 점검)
    python src/analysis/check_screen_contract.py 20260826 --prefs 확실성=많이   (A10·A11)
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import ask_loop as L  # noqa: E402
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402
import view as V  # noqa: E402

SEEDS = 200          # `prereg-09` §4 에 못 박은 값. 결과를 보고 고치지 않는다
EPS = 1e-6

# A3 에서 "화면에 문장이 있어야 한다" 고 요구하는 사유 코드 — `CAVEAT` 전부다.
# 지금 3단계 화면은 `HARD_CAVEATS` 여섯 개만 문장으로 낸다. 그 차이가 위반으로 잡히면
# **그것이 이 검사가 찾은 것**이다(`prereg-09` §5 가 A3 위반 가능성을 예고했다).
A3_CODES = tuple(C.CAVEAT.keys())


# 웹은 **보이는 글자만** 본다. 상태 키가 `answer_key`·`state_json` 의 값으로 폼에
# 실려야 하는데(`0040` 무상태), 그건 사용자가 읽는 글자가 아니다. 태그를 지우면
# 속성값이 같이 사라지므로 남는 것이 정확히 **화면에 보이는 글자**다.
TAG = re.compile(r"<[^>]*>")
# `<style>`·`<script>` 안은 **화면 글자가 아니다.** 태그만 지우면 CSS 본문이 남아
# 거기 쓴 한글 주석까지 화면에 나간 낱말로 세게 된다
HIDDEN = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.S | re.I)


def visible(html: str) -> str:
    return TAG.sub(" ", HIDDEN.sub(" ", html))


# 결정 번호·사전등록 좌표 — `0017` · `decisions/0018` · `prereg-15` 꼴.
# 금리(`2.55`)·스냅샷(`20260826`)·개수와 겹치지 않게 **네 자리 앞이 0 인 것**만 본다
DOC_REF = re.compile(r"decisions?/\d{4}|prereg-\d{2}|(?<![\d.])0\d{3}(?![\d.])")


def check_words(text: str, where: str) -> list[dict]:
    """A14 — 내부 이름이 화면에 남았나 (F5 · 이슈 #45).

    **목록은 `calculate.internal_words()` 한 곳에서 온다.** 검사기가 자기 목록을
    들면 표를 고칠 때 한쪽만 고쳐진다(`0035`).

    상품명은 목록에 없다 — `해피라이프_여행스케치적금` 처럼 **은행이 지은 이름에도
    밑줄이 있다.** 그건 공시 원문이고 손대면 `0031` 이 막은 자리에 들어간다.
    """
    bad = [{"assert": "A14", "product": w,
            "detail": f"{where}에 내부 이름 `{w}` 이 남아 있다"}
           for w in C.internal_words() if w in text]
    # **우리 기록의 좌표도 사용자 화면에 쓰지 않는다** (F5). 실제로 새고 있었다 —
    # 리포트가 *"왜 이 순서인가 — 세후 최대 금리 순 (0017 — 다 채웠을 때 순)"* 이라고
    # 썼고, CLI 2단계 머리말이 *"(decisions/0018 고정 순서)"* 였다.
    # `CLAUDE.md` 가 정한 것과 같다 — **결론을 먼저, 감사 번호로 시작하지 않는다.**
    bad += [{"assert": "A14", "product": m,
             "detail": f"{where}에 결정 번호 `{m}` 이 남아 있다 — 우리 기록의 좌표다"}
            for m in sorted(set(DOC_REF.findall(text)))]
    return bad


def check_org_names(text: str, scored: list[dict], where: str) -> list[dict]:
    """A14 — **공시 이름이 화면에 남았나** (F5). 표기가 달라지는 기관만 본다.

    `농협은행주식회사`·`주식회사 케이뱅크` 처럼 법인 형태가 붙은 이름이 그대로 나가면
    위반이다. 이름이 안 바뀌는 기관은 보지 않는다 — 그러면 검사가 정상 화면을 잡는다.
    """
    bad = []
    seen: dict[str, str] = {}
    for co in sorted({s.get("company") or "" for s in scored if s.get("company")}):
        shown = C.org_label(co)
        if shown != co and co in text:
            bad.append({"assert": "A14", "product": co,
                        "detail": f"{where}에 공시 이름 `{co}` 이 남아 있다 "
                                  f"(화면 표기는 `{shown}`)"})
        # **표기가 겹치면 서로 다른 은행이 한 이름으로 보인다** — `0031` 이 상품 신원에서
        # 막은 실패와 같은 모양이다. `0046` 이 반증 조건으로 적어 둔 것을 검사로 만든다.
        # 지금 스냅샷에서는 은행 17곳·저축은행 30곳 다 충돌 0 이다
        if shown in seen and seen[shown] != co:
            bad.append({"assert": "A14", "product": co,
                        "detail": f"표기 이름 `{shown}` 이 `{seen[shown]}` 과 겹친다 — "
                                  f"서로 다른 은행이 한 이름으로 보인다"})
        seen[shown] = co
    return bad


def check_labels(screen: str) -> list[dict]:
    """A12·A13 — 화면이 **무엇을 말하는 숫자인지**와 **자기가 무엇인지**를 밝히나.

    문구는 `ask_loop` 의 상수를 읽는다 — 검사기가 자기 사본을 갖고 있으면 렌더 쪽만
    고쳐도 통과한다.

    **이 검사를 만든 이유가 실제 누락이다** — `calculate.py` 목록 헤더에는
    `세후 확정~최대`·`세전` 이 있었는데 **질문 루프 화면에는 `세후` 라는 말이 한
    번도 없었다**(2026-08-31 · `0035`). 사용자가 보는 것은 이 화면이다.
    """
    bad = []
    if "%" in screen and "세후" not in screen:
        bad.append({"assert": "A12", "product": "-",
                    "detail": "금리가 있는 화면에 `세후` 라벨이 없다"})
    if L.NOTICE not in screen:
        bad.append({"assert": "A13", "product": "-",
                    "detail": "성격 고지가 화면에 없다"})
    return bad


def check_web(scored: list[dict], plan: dict, state: dict, total: int,
              prefs: dict | None, tag: str,
              outside: dict | None = None,
              order: str = "hi") -> list[dict]:
    """**웹 HTML** 에 렌더 겹을 건다 (F4-3 · 이슈 #42).

    렌더러가 하나 늘면 계약도 하나 늘린다(`0039` D3). 뷰 모델에 사실이 담겨 있어도
    **렌더러가 안 그리면 위반**이고, 그건 모델 겹이 못 잡는다.

    F4-2 가 HTML 만드는 자리를 **함수 하나**로 뒀기 때문에(`0043` D2) 여기서
    그것을 부르면 된다 — 브라우저도 헤드리스도 필요 없다. **JS 없이 도는 화면**이라
    서버가 낸 HTML 이 사용자가 보는 것과 같다.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "web"))
    import render as RENDER
    import report as R

    vm = V.build(scored, plan, state, total, 10, outside, None, None, prefs, order)
    reports = [R.build(s, i, prefs) for i, s in enumerate(vm["products"], 1)]
    form = {"snapshot": "-", "group": "-", "term": 12, "order": order,
            "state_json": "{}"}
    html = RENDER.render_screen(vm, form, reports)

    def hit(code: str, product: str, detail: str) -> list[dict]:
        return [{"assert": code, "product": product, "session": tag, "step": -1,
                 "detail": f"[웹] {detail}"}]

    bad: list[dict] = []
    # **0단계 폼과 오류 화면도 사용자 화면이다** (F5 · A14). 실제로 여기 `스코프` 가
    # 남아 있었다 — 오류가 화면으로 나가는 자리를 검사 밖에 두면 낱말이 거기 숨는다
    for 화면, 이름 in ((RENDER.render_start(), "0단계 폼"),
                    (RENDER.render_start({}, "찾는 범위에 맞는 상품이 없습니다"),
                     "0단계 폼(오류)")):
        for v in check_words(visible(화면), 이름):
            bad += hit("A14", v["product"], v["detail"])
    # A12·A13 — 세후 라벨과 고지. 문구는 상수에서 온다(사본을 만들지 않는다)
    if "%" in html and "세후" not in html:
        bad += hit("A12", "-", "금리가 있는 화면에 `세후` 라벨이 없다")
    if L.NOTICE not in html:
        bad += hit("A13", "-", "성격 고지가 화면에 없다")
    # A14 — **보이는 글자만** 본다 (F5). 상태 키와 답으로 보낼 공시 이름은 hidden·
    # value 로 실려야 하므로, 태그를 지운 뒤에 본다
    seen = visible(html)
    for v in check_words(seen, "웹 화면") + check_org_names(seen, scored, "웹 화면"):
        bad += hit("A14", v["product"], v["detail"])
    # A1 — 폭이 남은 상품은 범위로 그려야 한다
    for s in vm["products"]:
        if s["net_hi"] - s["net_lo"] > EPS and V.display(s)["범위"] not in html:
            bad += hit("A1", s["name"], f"범위 {V.display(s)['범위']} 가 화면에 없다")
    # A15 — 행동 조건에 기댄 금리는 전제를 말한다 (이슈 #50). 리포트 겹이 아니라
    # **웹 렌더러가 그렸는지**를 본다 — 모델에 있어도 안 그리면 위반이다(`0039`)
    for rep in reports:
        if rep["전제"] and C.PREMISE_NOTE not in html:
            bad += hit("A15", rep["상품"], "행동 조건에 기댄 금리인데 전제 문장이 없다")
            break
    # A3 — 사유는 **문장**으로 나가야 한다. 그리고 태그는 **라벨**이어야 한다 (A14)
    for r in vm["notices"]["사유"]:
        if r["문장"] not in html:
            bad += hit("A3", f"사유 {r['코드']}", f'"{r["문장"][:36]}…" 가 없다')
        if r["라벨"] not in html:
            bad += hit("A14", f"사유 {r['코드']}",
                       f'사용자용 라벨 "{r["라벨"]}" 이 화면에 없다')
    # A7 — 스코프 밖 최고 금리
    if outside and f"{outside['net_hi']:.2f}" not in html:
        bad += hit("A7", outside["name"], "스코프 밖 최고 금리가 화면에 없다")
    # A8 — 성과 줄이 목록 1위와 같아야 한다. 낱말도 사실이어야 한다(`0030`)
    if vm["headline"]["상품"]:
        d = V.display(vm["headline"]["상품"])
        want = f"{vm['headline']['라벨']} {d['범위']}"
        if want not in html:
            bad += hit("A8", d["이름"], f"성과 줄 '{want}' 가 화면에 없다")
    # A10 — 옮긴 가중치가 보이고 고치는 방법이 있어야 한다
    if prefs:
        for key, answer in (prefs.get("_answers") or {}).items():
            if answer not in html:
                bad += hit("A10", key, f"가중치 답 '{answer}' 가 화면에 없다")
        if "처음으로" not in html:
            bad += hit("A10", "-", "선호를 고치는 방법이 화면에 없다")
    return bad


def check_report(scored: list[dict], top: int, prefs: dict | None,
                 tag: str) -> list[dict]:
    """비교 리포트(F1)에 A1·A3·A12·A13 을 건다 (이슈 #33).

    **왜 목록 화면과 따로 검사하나.** 렌더가 다르다 — 목록은 한 줄이고 리포트는
    블록이다. `0035` 가 찾은 실패가 정확히 그 모양이었다(`calculate.py` 목록에는
    세후 라벨이 있고 `ask_loop` 화면에는 없었다). 렌더가 하나 늘면 계약도 하나
    늘려야 한다.

    **전 세션에서 돌리지 않는다.** 리포트는 목록보다 렌더가 무겁고, 여기서 잡는
    것은 상태에 따라 변하는 값이 아니라 **렌더 구조**다. 페르소나 끝 상태 세 개와
    아무것도 안 답한 상태에서 본다.
    """
    import report as R
    text = R.render_all(scored, top, prefs)
    bad = [{**v, "detail": f"[리포트] {v['detail']}", "session": tag, "step": -1}
           for v in (check_labels(text) + check_words(text, "리포트")
                     + check_org_names(text, scored, "리포트"))]
    main = L.ranked(scored, prefs)[:top]
    for s in main:
        rep = R.build(s, 1, prefs)
        block = R.render(rep)
        if s["net_hi"] - s["net_lo"] > EPS and "~" not in block:
            bad.append({"assert": "A1", "product": s["name"], "session": tag,
                        "step": -1, "detail": "[리포트] 폭이 남았는데 범위가 없다"})
        # A15 — "하겠다" 고 답한 조건 위에 선 금리는 그 전제를 말해야 한다 (이슈 #50)
        if rep["전제"] and C.PREMISE_NOTE not in block:
            bad.append({"assert": "A15", "product": s["name"], "session": tag,
                        "step": -1, "detail": "[리포트] 행동 조건에 기댄 금리인데 "
                                              "전제 문장이 없다"})
    for code in sorted({c for s in main for c in s.get("caveats", [])}
                       & set(A3_CODES)):
        if C.CAVEAT[code] not in text:
            bad.append({"assert": "A3", "product": f"사유 {code}", "session": tag,
                        "step": -1,
                        "detail": f"[리포트] \"{C.CAVEAT[code][:36]}…\" 가 없다"})
    return bad


def check_state(screen: str, scored: list[dict], tax: dict,
                prefs: dict | None = None) -> list[dict]:
    """한 중간 상태의 화면에 대해 A1·A2·A3·A5·A9·A12·A13 을 본다.

    A4 는 세션 단위라 따로 본다.
    """
    bad = (check_labels(screen) + check_words(screen, "화면")     # A12·A13 · A14
           + check_org_names(screen, scored, "화면"))
    main = L.ranked(scored, prefs)
    for i, s in enumerate(main, 1):
        line = L.product_line(i, s)
        width = s["net_hi"] - s["net_lo"]
        # **렌더된 줄을 본다.** 여기가 `L.span(s)` 를 보고 있었다 — 그건 헬퍼가
        # 제대로 동작하는지일 뿐이고, **화면이 그 값을 실제로 썼는지는 안 봤다.**
        # F4-0 음성 검사에서 잡혔다(2026-09-01 · 이슈 #36): `product_line` 이 최대값
        # 하나만 출력하게 바꿔도 A1 이 통과했다. 계약 검사가 계약을 안 보고 있었다
        if width > EPS and "~" not in line:
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


def check_prefs_shown(screen: str, prefs: dict) -> list[dict]:
    """A10 — 옮긴 가중치가 **전부** %p 로 보이고 고치는 방법이 적혀 있는가.

    `problem.md` §3 이 *"옮긴 결과를 사용자에게 보여주고 고칠 수 있게 한다. 이게
    있어야 '시스템이 마음대로 정했다' 가 안 된다"* 고 적어 둔 자리다.
    """
    bad = []
    for key in P.AXES:
        if key not in prefs:
            continue
        v = prefs[key]
        want = "맨 아래로" if v is P.BLOCK else f"{v:+.2f}%p"
        if want not in screen:
            bad.append({"assert": "A10", "product": key,
                        "detail": f"'{want}' 가 화면에 없다"})
    if "--prefs" not in screen:
        bad.append({"assert": "A10", "product": "-",
                    "detail": "고치는 방법(--prefs)이 화면에 없다"})
    return bad


def check_prefs_isolated(scored: list[dict], rows: list[dict], by_pair: dict,
                         state: dict, tax: dict) -> list[dict]:
    """A11 — 선호를 걸어도 **판정이 안 변한다.**

    `scored` 는 선호가 붙은 쪽(`ranked()` 가 `_adj`·`_score` 를 달아 놨다)이고,
    여기서 선호 없이 같은 상태를 다시 채점해 상품별로 대조한다.
    `evaluate()` 가 `prefs` 를 인자로 안 받으므로 구조적으로 참이어야 하지만,
    **구조가 무너지는 순간을 잡는 것이 이 assert 의 존재 이유다** — 조정값을
    `net_hi` 에 더해 버리는 구현이 가장 쉬운 실수다.

    **`code` 로 짝지으면 안 된다** — 유일하지 않다. 은행권 12개월에서 6개 코드가
    두 행씩이다(`우리SUPER주거래적금`·`해피라이프_여행스케치적금V` 등. 적립유형만
    다르고 기본금리가 2.5/2.3 처럼 갈린다). 처음 이 함수를 `code` 로 짝지었더니
    A11 이 2,388건 불통과로 나왔는데 **전부 짝을 잘못 지은 것**이었다.
    `AB.score_all()` 은 `rows` 순서를 그대로 지키므로 **자리로 짝짓는다.**
    """
    plain = AB.score_all(rows, by_pair, state, tax)
    if len(plain) != len(scored):
        return [{"assert": "A11", "product": "-",
                 "detail": f"상품 수가 다르다: 선호 {len(scored)} ≠ 기준 {len(plain)}"}]
    bad = []
    for s, b in zip(scored, plain):
        for field in ("net_lo", "net_hi"):
            if abs(s[field] - b[field]) > EPS:
                bad.append({"assert": "A11", "product": s["name"],
                            "detail": f"{field} 이 선호에 따라 변했다: "
                                      f"{b[field]} → {s[field]}"})
        if s["tier"] != b["tier"]:
            bad.append({"assert": "A11", "product": s["name"],
                        "detail": f"tier 가 변했다: {b['tier']} → {s['tier']}"})
        if sorted(s.get("caveats") or []) != sorted(b.get("caveats") or []):
            bad.append({"assert": "A11", "product": s["name"],
                        "detail": f"caveats 가 변했다: {b.get('caveats')} → "
                                  f"{s.get('caveats')}"})
        if L.span(s) != L.span(b):
            bad.append({"assert": "A11", "product": s["name"],
                        "detail": f"금리 칸이 변했다: {L.span(b)} → {L.span(s)}"})
    return bad


def pick_answer(slot: dict, rng: random.Random | None, persona: str | None) -> tuple[str, str]:
    """(원문, 종류). 페르소나면 고정, 무작위면 시드로 뽑는다.

    `prereg-10` 뒤로 유형 질문과 문구 질문이 같은 모양이라 답은 셋뿐이다 —
    수치 경로가 사라졌다.
    """
    if slot.get("unit") == C.LIST_UNIT:              # 목록 질문 (F6 · `prereg-15`)
        banks = slot.get("기관") or []
        if persona:
            # **예 = 전 기관과 거래한다** — 유도가 하나도 안 걸려 질문이 가장 많은 경로다.
            # **아니오 = 거래한 곳이 없다** — 전부 유도되어 가장 적은 경로다.
            # 검사가 두 극단을 다 걷는다
            return {"예": (",".join(banks), "list"),
                    "아니오": ("없음", "list"),
                    "모름": ("모름", "unsure")}[persona]
        assert rng is not None
        if rng.random() < 1 / 3:
            return "모름", "unsure"                  # 유도를 안 쓰는 경로도 걷는다
        picked = [b for b in banks if rng.random() < 0.3]
        return (",".join(picked) if picked else "없음"), "list"
    if persona:
        return {"예": ("예", "yes"), "아니오": ("아니오", "no"),
                "모름": ("모름", "unsure")}[persona]
    assert rng is not None
    kind = rng.choice(["yes", "no", "unsure"])
    return ({"yes": "예", "no": "아니오", "unsure": "모름"}[kind], kind)


def walk(rows: list[dict], by_pair: dict, plan: dict, total: int, tax: dict,
         persona: str | None = None, seed: int | None = None,
         rows_all: list[dict] | None = None,
         prefs: dict | None = None,
         order: str = "hi") -> list[dict]:
    """세션 하나를 끝까지 걸으며 각 중간 상태를 검사한다. 위반 목록을 낸다."""
    rng = random.Random(seed) if seed is not None else None
    state: dict = {}
    bad: list[dict] = []
    prev_left = None
    scoped = rows_all is not None and len(rows_all) > len(rows)
    for step in range(len(plan) * 3 + 5):        # 무한 루프 방어
        scored = AB.score_all(rows, by_pair, state, tax)
        outside = (V.outside_best(rows_all, rows, by_pair, state, tax)
                   if scoped else None)
        screen, st = L.render_final_screen(scored, plan, state, total, None, outside,
                                           prefs=prefs, order=order)
        if outside and f"{outside['net_hi']:.2f}%" not in screen:      # A7
            bad.append({"assert": "A7", "product": outside["name"], "session": "-",
                        "step": step,
                        "detail": f"스코프 밖 최고 {outside['net_hi']:.2f}% 가 화면에 없다"})
        tag = persona or f"seed{seed}"
        for v in check_state(screen, scored, tax, prefs):
            bad.append({**v, "session": tag, "step": step})
        # 모델 겹 — 화면 문자열이 아니라 **뷰 모델**을 본다 (F4-0 · 이슈 #36)
        vm = V.build(scored, plan, state, total, None, outside, prefs=prefs,
                     order=order)
        for v in V.check_model(vm):
            bad.append({**v, "session": tag, "step": step})
        if prefs:                                                  # A10 · A11
            # `scored` 를 **정렬하지 않은 채로** 넘긴다 — `ranked()` 가 이미 같은
            # dict 들에 `_adj`·`_score` 를 달아 놨고, 짝짓기는 자리로 한다
            for v in (check_prefs_shown(screen, prefs)
                      + check_prefs_isolated(scored, rows, by_pair, state, tax)):
                bad.append({**v, "session": tag, "step": step})
        if prev_left is not None and st["left"] > prev_left:      # A4
            bad.append({"assert": "A4", "product": "-", "session": tag, "step": step,
                        "detail": f"남은 질문 {prev_left} → {st['left']} 로 늘었다"})
        main_now = L.ranked(scored, prefs, order)                 # A8
        if main_now:
            want = L.span(main_now[0])
            if want not in screen or main_now[0]["name"][:20] not in screen:
                bad.append({"assert": "A8", "product": main_now[0]["name"],
                            "session": tag, "step": step,
                            "detail": f"성과 줄에 1위 {want} 가 없다"})
            # **낱말도 사실이어야 한다.** A8 이 처음에는 숫자만 봤고, 그래서 선호를
            # 넣었을 때 성과 줄이 `최고 2.79~2.88%` 라고 쓰는데 **같은 화면 3위에
            # 3.26% 가 있는** 상태를 못 잡았다(`0030`). 사람이 화면을 읽어서 찾았다.
            best = max(s["net_hi"] for s in main_now)
            if (f"성과  최고 {want}" in screen
                    and main_now[0]["net_hi"] < best - EPS):
                bad.append({"assert": "A8", "product": main_now[0]["name"],
                            "session": tag, "step": step,
                            "detail": f"성과 줄이 '최고' 라고 쓰는데 1위 "
                                      f"{main_now[0]['net_hi']:.2f}% 위에 "
                                      f"{best:.2f}% 가 있다"})
            # **확정된 값 순 화면도 같은 검사를 받는다** (`prereg-14` §8 A안) —
            # 라벨만 바꾸고 정렬이 안 따라가면 여기서 걸린다
            best_lo = max(s["net_lo"] for s in main_now)
            if (f"성과  확실히 받는 것 중 최고 {want}" in screen
                    and main_now[0]["net_lo"] < best_lo - EPS):
                bad.append({"assert": "A8", "product": main_now[0]["name"],
                            "session": tag, "step": step,
                            "detail": f"성과 줄이 '확실히 받는 것 중 최고' 라고 "
                                      f"쓰는데 1위 확정 "
                                      f"{main_now[0]['net_lo']:.2f}% 위에 "
                                      f"{best_lo:.2f}% 가 있다"})
        if st["answered"] != step:                                # A6
            bad.append({"assert": "A6", "product": "-", "session": tag, "step": step,
                        "detail": f"화면의 '답한 질문' {st['answered']} ≠ 실제 답한 수 {step}"})
        prev_left = st["left"]
        ordered = [(k, s) for k, s in C.rank_questions(scored, state)
                   if k not in state]
        if not ordered:
            break
        key, slot = ordered[0]
        # **질문 화면도 사용자가 읽는 화면이다** (F5). `급여_연금이체` 가 가장 크게
        # 보였던 자리가 여기다 — 최종 화면만 검사하면 이 자리가 검사 밖에 남는다
        head, qlines = L.prompt_for(key, slot)
        qtext = head + "\n" + "\n".join(qlines)
        for v in (check_words(qtext, "질문 화면")
                  + check_org_names(qtext, scored, "질문 화면")):
            bad.append({**v, "session": tag, "step": step})
        raw, kind = pick_answer(slot, rng, persona)
        if L.apply_answer(state, key, slot, raw, kind) == "bad":
            bad.append({"assert": "검사기", "product": "-", "session": tag, "step": step,
                        "detail": f"답을 못 넣었다: {key} ← '{raw}'"})
            break
    return bad


def run(stamp: str, group: str, term: int, seeds: int,
        company: str | None = None, kinds: str | None = None,
        prefs: dict | None = None, order: str = "hi") -> dict:
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
    if prefs:
        print(f"선호 {prefs.get('_answers')} — A10·A11 도 검사한다")
    print(f"정렬 {order} — "
          f"{'다 채웠을 때 순' if order == 'hi' else '확정된 값 순'}"
          f"  (`0017` · `prereg-14` §8). 두 정렬을 다 돌아야 한다")
    print("검사 대상 화면은 ask_loop.render_final_screen() — 중단하면 보는 그 화면이다\n")

    t0 = time.monotonic()
    bad, n_states = [], 0
    # 비교 리포트(F1) — 네 상태에서 렌더 구조를 본다 (이슈 #33)
    # **목록 키는 모양이 다르다** (F6) — 기관 목록이거나 "모름" 이다. 여기에 `True` 를
    # 넣으면 `answer_of()` 가 기관을 목록에서 찾다가 터진다
    banks_all = sorted({r.get("company") or "" for r in rows if r.get("company")})
    def _st(v, banks):
        s = {k: v for k in plan if k != C.TRADED_KEY}
        if C.TRADED_KEY in plan:
            s[C.TRADED_KEY] = banks
        return s
    for tag, st0 in (("리포트·미응답", {}),
                     ("리포트·전부예", _st(True, banks_all)),
                     ("리포트·전부아니오", _st(False, [])),
                     ("리포트·전부모름", _st(C.UNSURE, C.UNSURE))):
        scored0 = AB.score_all(rows, by_pair, st0, tax)
        if prefs:
            P.annotate(scored0, prefs)
        rep_bad = check_report(scored0, 5, prefs, tag)
        web_bad = check_web(scored0, plan, st0, total, prefs,
                            tag.replace("리포트", "웹"), order=order)
        bad += rep_bad + web_bad
        print(f"  {tag:<16}리포트 {len(rep_bad)}건 · 웹 {len(web_bad)}건")
    for persona in ("예", "아니오", "모름"):
        out = walk(rows, by_pair, plan, total, tax, persona=persona,
                   rows_all=rows_all, prefs=prefs, order=order)
        n_states += max(s["step"] for s in out) + 1 if out else total + 1
        bad += out
        print(f"  페르소나 {persona:<4} 위반 {len(out)}건")
    for seed in range(seeds):
        bad += walk(rows, by_pair, plan, total, tax, seed=seed,
                    rows_all=rows_all, prefs=prefs, order=order)
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
                       ("A9", "가입 채널 표시가 원천과 일치한다"),
                       ("A10", "가중치가 보이고 고칠 수 있다"),
                       ("A11", "가중치는 정렬만 바꾼다"),
                       ("A12", "금리 옆에 `세후` 라벨이 있다"),
                       ("A13", "화면이 자기가 무엇인지 밝힌다"),
                       ("A14", "내부 이름이 화면에 없다"),
                       ("A15", "행동 조건에 기댄 금리는 전제를 말한다")):
        if name in ("A10", "A11") and not prefs:
            print(f"  {name} {text:<35}검사 안 함 (--prefs 없음)")
            continue
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
            "order": order,
            "questions_total": total, "products": len(rows),
            "violations": bad,
            "summary": {k: len(v) for k, v in sorted(codes.items())}}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, seeds = "bank", 12, SEEDS
    company, kinds, prefs_arg = None, None, None
    orders = ["hi", "lo"]          # 기본은 **둘 다** — 새 경로를 검사 밖에 두지 않는다
    for flag in ("--group", "--term", "--seeds", "--company", "--kind", "--prefs",
                 "--order"):
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
            prefs_arg = v if flag == "--prefs" else prefs_arg
            orders = [v] if flag == "--order" else orders
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/check_screen_contract.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--seeds 200] "
                         "[--company 우리] [--kind 적금] [--prefs 확실성=많이] "
                         "[--order hi|lo · 안 주면 둘 다]")
    for o in orders:
        if o not in ("hi", "lo"):
            raise SystemExit("--order 는 hi 또는 lo 다")
    prefs = P.parse(prefs_arg)
    # **두 정렬을 다 돈다** — `prereg-14` §8 로 정렬이 사용자에게 노출됐다.
    # 한쪽만 검사하면 노출한 쪽이 검사 밖에 남는다
    for o in orders:
        report = run(argv[0], group, term, seeds, company, kinds, prefs, o)
        tag = ("_prefs" if prefs else "") + ("" if o == "hi" else "_lo")
        out = C.OUT_DIR / f"screen_contract_{group}_{argv[0]}_{term}m{tag}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"→ {out.relative_to(C.REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
