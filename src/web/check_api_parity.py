# -*- coding: utf-8 -*-
"""서버가 CLI 와 **같은 뷰 모델**을 내는가 — F4-1 의 완료 조건 3 (이슈 #38).

이 파일이 채우는 자리
    `problem.md` §7 이 *"계산은 전부 코드다"* 로 정한 것을 지키려면 **계산이 한 벌**
    이어야 한다. 서버는 `evaluate()`·`view.build()` 를 부르기만 하므로 원리상 같은
    답이 나오지만, **원리상 같다는 것과 실제로 같다는 것은 다르다** — 서버가 인자를
    하나 다르게 넘기면(예: `top` 기본값, 스코프 계산 순서) 조용히 갈라진다.

    `0035` 가 찾은 실패가 그 모양이었다 — 같은 문구를 두 곳에서 만들다가 한쪽만
    고쳤다. 그래서 **두 경로를 같은 입력으로 돌려 대조한다.**

무엇을 하나
    (가) 파이썬에서 직접 `view.build` 를 부른 결과
    (나) HTTP `POST /api/screen` 으로 받은 결과
    JSON 왕복에서 바뀌는 것(튜플 → 리스트)만 정규화하고 나머지는 그대로 비교한다.

    그리고 **에러 계약**을 본다 — CLI 는 `SystemExit` 로 죽어도 되지만 서버는 4xx 로
    답해야 한다. 없는 스냅샷 · 없는 기간 · 모르는 조건 유형 · 빈 스코프 · 잘못된 선호 ·
    모르는 필드 여섯이다.

사용법
    # 먼저 서버를 띄운다
    python -m uvicorn src.web.app:app --host 127.0.0.1 --port 8000
    # 다른 터미널에서
    python src/web/check_api_parity.py                 (기본 포트 8000)
    python src/web/check_api_parity.py --port 8137
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "analysis"))

import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402
import report as R  # noqa: E402
import view as V  # noqa: E402

# 대조할 입력 — 권역 둘 · 답 없음/있음/모름 · 스코프+선호 · 전체 목록
CASES = [
    ("미응답", {"snapshot": "20260826", "term": 12}),
    ("답 둘", {"snapshot": "20260826", "term": 12,
               "state": {"급여_연금이체": True, "카드실적": False}}),
    ("모름 섞임", {"snapshot": "20260826", "term": 12, "state": {"자동이체": "모름"}}),
    ("저축은행", {"snapshot": "20260825", "group": "savingsbank", "term": 12}),
    ("스코프+선호", {"snapshot": "20260826", "term": 12, "company": "우리",
                     "prefs": "영업점=되도록안간다,확실성=조금"}),
    ("전체 목록", {"snapshot": "20260826", "term": 12, "top": 500}),
    # 정렬 (`prereg-14` §8 A안). 노출한 경로는 대조도 받아야 한다
    ("확정된 값 순", {"snapshot": "20260826", "term": 12, "order": "lo"}),
    ("확정순+답 둘", {"snapshot": "20260826", "term": 12, "order": "lo",
                     "state": {"급여_연금이체": False, "카드실적": False}}),
    # 목록 질문 (F6 · `prereg-15`) — 답의 모양이 다른 유일한 질문이라 대조가 필요하다
    ("거래은행 1곳", {"snapshot": "20260826", "term": 12,
                   "state": {"_거래은행": ["국민은행"]}}),
    ("거래은행 없음", {"snapshot": "20260826", "term": 12,
                    "state": {"_거래은행": []}}),
    ("거래은행 모름", {"snapshot": "20260826", "term": 12,
                    "state": {"_거래은행": "모름"}}),
    ("기관별 답", {"snapshot": "20260826", "term": 12,
                 "state": {"_거래은행": ["국민은행", "신한은행"],
                           "카드실적@국민은행": True,
                           "주거래_장기거래_재예치@신한은행": True}}),
]

# 에러 계약 — (이름, 요청, 기대 코드). 422 는 Pydantic 이 요청 모양을 거른 것이다
ERRORS = [
    ("없는 스냅샷", {"snapshot": "20990101", "term": 12}, 400),
    ("없는 기간", {"snapshot": "20260826", "term": 7}, 400),
    ("모르는 정렬", {"snapshot": "20260826", "term": 12, "order": "middle"}, 422),
    ("모르는 조건", {"snapshot": "20260826", "term": 12, "state": {"없는조건": True}}, 400),
    ("빈 스코프", {"snapshot": "20260826", "term": 12, "company": "없는은행"}, 400),
    ("잘못된 선호", {"snapshot": "20260826", "term": 12, "prefs": "영업점=많이"}, 400),
    ("모르는 필드", {"snapshot": "20260826", "term": 12, "몰라": 1}, 422),
    # 목록 답의 모양 (F6) — 문자열을 그대로 받으면 `"국민은행" in "국민은행"` 이 참이라
    # 조용히 엉뚱한 판정이 된다. 400 으로 막아야 한다
    ("목록이 불리언", {"snapshot": "20260826", "term": 12,
                   "state": {"_거래은행": True}}, 400),
    ("목록이 문자열", {"snapshot": "20260826", "term": 12,
                   "state": {"_거래은행": "국민은행"}}, 400),
    # 기관이 붙을 수 없는 유형 (F6) — `마케팅_정보동의` 는 기관 무관이다
    ("기관 무관에 기관", {"snapshot": "20260826", "term": 12,
                     "state": {"마케팅_정보동의@국민은행": True}}, 400),
    ("후보에 없는 기관", {"snapshot": "20260826", "term": 12,
                     "state": {"_거래은행": ["없는은행"]}}, 400),
]


def post(base: str, body: dict) -> tuple[int, object]:
    req = urllib.request.Request(
        base + "/api/screen", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise SystemExit(f"서버에 붙을 수 없다 ({base}) — 먼저 띄운다: {e}") from e


def local(body: dict) -> dict:
    """**서버가 하는 것과 같은 순서로** 부른다. 순서가 달라지면 여기가 먼저 틀린다."""
    tax = C.load_tax()
    rows_all, by_pair = AB.load(body["snapshot"], body.get("group", "bank"),
                                body.get("term", 12))
    prefs = P.parse(body.get("prefs"))
    rows = C.scope_rows(rows_all, body.get("company"), body.get("kinds"))
    state = body.get("state", {})
    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    scored = AB.score_all(rows, by_pair, state, tax)
    if prefs:
        P.annotate(scored, prefs)
    outside = (V.outside_best(rows_all, rows, by_pair, state, tax)
               if len(rows) < len(rows_all) else None)
    total_all = (C.questions_left(C.question_plan(rows_all, by_pair), {})
                 if len(rows) < len(rows_all) else None)
    vm = V.build(scored, plan, state, total, body.get("top", 10), outside,
                 total_all, None, prefs, body.get("order", "hi"))
    return {**vm, "reports": [R.build(s, i, prefs)
                              for i, s in enumerate(vm["products"], 1)]}


def norm(o: object) -> object:
    """JSON 왕복에서 바뀌는 것만 맞춘다 — 튜플은 리스트가 되고 키는 문자열이 된다."""
    return json.loads(json.dumps(o, ensure_ascii=False, default=str))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    port = 8000
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    base = f"http://127.0.0.1:{port}"

    print(f"\n=== 서버·CLI 뷰 모델 대조 · {base} (이슈 #38) ===")
    print("같은 입력을 두 경로로 돌려 뷰 모델을 그대로 비교한다\n")
    fail = 0
    for label, body in CASES:
        code, got = post(base, body)
        if code != 200:
            print(f"  {label:<12}HTTP {code} — {got}")
            fail += 1
            continue
        want, got = norm(local(body)), norm(got)
        if want != got:
            keys = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
            print(f"  {label:<12}**다르다** — 다른 키 {keys}")
            for k in keys[:2]:
                print(f"      로컬 {k}: "
                      f"{json.dumps(want.get(k), ensure_ascii=False)[:180]}")
                print(f"      서버 {k}: "
                      f"{json.dumps(got.get(k), ensure_ascii=False)[:180]}")
            fail += 1
            continue
        q = got["questions"]["현재"]
        print(f"  {label:<12}같다 · 상품 {len(got['products'])}개 · "
              f"리포트 {len(got['reports'])}개 · "
              f"다음 질문 {q['key'] if q else '없음'}")

    print("\n에러 계약 — CLI 는 죽어도 되지만 서버는 4xx 로 답해야 한다")
    for label, body, want_code in ERRORS:
        code, got = post(base, body)
        mark = "맞다" if code == want_code else f"**{want_code} 를 기대했는데 {code}**"
        detail = str(got.get("detail") if isinstance(got, dict) else got)
        print(f"  {label:<12}{code}  {mark}  {detail[:70]}")
        if code != want_code:
            fail += 1

    print("\n폼 계약 — 목록 질문의 답 셋 (이슈 #48). HTML 경로라 state_json 으로 확인한다")
    fail += check_list_form(base)

    print(f"\n  {'**전부 통과**' if not fail else f'**실패 {fail}건**'}")
    raise SystemExit(1 if fail else 0)


def post_form(base: str, fields: list[tuple[str, str]]) -> tuple[int, str]:
    """`POST /screen` 을 브라우저처럼 urlencoded 로. 체크박스는 같은 이름이 여럿이다."""
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(f"{base}/screen", data=data, method="POST",
                                 headers={"Content-Type":
                                          "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def state_of(html: str) -> dict:
    """화면이 들고 다니는 답 — hidden `state_json` 을 읽는다 (`0040`)."""
    m = re.search(r'name="state_json" value="([^"]*)"', html)
    return json.loads(_html.unescape(m.group(1))) if m else {}


def check_list_form(base: str) -> int:
    base_fields = [("snapshot", "20260826"), ("group", "bank"), ("term", "12"),
                   ("state_json", "{}"), ("answer_key", C.TRADED_KEY)]
    cases = [
        # (이름, 추가 필드, 기대하는 _거래은행 값 · 'absent' 면 답이 안 들어가야 한다, 안내가 보여야 하나)
        ("빈 채로 고름", [("answer", "고름")], "absent", True),
        ("없음 버튼", [("answer", "없음")], [], False),
        ("모름 버튼", [("answer", "모름")], "모름", False),
        ("한 곳 고름", [("answer", "고름"), ("answer_bank", "주식회사 카카오뱅크")],
         ["주식회사 카카오뱅크"], False),
    ]
    fail = 0
    for label, extra, want, want_notice in cases:
        code, html = post_form(base, base_fields + extra)
        st = state_of(html)
        got = st.get(C.TRADED_KEY, "absent")
        has_notice = "은행을 하나 이상 고르거나" in html
        ok = code == 200 and got == want and has_notice == want_notice
        # 빈 제출을 막았으면 **같은 질문이 다시 나와야 한다** — 넘어가면 안 된다
        if label == "빈 채로 고름" and "거래해 본 은행을 골라 주세요" not in html:
            ok = False
        mark = "맞다" if ok else "**틀리다**"
        print(f"  {label:<12}{code}  {mark}  _거래은행={json.dumps(got, ensure_ascii=False)}"
              f"  안내={'있음' if has_notice else '없음'}")
        fail += 0 if ok else 1
    return fail


if __name__ == "__main__":
    main()
