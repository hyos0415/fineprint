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

import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "analysis"))

import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402
import prefs as P  # noqa: E402
import report as R  # noqa: E402
import view as V  # noqa: E402

app = FastAPI(
    title="FINeprint",
    description="내 상황과 내 선호에 맞는 예금·적금을 골라준다 — 화면 계약 A1~A13 을 "
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


class ScreenRequest(BaseModel):
    """화면 한 장을 받으려고 보내는 것. **답(state)까지 여기 실린다** — 무상태다."""

    model_config = ConfigDict(extra="forbid")

    snapshot: str = Field(..., description="스냅샷 날짜 YYYYMMDD", examples=["20260826"])
    group: Literal["bank", "savingsbank"] = "bank"
    term: int = Field(12, ge=1, le=60, description="가입 기간(개월)")
    company: str | None = Field(None, description="기관 스코프 — 쉼표로 여럿 (`0028`)")
    kinds: str | None = Field(None, description="상품군 스코프 — 예금/적금")
    prefs: str | None = Field(None, description="선호 — `영업점=되도록안간다,확실성=조금`")
    top: int | None = Field(10, ge=1, le=500, description="목록에 담을 상품 수")
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
            detail=f"스코프에 맞는 상품이 없다 (기관={req.company} 상품군={req.kinds})")

    # 답에 모르는 조건 유형이 오면 **거른다** — 클라이언트를 믿지 않는다(무상태의 대가)
    unknown = [k for k in req.state
               if k not in C.CONDITION_TYPES
               and not (k.rpartition("_")[2] in ("금액", "횟수")
                        and k.rpartition("_")[0] in C.CONDITION_TYPES)]
    if unknown:
        raise HTTPException(status_code=400, detail=f"모르는 조건 유형: {unknown}")

    plan = C.question_plan(rows, by_pair)
    total = C.questions_left(plan, {})
    scored = AB.score_all(rows, by_pair, req.state, tax)
    if prefs:
        P.annotate(scored, prefs)

    # A7 — 스코프를 걸었으면 밖의 최고 금리를 같이 낸다 (`0028` S4)
    outside = (V.outside_best(rows_all, rows, by_pair, req.state, tax)
               if len(rows) < len(rows_all) else None)
    total_all = (C.questions_left(C.question_plan(rows_all, by_pair), {})
                 if len(rows) < len(rows_all) else None)

    vm = V.build(scored, plan, req.state, total, req.top, outside, total_all,
                 None, prefs)
    return {**vm,
            "reports": [R.build(s, i, prefs)
                        for i, s in enumerate(vm["products"], 1)]}


@app.get("/api/health", summary="살아 있나 · 무엇을 들고 있나")
def health() -> dict:
    return {"들고 있는 스냅샷": [f"{s}/{g}/{t}개월" for s, g, t in _CACHE],
            "세율": C.load_tax()["적용_시점"],
            "고지": C.NOTICE}
