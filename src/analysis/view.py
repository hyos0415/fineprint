# -*- coding: utf-8 -*-
"""뷰 모델 — 화면이 내놓아야 하는 것 전부를 한 덩이로 모은다.

이 파일이 채우는 자리
    화면 계약 A1~A13 이 **렌더된 CLI 문자열을 grep** 하고 있었다.

        if "%" in screen and "세후" not in screen:       # A12
        if C.CAVEAT[code] not in screen:                 # A3
        if f"{outside['net_hi']:.2f}%" not in screen:    # A7

    웹으로 옮기면(F4) 이 검사가 **전부 무의미해진다.** 그리고 이 저장소가 찾은 실패는
    거의 다 화면에서 나왔다 — `0019`(조건이 한 글자도 없는데 4.80% 가 확정처럼 보였다) ·
    `0026`(중단 지점 화면) · `0029`(진행 바밖에 안 보인다) · `0035`(`세후` 라벨이
    `calculate.py` 목록에는 있고 질문 루프 화면에는 없었다).

    그래서 UI 를 쓰기 전에 계약을 옮긴다 (이슈 #33 → #36 · `ui-plan.md` F4-0).

무엇을 하나 — 계약을 두 겹으로 가른다
    build()         화면이 쓸 것을 모은다. **렌더러가 이걸 거쳐 간다**
    check_model()   뷰 모델에 필요한 **사실**이 담겼나 (렌더러와 무관)
    (렌더 검사)      렌더러가 그 사실을 실제로 **출력**했나 — `check_screen_contract`

    **문자열 검사를 없애지 않는다.** 뷰 모델에 `net_lo`·`net_hi` 가 둘 다 있어도
    렌더러가 하나만 출력하면 A1 위반이고, 그건 객체를 봐서는 못 잡는다. `0035` 가
    찾은 실패가 정확히 그 모양이었다 — **데이터는 있고 한 화면에만 라벨이 없었다.**

무엇을 **안** 하나
    - **상품 dict 를 복사하지 않는다.** `products` 는 `evaluate()` 가 낸 그 객체다.
      복사하면 뷰 모델과 화면이 서로 다른 값을 들 수 있다 — 드리프트가 생기는 자리다
    - **Pydantic 을 쓰지 않는다.** 의존성 추가는 F4-1 의 일이다(`0038`). 여기는
      표준 라이브러리로 끝낸다
    - **숫자를 다시 계산하지 않는다.** `0036` 이 리포트에 정한 것과 같다
"""
from __future__ import annotations

import calculate as C

EPS = 1e-6


def build(scored: list[dict], plan: dict, state: dict, total: int,
          top: int | None = None, outside: dict | None = None,
          total_all: int | None = None, start: dict | None = None,
          prefs: dict | None = None) -> dict:
    """화면 하나가 내놓을 것 전부.

    인자는 `ask_loop.render_final_screen()` 과 같다 — 그 함수가 이것을 부르고,
    웹 렌더러도 같은 것을 받는다.
    """
    import ask_loop as L                # 렌더 쪽 헬퍼. 순환을 피해 여기서만 부른다
    import prefs as P

    main = L.ranked(scored, prefs)
    rest = [s for s in scored if s["tier"] not in C.MAIN_TIERS]
    shown = main[:top] if top else main
    _bar, st = L.status_lines(plan, state, scored, total, start, prefs)

    tally = {}
    for s in rest:
        tally[s["tier"]] = tally.get(s["tier"], 0) + 1

    # 화면에 문장으로 나가야 하는 사유 — **코드가 아니라 문장**이다 (`0016` · A3)
    #
    # **`shown`(상위 N개)이 아니라 `main`(메인 전부)에서 모은다.** 목록은 잘라 보여줘도
    # 사유 문장은 메인 전체 것을 낸다 — 옛 코드가 그렇게 했고 화면 계약 A3 도 메인
    # 전체를 본다. 여기서 `shown` 으로 좁히면 화면에서 문장이 사라진다
    codes = [c for c in C.CAVEAT if any(c in s.get("caveats", []) for s in main)]
    return {
        "meta": {
            "세후_라벨": L.tax_label(scored),      # A12 — 세율은 config 에서 온다
            "고지": C.NOTICE,                      # A13 — `0035`
            "세율": shown[0]["tax_rate"] if shown else None,
        },
        # A4·A6 이 읽는 것. **이미 뷰 모델이었다** — `status_lines()` 가 돌려준다
        "progress": st,
        "headline": {
            # A8 — 성과 줄은 **목록 1위와 같아야** 한다. 낱말도 사실이어야 한다(`0030`)
            "라벨": "1위" if prefs else "최고",
            "상품": main[0] if main else None,
            "폭_시작": (start or {}).get("width"),
        },
        "products": shown,                          # 복사하지 않는다 — 같은 객체다
        "메인밖": {"수": len(rest), "층별": tally},
        "questions": {"남은": st["left"], "답한": st["answered"],
                      "지금_총": st["total_now"], "처음_총": total},
        "notices": {
            "사유": [(c, C.CAVEAT[c]) for c in codes],       # A3
            "스코프밖": outside,                              # A7
            "넓히면_질문": total_all,
        },
        "prefs": {"적용": prefs or {},
                  "막힌_상품": sum(1 for s in main if s.get("_blocked"))},
    }


def check_model(vm: dict) -> list[dict]:
    """**뷰 모델에 사실이 담겼나.** 렌더러가 무엇이든 이 검사는 같다.

    여기서 잡는 것은 "화면이 못 보여줄 수밖에 없는 상태" 다 — 데이터가 아예 없으면
    어떤 렌더러도 계약을 못 지킨다. 반대로 **데이터가 있는데 안 그린 것**은 여기서
    안 잡히고 렌더 검사가 잡는다.
    """
    bad = []

    def hit(code: str, product: str, detail: str) -> None:
        bad.append({"assert": code, "product": product, "detail": f"[모델] {detail}"})

    # A1 — 범위를 낼 수 있는 재료가 있나. 한쪽만 있으면 화면은 단일 숫자밖에 못 쓴다
    for s in vm["products"]:
        for k in ("net_lo", "net_hi", "gross_lo", "gross_hi"):
            if not isinstance(s.get(k), (int, float)):
                hit("A1", s.get("name", "-"), f"{k} 가 없다 — 범위를 만들 수 없다")
        if s.get("net_lo") is not None and s.get("net_hi") is not None \
                and s["net_lo"] > s["net_hi"] + EPS:
            hit("A1", s["name"], f"net_lo {s['net_lo']} > net_hi {s['net_hi']}")

    # A3 — 화면에 붙은 사유마다 **문장**이 담겼나. 코드만 있으면 사용자는 못 읽는다
    have = {c for c, _t in vm["notices"]["사유"]}
    for s in vm["products"]:
        for c in s.get("caveats", []):
            if c not in have:
                hit("A3", s["name"], f"사유 {c} 의 문장이 뷰 모델에 없다")
    for c, text in vm["notices"]["사유"]:
        if not text:
            hit("A3", "-", f"사유 {c} 의 문장이 비어 있다")

    # A8 — 성과 줄의 재료가 목록 1위와 같은 객체인가
    head, prods = vm["headline"]["상품"], vm["products"]
    if prods and head is not prods[0]:
        hit("A8", "-", "headline 이 목록 1위와 다른 객체다")
    if head is not None:
        best = max((s["net_hi"] for s in prods), default=None)
        if vm["headline"]["라벨"] == "최고" and best is not None \
                and head["net_hi"] < best - 0.005:
            hit("A8", head["name"],
                f"라벨이 '최고' 인데 1위 {head['net_hi']:.2f}% 위에 {best:.2f}% 가 있다")

    # A12·A13 — 라벨과 고지가 담겼나
    if vm["products"] and not vm["meta"]["세후_라벨"]:
        hit("A12", "-", "세후 라벨이 비어 있다")
    if "세후" not in (vm["meta"]["세후_라벨"] or ""):
        hit("A12", "-", "세후 라벨에 '세후' 가 없다")
    if vm["meta"]["고지"] != C.NOTICE:
        hit("A13", "-", "고지가 calculate.NOTICE 와 다르다")

    # A4·A6 — 진행 카운터의 재료
    q = vm["questions"]
    if q["답한"] + q["남은"] != q["지금_총"]:
        hit("A6", "-", f"답한 {q['답한']} + 남은 {q['남은']} != 총 {q['지금_총']}")
    return bad
