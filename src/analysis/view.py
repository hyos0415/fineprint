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
import companies as CO

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
            "company": C.org_label(best_out.get("company") or ""),      # 화면 표기 (F5)
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
        adj = "선호와 안 맞음"          # 옛 `선호밖` — 만든 사람만 아는 말이었다 (F5)
    elif s.get("_adj"):
        adj = f"조정 {s['_adj']:+.2f}%p"
    else:
        adj = ""
    return {
        "이름": s["name"],
        # 화면 표기 — 공시 이름의 법인 형태를 뗀다 (F5). **신원은 `company` 가 진다**
        "기관": C.org_label(s.get("company") or ""),
        "범위": L.span(s),          # 같을 때만 숫자 하나다 (A1)
        "채널": s.get("channel") or "",
        "남은": left,
        "조정": adj,
        "조정_사유": s.get("_why") or [],
        # **사유와 층을 라벨로 낸다** (F5 · 이슈 #45). 옛 화면은 코드를 그대로 태그로
        # 썼다 — `주의:미응답` · 층 칸에 `추출불확실`. 코드는 상태 dict·세션 로그의
        # 키라서 못 바꾸므로(`0031`), **표를 옆에 두고 화면만 라벨을 읽는다**
        #
        # **코드는 여기 다시 담지 않는다.** 검사·로그는 상품 dict 의 `caveats`·`tier` 를
        # 그대로 읽는다 — 아무도 안 읽는 칸을 늘리면 그게 드리프트가 자라는 자리다(`0039`)
        "주의": [C.caveat_label(c) for c in (s.get("caveats") or [])],
        "층": C.tier_label(s["tier"]),
        # 같은 상품의 다른 행 — 적립방식·단리복리와 그 행의 범위 (`prereg-18` §2.3 · A16)
        "다른_행": [f"{variant_label(o)} {L.span(o)}" for o in (s.get("_다른_행") or [])],
        # 기관 홈페이지·대표전화 (F3 · `prereg-21` · A17). **기관 코드로 짝짓는다.** 링크는
        # 정보이고 가입은 기관에서 한다(`0037`) — 사유 문장이 "은행에 확인해 보세요" 로 끝나는데
        # 갈 곳이 없던 자리다. 스킴 보정은 `companies.link()` 한 곳이고, 웹의 `href` 와 CLI 의
        # 한 줄이 같은 이 칸을 읽는다. 짝이 없으면 빈 칸이다 — 다른 곳에서 채우지 않는다
        **CO.contact(s),
    }


def variant_label(s: dict) -> str:
    """행의 갈래 이름 — `정액적립식 · 단리`. 공시 칸 그대로라 빈 칸은 뺀다."""
    return " · ".join(x for x in (s.get("rsrv_type") or "", s.get("rate_type") or "") if x) \
        or "다른 조건"


def next_question(scored: list[dict], state: dict) -> tuple[str | None, dict | None]:
    """다음에 물을 질문 하나. **순서 규칙은 `rank_questions` 가 정한다** (`0018`).

    **CLI 루프와 뷰 모델이 같은 함수를 쓴다** (F4-1 · 이슈 #38). 옛 루프는 자기
    자리에서 `rank_questions` 를 불러 첫 항목을 집었고, 뷰 모델에는 질문 **수**만
    있었다. 웹이 "다음 질문이 무엇인가" 를 물으면 그 자리가 둘로 갈라진다 —
    `0039` 반증 조건이 *"칸을 늘리되 CLI 렌더러도 그 칸을 쓰게 한다"* 로 미리
    적어 둔 자리다.
    """
    for key, slot in C.rank_questions(scored, state):
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
            "기관": " · ".join(sorted(C.org_label(o) for o in src.get(ev, set()) if o))}
           for ev in sorted(slot["evidence"])]
    # **질문 문장을 뷰 모델이 만든다** (F6). 전에는 CLI 와 웹이 각자 만들었는데,
    # 기관이 붙은 뒤로 그러면 한쪽이 *"자동이체 — 충족하십니까"* 라고만 물어
    # **어느 은행 이야기인지 사라진다**. `0039` 가 막은 자리와 같은 모양이다.
    # 상태 키에는 **공시 이름**이 들어 있다(신원). 화면에는 표기 이름을 쓴다 (F5)
    기관_원천 = key.partition("#")[0].partition("@")[2]
    기관 = C.org_label(기관_원천)
    꼬리 = f" · {기관}" if 기관 else ""
    if slot["unit"] == C.LIST_UNIT:                       # 목록 질문 (F6)
        return {
            "key": key,
            "유형": slot["kind"],
            "단위": slot["unit"],
            "질문": "거래해 본 은행을 골라 주세요 — 여러 곳을 고를 수 있습니다",
            "설명": "고르지 않은 은행은 '첫 거래' 로, 그 은행에서의 실적 조건은 "
                    "'아니오' 로 채워집니다 — 거래가 없으면 실적이 있을 수 없습니다",
            "문구": [],
            "여는_상품수": len(slot["products"]),
            # `선택지` 는 **화면에 보일 이름**이고, 답으로 돌려보낼 것은 `값` 이다 —
            # 상태에는 공시 이름이 들어가야 `answer_of()` 가 상품의 기관과 짝짓는다
            "선택지": [C.org_label(b) for b in slot["기관"]],
            "값": list(slot["기관"]),
            "다중": True,
            # 버튼 셋 (이슈 #48 · `prereg-16` §6). **"거래한 곳이 없다" 는 명시적 답이다** —
            # 3런에서 빈 제출이 답이라는 것을 안내문으로 적었더니 사람은 "모르겠습니다"
            # 하나만 고를 수 있는 것으로 읽었다. 빈 채로 "고른 대로 계속" 은 넘어가지
            # 않는다(서버가 막고 `빈_제출_안내` 를 그대로 낸다). CLI 도 이 라벨을 읽는다
            "버튼": [{"값": "고름", "라벨": "고른 대로 계속"},
                     {"값": "없음", "라벨": "거래해 본 은행이 없습니다"},
                     {"값": "모름", "라벨": "모르겠습니다"}],
            "빈_제출_안내": "은행을 하나 이상 고르거나, 거래해 본 은행이 없으면 "
                          "'거래해 본 은행이 없습니다' 를 눌러 주세요",
            "모름_안내": "'모르겠습니다' 를 고르면 채워 넣지 않고 은행마다 따로 여쭙습니다 "
                       "— 질문이 많이 늘어납니다",
        }
    # **내부 이름을 질문 문장에 넣지 않는다** (F5 · 이슈 #45). 옛 화면은
    # `급여_연금이체 — 이 조건을 충족하십니까?` 라고 물었다 — 만든 사람만 아는 말이다
    #
    # 기관은 **라벨 안의 `이 기관` 자리**에 들어간다. 꼬리로 붙이면
    # *"이 기관의 다른 상품 가입·보유 · 국민은행"* 이 되어 두 번 읽어야 한다
    이름 = C.type_label(slot["kind"], 기관)
    붙었다 = 기관 and 기관 in 이름
    꼬리 = "" if 붙었다 else 꼬리
    # **시제가 갈린다** (이슈 #50 · `prereg-17`). 상태 조건은 "해당되십니까", 행동 조건은
    # "하실 건가요", 섞인 유형은 둘을 병기한다. 옛 문장 "충족하십니까" 는 가입 뒤 할 일에
    # 쓰면 틀린 질문이었다 — 사람이 3런에서 짚었다
    꼬리말 = C.ask_tail(slot["kind"])
    if "#" in key and not slot.get("직접"):
        # 원문 재질문 (이슈 #52). 옛 문장 *"위는 공시 문구 원문입니다"* 는 3런에서 안 읽혔다
        # (M3 ≥ 2) — 왜 같은 조건을 다시 묻는지가 없었다. 이 질문은 유형에 "예" 라고 답한
        # 뒤에만 나오고(`0024` P4), 문구에 기준(금액·횟수·기간)이 있어 따로 확인하는 것이다
        질문 = (f"아까 '{이름}{꼬리}' 에 예라고 하셨는데, 이 문구는 기준이 있어 "
                f"따로 여쭙습니다 — {꼬리말}")
    else:
        질문 = f"{이름}{꼬리} — {꼬리말}"
    return {
        "key": key,
        "유형": slot["kind"],
        "단위": slot["unit"],
        "질문": 질문,
        "설명": "",
        "문구": 문구,
        "여는_상품수": len(slot["products"]),
        "선택지": ["예", "아니오", "모름"],
        "값": ["예", "아니오", "모름"],
        "다중": False,
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
    # **같은 상품은 한 줄이다** (`0031` · `prereg-18` §2.3). 대표는 지금 정렬에서 가장
    # 위에 오는 행이고, 나머지 행(적립방식·단리복리)은 그 줄 아래에 **전부** 적는다 —
    # 숫자를 버리지 않는다. 지표(확정률·폭·게이트)는 행 단위 그대로다(`0031` 3항).
    # `_다른_행` 은 `P.annotate()` 의 `_adj` 처럼 화면용 주석이다 — 매 build 마다 새로 쓴다
    folded: list[dict] = []
    first: dict[tuple, dict] = {}
    for s in main:
        pk = C.product_key(s)
        if pk in first:
            first[pk]["_다른_행"].append(s)
        else:
            s["_다른_행"] = []
            first[pk] = s
            folded.append(s)
    shown = folded[:top] if top else folded
    _bar, st = L.status_lines(plan, state, scored, total, start, prefs, order)

    tally = {}
    for s in rest:
        tally[s["tier"]] = tally.get(s["tier"], 0) + 1
    # 층 라벨로 센 것도 같이 담는다 (F5) — 렌더러가 각자 라벨을 붙이면 세 곳이 갈라진다
    tally_label = {C.tier_label(t): n for t, n in sorted(tally.items())}

    # 화면에 문장으로 나가야 하는 사유 — **코드가 아니라 문장**이다 (`0016` · A3)
    #
    # **`shown`(상위 N개)이 아니라 `main`(메인 전부)에서 모은다.** 목록은 잘라 보여줘도
    # 사유 문장은 메인 전체 것을 낸다 — 옛 코드가 그렇게 했고 화면 계약 A3 도 메인
    # 전체를 본다. 여기서 `shown` 으로 좁히면 화면에서 문장이 사라진다
    codes = [c for c in C.CAVEAT if any(c in s.get("caveats", []) for s in main)]
    # **코드와 라벨과 문장을 한 자리에 담는다** (F5). 코드는 검사·로그가 읽고, 라벨과
    # 문장은 화면이 읽는다 — 목록을 둘로 나누면 서로 다른 말을 하게 된다(`0035`)
    return {
        "meta": {
            "세후_라벨": L.tax_label(scored),      # A12 — 세율은 config 에서 온다
            "고지": C.NOTICE,                      # A13 — `0035`
            "세율": shown[0]["tax_rate"] if shown else None,
            # 이 화면이 무슨 순서인지 — 렌더러가 사용자에게 그대로 말한다
            "정렬": order,
            # 남기고 **설명만 붙이는** 낱말 (F5 · 이슈 #45). `%p` 는 정확해서 필요하다 —
            # 없애면 흐려지므로 첫 등장에서 풀어 준다
            "%p 설명": C.PP_NOTE,
            "우대조건 설명": C.BONUS_NOTE,
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
        "메인밖": {"수": len(rest), "층별": tally, "층별_라벨": tally_label},
        "questions": {"남은": st["left"], "답한": st["answered"],
                      "지금_총": st["total_now"], "처음_총": total,
                      # 다음에 물을 질문 하나. 없으면 None (더 물을 게 없다)
                      "현재": question_card(*next_question(scored, state))},
        "notices": {
            "사유": [{"코드": c, "라벨": C.caveat_label(c), "문장": C.CAVEAT[c]}
                   for c in codes],                             # A3 · F5
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
    have = {r["코드"] for r in vm["notices"]["사유"]}
    for s in vm["products"]:
        for c in s.get("caveats", []):
            if c not in have:
                hit("A3", s["name"], f"사유 {c} 의 문장이 뷰 모델에 없다")
    for r in vm["notices"]["사유"]:
        if not r["문장"]:
            hit("A3", "-", f"사유 {r['코드']} 의 문장이 비어 있다")
        # A14 — 코드가 아니라 **사람 말**이 화면으로 가야 한다 (F5 · 이슈 #45)
        if not r["라벨"] or r["라벨"] == r["코드"]:
            hit("A14", "-", f"사유 {r['코드']} 의 사용자용 라벨이 없다")

    # A16 — 같은 상품이 목록에 두 줄 없다 (`0031` · `prereg-18` §2.3)
    seen_pk: dict = {}
    for s in vm["products"]:
        pk = C.product_key(s)
        if pk in seen_pk:
            hit("A16", s["name"], f"같은 상품이 두 줄이다 — {seen_pk[pk]['rate_type']}/"
                                   f"{seen_pk[pk]['rsrv_type']} 와 {s['rate_type']}/{s['rsrv_type']}")
        seen_pk.setdefault(pk, s)

    # A17 — 기관 홈페이지·대표전화의 **재료**가 있고 URL 이 API 값에서 스킴만 보정된 것인가
    # (F3 · `prereg-21`). 사전에 없는 기관은 여기서 드러난다 — 화면은 빈 칸으로 내지만
    # (`prereg-20` §4) 빈 칸이 생긴 사실은 검사가 말해야 한다. 렌더러가 그렸는지는 렌더 겹이 본다
    for s in vm["products"]:
        d = display(s)
        if not d["홈페이지"] or not d["전화"]:
            hit("A17", s["name"], f"기관 {s.get('co_no') or '-'} 의 홈페이지·전화가 사전에 없다")
        elif not CO.is_faithful(d["홈페이지"], d["홈페이지_원천"]):
            hit("A17", s["name"], f"화면 URL {d['홈페이지']} 이 API 값 {d['홈페이지_원천']} 에서 "
                                  f"스킴 보정 이상으로 바뀌었다")
        # 링크가 가는 기관(코드)과 화면에 적힌 기관(이름)이 **같은 곳**이어야 한다. 다르면 링크가
        # 이름과 다른 은행으로 간다 — `prereg-21` 측정에서 실제로 잡혔다(저축은행 · 추출이 상품코드만으로
        # 기관을 넘어 짝지은 행). 원인은 추출 쪽이고 여기서 고치지 않는다 — 검사는 사실만 말한다
        기관_이름 = CO.name_of(s.get("co_no") or "")
        if 기관_이름 and 기관_이름 != (s.get("company") or ""):
            hit("A17", s["name"], f"행의 기관 코드 {s.get('co_no')} 는 {기관_이름} 인데 "
                                  f"화면 이름은 {s.get('company')} 다 — 링크가 이름과 다른 곳으로 간다")

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
    # A14 — 남기기로 한 낱말은 **풀어 줄 재료**가 뷰 모델에 있어야 한다 (F5)
    for 칸 in ("%p 설명", "우대조건 설명"):
        if not vm["meta"].get(칸):
            hit("A14", "-", f"{칸} 이 뷰 모델에 없다 — 낱말을 풀어 줄 수 없다")
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
        if not cur.get("질문"):
            hit("A3", cur["key"], "물을 질문에 질문 문장이 없다")
        if cur["다중"]:
            # **목록 질문** (F6) — 문구가 아니라 기관 목록이 선택지다. 무엇이 유도되는지
            # 화면이 말해야 한다: 안 고른 기관의 답을 우리가 채우기 때문이다
            if not cur["선택지"]:
                hit("A3", cur["key"], "목록 질문에 고를 은행이 없다")
            if len(cur["선택지"]) != len(cur["값"]):
                hit("A3", cur["key"],
                    f"보일 이름 {len(cur['선택지'])}개 ≠ 답할 값 {len(cur['값'])}개")
            if not cur.get("설명"):
                hit("A3", cur["key"], "목록 질문에 무엇이 유도되는지 설명이 없다")
            # **"거래한 곳이 없다" 가 버튼이어야 한다** (이슈 #48). 안내문으로만 있으면
            # 사람은 "모르겠습니다" 를 고른다 — 3런에서 실제로 그랬다
            if [b["값"] for b in cur.get("버튼", [])] != ["고름", "없음", "모름"]:
                hit("A3", cur["key"], "목록 질문의 버튼이 고름·없음·모름 셋이 아니다")
            if not cur.get("빈_제출_안내"):
                hit("A3", cur["key"], "빈 제출을 막았을 때 보여줄 안내가 없다")
        else:
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
            # **기관 상대 조건이면 어느 기관인지 질문에 있어야 한다** (F6) — 없으면
            # 사용자가 "당행" 을 자기가 아는 은행으로 읽는다
            기관 = C.org_label(cur["key"].partition("#")[0].partition("@")[2])
            if 기관 and 기관 not in cur["질문"]:
                hit("A3", cur["key"], f"질문에 기관({기관})이 없다: {cur['질문']}")
    return bad
