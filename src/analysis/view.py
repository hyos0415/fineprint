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


def outside_best(rows_all: list[dict], rows_in: list[dict], by_pair: dict,
                 state: dict, tax: dict) -> dict | None:
    """**스코프 밖 최고 금리** — 화면 계약 A7 (`decisions/0028` S4 · `prereg-11` §2).

    **2026-09-01 에 `ask_loop`(렌더러)에서 여기로 옮겼다** (F4-1 · 이슈 #38).
    이 함수는 그리는 것이 아니라 **사실을 만든다** — 서버도 CLI 도 같은 사실을
    써야 하는데 렌더러에 있으면 서버가 CLI 모듈을 import 하게 된다.

    좁히면 금리를 잃는다. 은행권 실측으로 기관별 격차 **중앙값 2.41%p**, 16곳 중
    15곳이 1.0%p 초과다. 안 보여주면 `0017` 이 막은 실패("좋은 상품이 묻힌다")를
    스코프에서 되살린다. 그래서 밖에 무엇이 있는지를 항상 같이 말한다.

    비교는 **조건을 다 채웠을 때(hi)** 로 한다 — 밖의 상품은 질문을 안 했으므로
    답을 받은 상태가 없다. 화면에도 "조건 다 채웠을 때" 라고 적어야 한다.
    """
    import ask_budget as AB

    inside_keys = {C.row_key(r) for r in rows_in}     # 행 단위 (`prereg-13`)
    outs = [r for r in rows_all if C.row_key(r) not in inside_keys]
    if not outs:
        return None
    best_out = max(AB.score_all(outs, by_pair, state, tax),
                   key=lambda s: s["net_hi"], default=None)
    inside = AB.score_all(rows_in, by_pair, state, tax) if rows_in else []
    best_in = max((s["net_hi"] for s in inside), default=0.0)
    if best_out is None or best_out["net_hi"] <= best_in + 1e-9:
        return None                      # 숨길 것이 없다 — 밖이 더 좋지 않다
    return {"name": best_out["name"], "net_hi": best_out["net_hi"],
            "gap": round(best_out["net_hi"] - best_in, 3),
            "company": best_out.get("company") or "",
            "channel": best_out.get("channel") or ""}


def display(s: dict) -> dict:
    """상품 한 줄이 **무엇을 어떻게 보여줄지**. 렌더러가 이걸 꽂기만 한다.

    **판정을 템플릿에 넣지 않으려고 만들었다** (F4-2 · `0038` 반증 조건).
    `{% if 폭이 있으면 범위로 %}` 를 템플릿이 하기 시작하면 화면 계약이 뷰 모델
    밖으로 샌다 — F4-0 이 계약을 객체로 옮긴 일이 무의미해진다.

    CLI 의 `product_line` 과 웹 템플릿이 **같은 이 함수**를 읽는다. 한쪽만 쓰는
    칸을 만들지 않는다(`0039` 반증 조건 1).

    돌려주는 값은 전부 **이미 정해진 문자열**이다 — 렌더러는 배치만 정한다.
    """
    import ask_loop as L

    # 남은 조건 수 — **금리에 영향이 없으면 그렇게 적는다** (`0017` 부수 정리)
    if s["net_hi"] > s["net_lo"]:
        left = f"남은 {s['n_unknown']}개"
    elif s["n_unknown"]:
        left = f"남은 {s['n_unknown']}개 (금리 영향 없음)"
    else:
        left = "확정"
    # 선호 조정 — **금리 칸이 아니라 별도 칸이다** (`prereg-12` §3 · A11)
    if s.get("_blocked"):
        adj = "선호밖"
    elif s.get("_adj"):
        adj = f"조정 {s['_adj']:+.2f}%p"
    else:
        adj = ""
    return {
        "이름": s["name"],
        "기관": s.get("company") or "",
        "범위": L.span(s),          # 같을 때만 숫자 하나다 (A1)
        "채널": s.get("channel") or "",
        "남은": left,
        "조정": adj,
        "조정_사유": s.get("_why") or [],
        "주의": list(s.get("caveats") or []),
        "층": s["tier"],
    }


def next_question(scored: list[dict], state: dict) -> tuple[str | None, dict | None]:
    """다음에 물을 질문 하나. **순서 규칙은 `rank_questions` 가 정한다** (`0018`).

    **CLI 루프와 뷰 모델이 같은 함수를 쓴다** (F4-1 · 이슈 #38). 옛 루프는 자기
    자리에서 `rank_questions` 를 불러 첫 항목을 집었고, 뷰 모델에는 질문 **수**만
    있었다. 웹이 "다음 질문이 무엇인가" 를 물으면 그 자리가 둘로 갈라진다 —
    `0039` 반증 조건이 *"칸을 늘리되 CLI 렌더러도 그 칸을 쓰게 한다"* 로 미리
    적어 둔 자리다.
    """
    for key, slot in C.rank_questions(scored):
        if key not in state:
            return key, slot
    return None, None


def question_card(key: str | None, slot: dict | None) -> dict | None:
    """질문 하나를 화면이 쓸 모양으로. **JSON 으로 그대로 나갈 수 있어야 한다.**

    `slot["products"]`·`needs`·`evidence` 는 `set` 이라 JSON 이 안 된다 — 여기서
    정렬된 리스트와 개수로 바꾼다.

    **공시 문구를 자르지 않는다** (`0027` · `prereg-10` §6) — 문구를 자르면 조건이
    달라진다. 선택지도 셋뿐이다(`0027`).
    """
    if key is None or slot is None:
        return None
    # **문구마다 어느 기관 것인지 붙인다** (2026-09-02) — "당행" 이 가리킬 대상이
    # 없으면 사용자가 답을 고를 수 없다. 같은 문구를 여러 기관이 쓰면 전부 적는다.
    src = slot.get("출처") or {}
    문구 = [{"문구": ev,
            "기관": " · ".join(sorted(o for o in src.get(ev, set()) if o))}
           for ev in sorted(slot["evidence"])]
    return {
        "key": key,
        "유형": slot["kind"],
        "단위": slot["unit"],
        "문구": 문구,
        "여는_상품수": len(slot["products"]),
        "선택지": ["예", "아니오", "모름"],
    }


def build(scored: list[dict], plan: dict, state: dict, total: int,
          top: int | None = None, outside: dict | None = None,
          total_all: int | None = None, start: dict | None = None,
          prefs: dict | None = None, order: str = "hi") -> dict:
    """화면 하나가 내놓을 것 전부.

    인자는 `ask_loop.render_final_screen()` 과 같다 — 그 함수가 이것을 부르고,
    웹 렌더러도 같은 것을 받는다.
    """
    import ask_loop as L                # 렌더 쪽 헬퍼. 순환을 피해 여기서만 부른다
    import prefs as P

    main = L.ranked(scored, prefs, order)
    rest = [s for s in scored if s["tier"] not in C.MAIN_TIERS]
    shown = main[:top] if top else main
    _bar, st = L.status_lines(plan, state, scored, total, start, prefs, order)

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
            # 이 화면이 무슨 순서인지 — 렌더러가 사용자에게 그대로 말한다
            "정렬": order,
        },
        # A4·A6 이 읽는 것. **이미 뷰 모델이었다** — `status_lines()` 가 돌려준다
        "progress": st,
        "headline": {
            # A8 — 성과 줄은 **목록 1위와 같아야** 한다. 낱말도 사실이어야 한다(`0030`).
            # 낱말은 `status_facts()` 가 정한다 — 여기서 또 정하면 CLI 와 갈라진다
            "라벨": st["성과_라벨"],
            "상품": main[0] if main else None,
            "폭_시작": (start or {}).get("width"),
        },
        "products": shown,                          # 복사하지 않는다 — 같은 객체다
        "메인밖": {"수": len(rest), "층별": tally},
        "questions": {"남은": st["left"], "답한": st["answered"],
                      "지금_총": st["total_now"], "처음_총": total,
                      # 다음에 물을 질문 하나. 없으면 None (더 물을 게 없다)
                      "현재": question_card(*next_question(scored, state))},
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
        # **확정된 값 순 화면도 같은 검사를 받는다** (`prereg-14` §8 · A안).
        # 라벨만 바꾸고 정렬이 안 따라가면 여기서 걸린다
        best_lo = max((s["net_lo"] for s in prods), default=None)
        if (vm["headline"]["라벨"] == "확실히 받는 것 중 최고"
                and best_lo is not None
                and head["net_lo"] < best_lo - 0.005):
            hit("A8", head["name"],
                f"라벨이 '확실히 받는 것 중 최고' 인데 1위 확정 "
                f"{head['net_lo']:.2f}% 위에 {best_lo:.2f}% 가 있다")

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

    # 질문 칸 — 남은 질문이 있으면 **무엇을 물을지**가 담겨야 한다 (F4-1)
    cur = q.get("현재")
    if q["남은"] > 0 and cur is None:
        hit("A6", "-", f"남은 질문이 {q['남은']}개인데 물을 질문이 담기지 않았다")
    if q["남은"] == 0 and cur is not None:
        hit("A6", "-", "남은 질문이 0인데 물을 질문이 담겼다")
    if cur is not None:
        # **공시 문구가 있어야 한다** — 사용자가 판단할 근거다 (`0027`).
        # 문구가 없는 조건은 `조건불명` 으로 질문이 안 만들어지므로 여기 오면 결함이다
        if not cur["문구"]:
            hit("A3", cur["key"], "물을 질문에 공시 문구가 없다")
        # **문구에 기관이 붙어 있나** — 없으면 "당행" 이 가리킬 대상이 없다
        for f in cur["문구"]:
            if not f.get("기관"):
                hit("A3", cur["key"],
                    f'문구에 기관이 없다: "{f["문구"][:40]}…"')
        if cur["선택지"] != ["예", "아니오", "모름"]:
            hit("A3", cur["key"], f"선택지가 셋이 아니다: {cur['선택지']}")
    return bad
