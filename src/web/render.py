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


def render_start(form: dict | None = None, error: str | None = None) -> str:
    """0단계 폼. 상품 목록을 만드는 **검색 축**을 받는다 (`0028`).

    조건 답은 여기서 받지 않는다 — 그건 질문 루프의 일이고, 사용자가 예/아니오/모름으로
    확인해야 한다(`0016`·`0024` P5).
    """
    return _env.get_template("start.html").render(
        form=form or {},
        축=P.AXES,                      # 선호 5문항 — 고정 표에서 온다 (`0030`)
        목록축=P.LIST_AXIS,
        error=error,
    )


def render_screen(vm: dict, form: dict, reports: list[dict]) -> str:
    """**검사가 부르는 함수.** 뷰 모델 하나가 화면 하나가 된다.

    `form` 은 다음 요청에 그대로 실어 보낼 것들이다 — 스냅샷·권역·기간·스코프·선호와
    **지금까지의 답(state)**. 서버가 상태를 안 들기 때문에 화면이 들고 다닌다(`0040`).
    """
    rows = [V.display(s) for s in vm["products"]]
    return _env.get_template("screen.html").render(
        vm=vm, rows=rows, form=form, reports=reports,
        state_json=form.get("state_json", "{}"),
    )
