# -*- coding: utf-8 -*-
"""기관 사전 — 상품 줄에 붙일 **홈페이지 · 대표전화** (F3 · 이슈 #60 · `prereg-21`).

이 파일이 채우는 자리
    사유 문장 셋(`조건불명`·`뜻없음`·`추첨`)이 전부 *"은행에 확인해 보세요"* 로 끝나는데
    화면에 갈 곳이 없었다. 재료는 A7 이 받아 뒀다(`fetch_companies.py` · `prereg-20` —
    기관 97곳 100%). 여기서는 그 파일을 읽어 **기관 코드**로 짝짓기만 한다.

무엇을 하나
    load()      두 권역 최신 `data/raw/company_*.json` 을 합쳐 `{fin_co_no: {"홈페이지", "전화"}}`.
                한 번 읽고 든다 — 월 1회 갱신되는 읽기 전용 파일이다(`0010`)
    link(url)   **화면에 낼 URL.** 스킴이 없을 때만 `https://` 를 붙이고 그 밖에는 API 값 그대로.
                사람이 정했다 (2026-09-04 · *"붙이든 안 붙이든 눌러서 열리게"*). 저장 데이터는 안 고친다
    contact(s)  상품 dict 하나 → `{"홈페이지": 화면 URL, "홈페이지_원천": API 값, "전화": API 값}`.
                짝이 없으면 전부 빈 문자열 — **다른 곳에서 채우지 않는다** (`prereg-20` §4 · `0016`)

무엇을 안 하나
    - 이름으로 짝짓지 않는다. 코드로 짝지으면 이름도 같다는 것을 `prereg-20` P4 가 확인했다
    - URL 에 아무것도 덧붙이지 않는다 — 추적 파라미터·제휴 코드 금지(`0037` D2). 붙어 있는
      파라미터(우리은행·푸른저축은행)도 떼지 않는다 — API 가 준 값이다
    - 전화에 하이픈을 넣지 않는다. 숫자만 온다(8~10자리) — 표기는 API 값 그대로고, 눌러서 걸리는
      것은 렌더러의 `tel:` 링크가 맡는다
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
GROUPS = ("bank", "savingsbank")
SCHEMES = ("http://", "https://")

_CACHE: dict[str, dict[str, str]] | None = None


def latest(group: str) -> Path | None:
    """이름 순 마지막 `company_{group}_*.json`. 없으면 None — 화면은 빈 칸으로 간다."""
    files = sorted(RAW_DIR.glob(f"company_{group}_*.json"))
    return files[-1] if files else None


def load(force: bool = False) -> dict[str, dict[str, str]]:
    """`{fin_co_no: {"홈페이지": API 값, "전화": API 값}}`. 두 권역을 합친다 — 기관 코드는 권역을
    넘어 유일하다(`prereg-13` 이 저축은행 58개 기관코드를 셀 때 확인한 사실)."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    out: dict[str, dict[str, str]] = {}
    for group in GROUPS:
        path = latest(group)
        if path is None:
            continue
        for r in json.loads(path.read_text(encoding="utf-8")).get("baseList", []):
            co = (r.get("fin_co_no") or "").strip()
            if co:
                out[co] = {"홈페이지": (r.get("homp_url") or "").strip(),
                           "전화": (r.get("cal_tel") or "").strip(),
                           # 공시 이름 — 화면에는 안 나가고 A17 이 행의 `company` 와 대조한다.
                           # 링크는 코드로 가는데 이름이 다른 기관이면 링크가 이름과 다른 곳으로 간다
                           "이름": (r.get("kor_co_nm") or "").strip()}
    _CACHE = out
    return out


def link(url: str) -> str:
    """화면에 낼 URL. **스킴이 없을 때만** `https://` 를 붙인다 — 그 밖에는 그대로다."""
    u = (url or "").strip()
    if not u:
        return ""
    return u if u.lower().startswith(SCHEMES) else f"https://{u}"


def contact(s: dict) -> dict[str, str]:
    """상품 dict 하나의 연락처. `co_no` 로 짝짓고, 없으면 빈 칸이다."""
    row = load().get((s.get("co_no") or "").strip(), {})
    raw = row.get("홈페이지", "")
    return {"홈페이지": link(raw), "홈페이지_원천": raw, "전화": row.get("전화", "")}


def name_of(co_no: str) -> str:
    """기관 코드의 공시 이름. 사전에 없으면 빈 문자열."""
    return load().get((co_no or "").strip(), {}).get("이름", "")


def is_faithful(shown: str, raw: str) -> bool:
    """화면 URL 이 API 값과 같거나 `https://` + API 값인가 — A17 (나). 우리가 붙인 것이 스킴뿐이어야 한다."""
    return shown == raw or (shown == f"https://{raw}" and not raw.lower().startswith(SCHEMES))
