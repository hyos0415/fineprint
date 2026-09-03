# -*- coding: utf-8 -*-
"""UI 서버 — 이미 있는 계산 함수를 HTTP 로 감싼 얇은 껍데기.

이 파일이 채우는 자리
    화면이 없었다(저장소에 `.html`·`.js` 0개). 그런데 계산기가 파이썬에 있어서
    정적 페이지로는 갈 수 없다 — JS 로 다시 쓰면 계산이 두 군데가 되어 **두 답**이
    나오고(`problem.md` §7), 미리 계산하려면 은행권 12개월만 질문 15개 ×
    예/아니오/모름이라 **3^15 = 1,435만 상태**다. 그래서 서버가 필요하다
    (`0038` · `ui-plan.md` F4-1).

무엇을 하나 — 셋뿐이다
    1. 시작할 때 스냅샷을 한 번 읽어 든다 (은행권 311KB · 저축은행 288KB · 50~94ms)
    2. 요청마다 `score_all` → `view.build` (계산 16ms · 뷰 모델 조립은 사실상 공짜)
    3. 뷰 모델을 JSON 으로 낸다

    **계산을 여기서 새로 하지 않는다.** `evaluate()`·`view.build()`·`report.build()` 를
    부르기만 한다 — CLI 와 웹이 같은 함수를 쓰므로 두 답이 나올 자리가 없다.

**무상태다** (이슈 #38)
    답을 서버에 저장하지 않는다. 클라이언트가 `state` 를 매 요청에 실어 보낸다 —
    질문 15개를 다 답한 state 가 **466B** 라 가능하다.

    이유 셋. (1) `0026` 의 반증 조건이 발동하지 않는다 — *"우대조건 답을 저장하면
    개인정보 최소수집과 충돌할 수 있다. 저장·계정 기능을 만드는 순간 이 결정을 다시
    본다."* (2) 이어하기(D9)가 공짜다 — 클라이언트가 자기 state 를 보관하면 서버
    재시작과 무관하다. (3) 나중에 세션 저장을 얹는 건 쉽지만 걷어내는 건 어렵다.

    **DB 가 없는 것도 같은 이유다.** 읽는 것은 월 1회 갱신되는 읽기 전용 스냅샷이고
    쓰는 것이 없다. DB 가 정당해지는 조건은 따로 적어 뒀다(답 저장 · 스냅샷 시계열
    질의 · A2 코퍼스 검색).

띄우는 법
    source .venv/Scripts/activate
    python -m uvicorn src.web.app:app --host 127.0.0.1 --port 8000 --reload

    **127.0.0.1 에만 묶는다** — 로컬 전용이고 `0037` 이 *"공개는 깃 단위에서 끝날
    가능성이 높다"* 를 전제로 선다. 문서는 http://127.0.0.1:8000/docs 에 있다.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "analysis"))
# `uvicorn src.web.app:app` 로 띄우면 이 디렉터리가 sys.path 에 없다 — 넣어 준다
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402
import report as R  # noqa: E402
import view as V  # noqa: E402

import render as RENDER  # noqa: E402  — 웹 렌더러 (같은 디렉터리)

app = FastAPI(
    title="FINeprint",
    description="내 상황과 내 선호에 맞는 예금·적금을 골라준다 — 화면 계약 A1~A14 를 "
                "지키는 뷰 모델을 낸다. 계산은 파이썬 한 벌뿐이다.",
    version="0.1.0",
)

# 스냅샷 캐시 — (스냅샷, 권역, 기간) 하나당 한 번만 읽는다.
#
# **요청마다 읽으면 50~94ms 가 계산(16ms)보다 커진다.** 스냅샷은 월 1회 갱신되고
# 프로세스가 사는 동안 안 바뀌므로 캐시가 틀릴 자리가 없다(`0010`).
_CACHE: dict[tuple[str, str, int], tuple[list[dict], dict]] = {}


def load(stamp: str, group: str, term: int) -> tuple[list[dict], dict]:
    key = (stamp, group, term)
    if key not in _CACHE:
        try:
            rows, by_pair = AB.load(stamp, group, term)
        except SystemExit as e:          # CLI 는 죽지만 서버는 400 으로 답해야 한다
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not rows:
            raise HTTPException(status_code=400,
                                detail=f"{term}개월 상품이 없다 (스냅샷 {stamp} · {group})")
        _CACHE[key] = (rows, by_pair)
    return _CACHE[key]


def resolve_snapshot(stamp: str | None, group: str) -> str:
    """비어 있으면 **권역별 최신**을 고른다 (이슈 #52).

    옛 폼은 권역과 무관하게 `20260826` 을 기본값으로 박아 두어 저축은행을 고른 사람이
    첫 화면에서 *"추출 결과가 없다"* 로 막혔다(3런 · `prereg-16`). 날짜를 적으면 그대로
    쓴다 — 옛 스냅샷으로 재현하는 길은 남긴다.
    """
    if stamp and stamp.strip():
        return stamp.strip()
    try:
        return AB.latest_snapshot(group)
    except SystemExit as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class ScreenRequest(BaseModel):
    """화면 한 장을 받으려고 보내는 것. **답(state)까지 여기 실린다** — 무상태다."""

    model_config = ConfigDict(extra="forbid")

    snapshot: str | None = Field(
        None, description="스냅샷 날짜 YYYYMMDD. **비우면 권역별 최신** — 저축은행은 은행권과 "
                          "날짜가 다르다(20260825 vs 20260826). 이슈 #52",
        examples=["20260826"])
    group: Literal["bank", "savingsbank"] = "bank"
    term: int = Field(12, ge=1, le=60, description="가입 기간(개월)")
    company: str | None = Field(None, description="기관 스코프 — 쉼표로 여럿 (`0028`)")
    kinds: str | None = Field(None, description="상품군 스코프 — 예금/적금")
    prefs: str | None = Field(None, description="선호 — `영업점=되도록안간다,확실성=조금`")
    top: int | None = Field(10, ge=1, le=500, description="목록에 담을 상품 수")
    order: Literal["hi", "lo"] = Field(
        "hi",
        description="정렬 — hi 다 채웠을 때 순(`0017` 기본값) · lo 확정된 값 순. "
                    "**조건을 못 채우는 사용자는 lo 를 봐야 한다** (`prereg-14` §8)",
    )
    state: dict[str, Any] = Field(
        default_factory=dict,
        description="지금까지의 답. `{조건유형: true|false|\"모름\"}` 또는 수치. "
                    "**서버에 저장하지 않는다** — 매 요청에 실어 보낸다",
    )


class ScreenResponse(BaseModel):
    """뷰 모델 그대로.

    **부분집합 모델을 만들지 않는다.** `extra="allow"` 로 두어 상품 dict 의 나머지
    칸이 그대로 통과한다 — 부분집합을 정의하면 API 가 보는 것과 화면 계약이 보는
    것이 갈라지고, 그게 `0039` D2 가 막은 자리다(뷰 모델과 화면의 드리프트).

    필수 칸만 여기서 강제한다. *"폭이 남았는데 단일 숫자로 렌더했나"* 같은 것은
    스키마가 못 잡으므로 **화면 계약 assert 를 대체하지 않는다**(`0038` 반증 조건).
    """

    model_config = ConfigDict(extra="allow")

    meta: dict[str, Any]
    progress: dict[str, Any]
    headline: dict[str, Any]
    products: list[dict[str, Any]]
    questions: dict[str, Any]
    notices: dict[str, Any]
    reports: list[dict[str, Any]]


@app.post("/api/screen", response_model=ScreenResponse,
          summary="화면 한 장 — 목록 · 진행 · 다음 질문 · 사유 · 비교 리포트")
def screen(req: ScreenRequest) -> dict:
    """뷰 모델을 만들어 낸다. **CLI 가 그리는 것과 같은 객체다.**

    엔드포인트가 하나뿐인 이유는 무상태이기 때문이다 — *"답 하나를 더 받는다" 가
    "답이 하나 더 들어간 state 로 다시 그린다" 와 같은 일*이다.
    """
    vm, reports = _screen_payload(req)
    return {**vm, "reports": reports}


def _screen_payload(req: "ScreenRequest") -> tuple[dict, list[dict]]:
    """뷰 모델과 리포트를 만든다. **API 와 화면이 같은 것을 쓴다.**

    `/api/screen` 과 `POST /screen`(HTML)이 이 함수를 공유하므로 둘이 갈라질 자리가
    없다 — `0035` 가 찾은 실패("문구가 두 곳에 있었다")를 구조로 막는다.
    """
    if not req.snapshot:
        req.snapshot = resolve_snapshot(None, req.group)
    rows_all, by_pair = load(req.snapshot, req.group, req.term)
    tax = C.load_tax()
    try:
        prefs = P.parse(req.prefs)
    except SystemExit as e:
        raise HTTPException(status_code=400, detail=f"선호를 읽을 수 없다: {e}") from e
    rows = C.scope_rows(rows_all, req.company, req.kinds)
    if not rows:
        raise HTTPException(
            status_code=400,
            detail=f"찾는 범위에 맞는 상품이 없습니다 "
                   f"(은행={req.company} · 예금/적금={req.kinds})")
    # 상태 키 판정은 `calculate.is_state_key()` 한 곳에서 한다 — 복사하면 갈라진다
    unknown = [k for k in req.state if not C.is_state_key(k)]
    if unknown:
        raise HTTPException(status_code=400, detail=f"모르는 조건 유형: {unknown}")
    # 목록 답만 모양이 다르다 (F6) — 기관 이름의 리스트이거나 "모름" 이다.
    # **여기서 안 막으면 `answer_of()` 가 문자열을 기관 목록으로 읽는다** —
    # `"국민은행" in "국민은행"` 이 참이라 조용히 엉뚱한 판정이 된다
    banks = req.state.get(C.TRADED_KEY)
    if banks is not None and banks != C.UNSURE:
        if not isinstance(banks, list) or not all(isinstance(b, str) for b in banks):
            raise HTTPException(
                status_code=400,
                detail=f"{C.TRADED_KEY} 는 은행 이름의 목록이어야 한다 (또는 \"모름\")")

    bad_banks = C.unknown_banks(req.state, rows)
    if bad_banks:
        raise HTTPException(
            status_code=400,
            detail=f"후보에 없는 은행이다: {bad_banks} — 목록에 없는 이름을 그냥 두면 "
                   f"'거래하지 않은 은행' 으로 유도된다")

    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    scored = AB.score_all(rows, by_pair, req.state, tax)
    if prefs:
        P.annotate(scored, prefs)
    outside = (V.outside_best(rows_all, rows, by_pair, req.state, tax)
               if len(rows) < len(rows_all) else None)
    total_all = (C.questions_left(C.question_plan(rows_all, by_pair), {})
                 if len(rows) < len(rows_all) else None)
    vm = V.build(scored, plan, req.state, total, req.top, outside, total_all,
                 None, prefs, req.order)
    reports = [R.build(s, i, prefs) for i, s in enumerate(vm["products"], 1)]
    return vm, reports


@app.get("/", response_class=HTMLResponse, summary="0단계 — 검색 축을 받는다")
def start() -> str:
    """폼이다. **자유 입력이 아니다** — 자유 입력(R2)은 `0042` 로 따로 정해 뒀고,
    그때는 로컬 모델이 첫 수신자가 되어야 한다.
    """
    return RENDER.render_start(snapshots=_snapshot_menu())


def _snapshot_menu() -> dict[str, list[str]]:
    """권역별로 있는 스냅샷 — 폼이 "비우면 최신" 옆에 무엇이 최신인지 적는 데 쓴다."""
    return {g: AB.snapshots(g) for g in ("bank", "savingsbank")}


@app.post("/screen", response_class=HTMLResponse, summary="화면 하나 (HTML)")
async def screen_html(request: Request) -> str:
    """폼을 받아 화면을 그린다.

    **폼을 표준 라이브러리로 파싱한다** — FastAPI 의 `Form(...)` 도 Starlette 의
    `request.form()` 도 `python-multipart` 를 요구한다(urlencoded 에도 그렇다).
    그런데 우리 폼은 **파일 업로드가 없는 `application/x-www-form-urlencoded`** 라
    `urllib.parse.parse_qs` 다섯 줄로 끝난다. 의존성 하나를 위해 `requirements.txt` 에
    다섯 번째 예외를 적을 이유가 없다(`0038` — 예외는 사유가 있어야 한다).

    **PRG(POST-redirect-GET)를 쓰지 않는다** (이슈 #40 정정). PRG 는 새로고침 때 같은
    **쓰기**가 두 번 일어나는 것을 막는 패턴인데 이 서버는 쓰기가 없다. 그리고 표준
    PRG 는 리다이렉트 대상이 GET 이라 **상태가 URL 에 올라간다** — 급여이체·카드실적
    같은 답이 URL 과 서버 로그에 남는 것을 피하려고 POST 를 고른 것이다.

    **답은 서버에 저장하지 않는다** — `state_json` 으로 받아서 하나 더하고, 다음 화면의
    hidden 으로 돌려보낸다 (`0040` 무상태).
    """
    multi = await _form(request)
    f = _flat(multi)
    # **HTML 경로는 어떤 오류든 HTML 로 답한다.** 사람 완주 2런에서 날 JSON 을 봤다 —
    # `{"detail": "모르는 조건 유형: [...]"}` 가 화면에 그대로 나왔다.
    #
    # 처음 고칠 때는 `_screen_payload` **하나만** 감쌌는데, 그 위쪽에서 나는 오류
    # (답 검증 · 기간 · 정렬)는 그대로 새어 나갔다. 실제로 `order=middle` 이
    # 날 JSON 으로 나오는 것을 검증에서 잡았다. **폼을 읽은 다음부터 전부 감싼다.**
    #
    # 에러 계약이 `/api/screen`(JSON)과 `POST /screen`(HTML)에서 다르다 —
    # 같은 함수를 쓰되 **답하는 모양만** 갈라진다.
    try:
        return _screen_from_form(f, multi.get("answer_bank", []))
    except HTTPException as e:
        return HTMLResponse(RENDER.render_start(f, str(e.detail), _snapshot_menu()),
                            status_code=e.status_code)


def _screen_from_form(f: dict[str, str], picked_banks: list[str] | None = None) -> str:
    """폼 하나를 화면 하나로. **오류는 그냥 던진다** — HTML 로 바꾸는 것은 위에서 한다."""

    def get(name: str, default: str = "") -> str:
        v = f.get(name, default)
        return v if isinstance(v, str) else default

    try:
        state = json.loads(get("state_json", "{}") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="state 를 읽을 수 없다") from None
    if not isinstance(state, dict):
        raise HTTPException(status_code=400, detail="state 가 객체가 아니다")

    # 답 하나를 더한다. **예/아니오/모름 셋뿐이다** (`0027`) — 목록 질문만 예외다(F6)
    key, answer = get("answer_key"), get("answer")
    notice: str | None = None
    if key == C.TRADED_KEY and answer:
        # 답은 셋이다 (이슈 #48) — 고른 목록 · **"거래한 곳이 없다"(명시적 버튼)** · 모름.
        # 예전에는 빈 제출이 "없다" 였는데, 3런에서 사람이 그것을 답으로 못 읽고
        # "모르겠습니다" 를 눌렀다(`prereg-16` §6). 이제 빈 채로 "고름" 을 누르면
        # **받지 않고 같은 화면을 안내와 함께 다시 낸다.**
        # 고른 기관이 후보에 없는 이름이면 막는다 — 조용히 무시하면 사용자가 고른 것과
        # 계산에 들어간 것이 달라진다
        picked = list(dict.fromkeys(picked_banks or []))
        if answer == "모름":
            state[key] = C.UNSURE
        elif answer == "없음":
            state[key] = []
        elif answer != "고름":
            raise HTTPException(status_code=400, detail=f"모르는 답: {answer}")
        elif picked:
            state[key] = picked
        else:
            notice = "__빈_제출__"           # 아래에서 뷰 모델의 문장으로 바꾼다
    elif key and answer:
        if answer not in ("예", "아니오", "모름"):
            raise HTTPException(status_code=400, detail=f"모르는 답: {answer}")
        state[key] = {"예": True, "아니오": False, "모름": C.UNSURE}[answer]

    try:
        term = int(get("term", "12") or 12)
    except ValueError:
        raise HTTPException(status_code=400, detail="기간을 읽을 수 없다") from None

    company, kinds = get("company"), get("kinds")
    prefs_arg = get("prefs") or _prefs_from_form(f)
    # 정렬 (`prereg-14` §8 A안). 폼이 안 보내면 `0017` 의 기본값이다
    order = get("order", "hi") or "hi"
    if order not in ("hi", "lo"):
        raise HTTPException(status_code=400, detail=f"모르는 정렬: {order}")
    group = get("group", "bank") or "bank"
    form = {"snapshot": resolve_snapshot(get("snapshot"), group), "group": group,
            "term": term, "company": company, "kinds": kinds, "prefs": prefs_arg,
            "order": order,
            "state_json": json.dumps(state, ensure_ascii=False)}
    req = ScreenRequest(snapshot=form["snapshot"], group=form["group"], term=term,
                        company=company or None, kinds=kinds or None,
                        prefs=prefs_arg or None, top=10, state=state, order=order)
    vm, reports = _screen_payload(req)
    if notice:
        # 문장은 뷰 모델이 든다 — 한쪽만 쓰는 낱말을 만들지 않는다 (`0039` 반증 조건 1)
        cur = vm["questions"].get("현재") or {}
        notice = cur.get("빈_제출_안내") or "은행을 하나 이상 골라 주세요"
    return RENDER.render_screen(vm, form, reports, notice)


async def _form(request: Request) -> dict[str, list[str]]:
    """`application/x-www-form-urlencoded` 본문을 표준 라이브러리로 읽는다.

    **값을 리스트로 돌려준다** — 목록 질문(F6)의 체크박스가 같은 이름을 여러 번
    보내기 때문이다. 나머지 칸은 `_flat()` 이 마지막 값 하나로 줄인다(브라우저가 폼을
    제출할 때의 순서다). 파일 업로드(multipart)는 다루지 않는다. 우리 폼에는 없다.
    """
    ctype = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in ctype:
        raise HTTPException(status_code=415,
                            detail=f"폼이 아니다 (content-type={ctype!r})")
    raw = (await request.body()).decode("utf-8")
    return urllib.parse.parse_qs(raw, keep_blank_values=True)


def _flat(multi: dict[str, list[str]]) -> dict[str, str]:
    """반복 필드를 마지막 값 하나로. 화면이 다시 실어 보낼 칸들은 전부 단일 값이다."""
    return {k: v[-1] for k, v in multi.items()}


def _prefs_from_form(f) -> str:
    """0단계 폼의 `pref_*` 칸들을 `--prefs` 문자열로 모은다.

    **고정 표의 답 문자열을 그대로 넘긴다** — 여기서 %p 로 바꾸지 않는다. 변환은
    `prefs.parse()` 한 곳에서만 한다(`0030` — 표가 하나여야 화면과 정렬이 같은 값을 쓴다).
    """
    parts = []
    for name in list(P.AXES) + [P.LIST_AXIS]:
        v = f.get(f"pref_{name}")
        if isinstance(v, str) and v.strip():
            if name == P.LIST_AXIS:
                # 쉼표·공백으로 적은 목록을 LIST_SEP 로 이어야 `--prefs` 의 축 구분자
                # `,` 와 안 섞인다 (이슈 #52)
                v = P.LIST_SEP.join(P.split_list(v))
            parts.append(f"{name}={v.strip()}")
    return ",".join(parts)


@app.get("/api/health", summary="살아 있나 · 무엇을 들고 있나")
def health() -> dict:
    return {"들고 있는 스냅샷": [f"{s}/{g}/{t}개월" for s, g, t in _CACHE],
            "세율": C.load_tax()["적용_시점"],
            "고지": C.NOTICE}
