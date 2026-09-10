# -*- coding: utf-8 -*-
"""웹 렌더러 — 뷰 모델을 HTML 로. **검사가 부를 수 있는 함수 하나**로 둔다.

이 파일이 채우는 자리
    F4-3 이 웹 렌더러에도 렌더 겹 검사를 걸어야 한다(`0039` D3 · `0040` 반증 조건).
    그러려면 **검사가 부를 수 있는 함수**가 있어야 한다 — 라우트 핸들러 안에 렌더가
    흩어지면 검사가 붙을 자리가 없고, F4-3 에서 다시 뜯게 된다.

    그래서 라우트는 `render_screen(vm)` 을 부르기만 하고, 검사도 같은 함수를 부른다.

템플릿에 판정을 넣지 않는다 (`0038` 반증 조건)
    `{% if 폭이 있으면 범위로 %}` 를 템플릿이 하기 시작하면 화면 계약이 뷰 모델 밖으로
    샌다 — F4-0 이 계약을 객체로 옮긴 일이 무의미해진다.

    표시 결정은 전부 **`view.display()`** 가 한다(범위 문자열 · 남은 조건 라벨 ·
    선호 조정 문구 · 주의 코드). CLI 의 `product_line` 도 같은 함수를 읽는다 —
    한쪽만 쓰는 칸을 만들지 않는다(`0039` 반증 조건 1).

    템플릿은 **이미 정해진 문자열을 꽂기만** 한다. 반복(`{% for %}`)은 배치라서 괜찮다.

이스케이프
    Jinja2 의 autoescape 를 켠다. 데이터에 `&` 와 `"` 가 실제로 있다
    (상품명·기관명·공시 문구 1,831개 중 3개) — `0038` 이 Jinja2 를 고른 이유 하나다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "analysis"))

import calculate as C  # noqa: E402
import prefs as P  # noqa: E402
import view as V  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent / "templates"

# `StrictUndefined` — 템플릿이 없는 값을 조용히 빈칸으로 그리지 않게 한다.
# 화면이 칸을 빠뜨리는 것이 이 저장소가 네 번 겪은 실패다(`0019`·`0029`·`0035`·`0039`).
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


TERM_MENU = (6, 12, 24, 36)


def render_start(form: dict | None = None, error: str | None = None,
                 snapshots: dict[str, list[str]] | None = None,
                 prefilled: tuple[str, ...] | list[str] | set[str] = (),
                 prefill_notice: str | None = None, prefill_failed: bool = False) -> str:
    """0단계 폼. 상품 목록을 만드는 **검색 축**을 받는다 (`0028`).

    조건 답은 여기서 받지 않는다 — 그건 질문 루프의 일이고, 사용자가 예/아니오/모름으로
    확인해야 한다(`0016`·`0024` P5).

    `prefilled` 는 **문장에서 채운 칸의 이름**이다 (R2 · `prereg-29` · A19). 템플릿은 그 칸 옆에
    "문장에서 채움 — 확인하세요" 를 붙이기만 한다 — 무엇을 채웠는지는 서버가 정했다.
    `prefill_notice` 는 채우기 뒤에 한 줄 (성공·실패·빈 상자). 문장 자체는 여기 오지 않는다.
    """
    form = form or {}
    # 기간 메뉴 — 모델이 낸 기간이 메뉴 밖(예: 18)이면 그 값을 더해 **보이게** 한다. 조용히 12 로 바꾸지 않는다
    terms = list(TERM_MENU)
    try:
        t = int(str(form.get("term", "")).strip() or 0)
    except ValueError:
        t = 0
    if t and t not in terms:
        terms = sorted(terms + [t])
    # 금액 읽기 — 칸에 값이 있으면 옆에 한글로 (`오백만 원`). 사람 세션에서 `5000000` 을 읽지 못했다(`prereg-29` §7).
    # 판정이 아니라 같은 값을 다른 표기로 한 번 더 보이는 것이다. 못 읽는 값은 그냥 둔다 — 제출 때 서버가 오류로 답한다
    readings: dict[str, str] = {}
    for k in ("amount_deposit", "amount_monthly"):
        raw = str(form.get(k, "") or "").strip()
        if not raw:
            continue
        try:
            readings[k] = C.amount_words(C.parse_amount(raw))
        except SystemExit:
            pass
    # "더 정하기" 를 펼칠 것인가 (F7 · `prereg-35` ①) — 접힌 칸에 값이 있으면 펼친다. 사용자가 적었든 문장에서 채웠든
    # **값이 있는 칸은 보여야 한다**(A19). 기본값(정렬 hi · 빈 스냅샷)은 값으로 치지 않는다. 판정은 여기(렌더러 코드)서 하고 템플릿은 플래그만 쓴다
    folded = ["company", "amount_deposit", "amount_monthly", "snapshot", "resume_code",
              f"pref_{P.LIST_AXIS}"] + [f"pref_{k}" for k in P.AXES]
    unfold = any(str(form.get(k) or "").strip() for k in folded) or (form.get("order") or "hi") != "hi"         or any(k in set(prefilled) for k in folded)
    return _env.get_template("start.html").render(
        form=form,
        축=P.AXES,                      # 선호 5문항 — 고정 표에서 온다 (`0030`)
        목록축=P.LIST_AXIS,
        스냅샷=snapshots or {},          # 권역별로 있는 날짜 — 비우면 최신 (이슈 #52)
        error=error,
        기간들=terms,
        채운칸=set(prefilled),
        금액읽기=readings,
        더_펼침=unfold,
        prefill_notice=prefill_notice,
        prefill_failed=prefill_failed,
    )


def render_screen(vm: dict, form: dict, reports: list[dict],
                  notice: str | None = None, resume_code: str = "",
                  stop: bool = False, survey_url: str = "") -> str:
    """**검사가 부르는 함수.** 뷰 모델 하나가 화면 하나가 된다.

    `form` 은 다음 요청에 그대로 실어 보낼 것들이다 — 스냅샷·권역·기간·스코프·선호와
    **지금까지의 답(state)**. 서버가 상태를 안 들기 때문에 화면이 들고 다닌다(`0040`).

    `notice` 는 **답을 받지 않고 같은 화면을 다시 낼 때** 붙이는 한 문장이다 (이슈 #48 —
    목록 질문을 빈 채로 넘기려 한 경우). 문장은 뷰 모델(`빈_제출_안내`)에서 오고 판정은
    서버가 한다. 템플릿은 받은 문장을 꽂기만 한다.
    """
    rows = [V.display(s) for s in vm["products"]]
    return _env.get_template("screen.html").render(
        vm=vm, rows=rows, form=form, reports=reports,
        state_json=form.get("state_json", "{}"),
        notice=notice,
        # 이어하기 코드 (D9) — 서버가 만든 문자열. 비면 상자를 안 그린다(검사가 부를 때)
        resume_code=resume_code,
        # 멈춤 화면 (F7 · `prereg-35` ④) — 질문 카드 대신 요약 카드. 요약 문장은 뷰 모델에 이미 있는 문자열의 배치다.
        # 설문 링크는 환경변수 — 서버는 설문을 받지 않는다(`0040`). 없으면 템플릿이 "진행자가 안내" 한 줄을 낸다
        stop=stop,
        survey_url=survey_url,
    )
