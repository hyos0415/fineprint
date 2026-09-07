# -*- coding: utf-8 -*-
"""R2 — 사용자 자연어 한 문단 → 스코프 + 조건 답 **후보** (D8 · 이슈 #73 · `0057` · `prereg-27`).

이 파일이 채우는 자리
    사용자가 "우리은행 주거래고 급여도 거기로 받아" 라고 쓰면, 그 말을 폼 칸(권역·은행·상품군·기간·금액)과 조건 답
    후보(`카드실적@국민은행: 예`)로 옮긴다. **모델은 제안만 한다** — 후보는 확인 화면에서 사용자가 항목별로 고른 뒤에만
    `state` 에 들어간다(`0057` D2). 이 파일은 그 확인 이전까지다.

지키는 것
    - **로컬 모델만** (`0042` D1). 엔드포인트는 llama.cpp `llama-server` 의 OpenAI 호환 API 다. 외부 API 로 보내지 않는다
    - **출력은 스키마로 강제** — 기관 이름은 공시 이름 55개의 enum, 조건 유형은 `CONDITION_TYPES` 의 enum, 값은 예/아니오/모름.
      없는 은행·없는 유형이 나올 수 없다(추출 시점 형식 제한 · `CLAUDE.md` 5번). 문구 단위 `#` 키는 스키마에 없다
    - **후보 집합 밖 키는 버린다** — 코드가 `type_key(type, bank)` 로 키를 만들고 `question_plan` 에 없는 키는 낸다고 해도 무시한다
    - **원문은 반환 뒤 즉시 버린다** — 로그에 남기지 않는다(`0042` D3). 이 모듈은 원문을 어디에도 쓰지 않는다

사용법 (측정은 `measure_r2.py` · 화면은 관문을 넘은 뒤):
    python src/analysis/r2_parse.py "우리은행 주거래고 적금 하나 들고 싶어" --url http://127.0.0.1:8081
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calculate as C  # noqa: E402
from extract_llm import CONDITION_TYPES  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8081"
TIMEOUT = 120
MAX_TOKENS = 600

# 공시 기관 이름 — 두 권역 · 55곳. 스키마 enum 이라 여기 없는 이름은 출력될 수 없다.
# 은행권 이름에 법인 형태가 붙은 것(주식회사 카카오뱅크)은 **공시 이름 그대로** 둔다 — 상태 키가 그 이름을 쓴다(F5 · `0031`)
BANK_NAMES = [
    "경남은행", "광주은행", "국민은행", "농협은행주식회사", "부산은행", "수협은행", "신한은행", "아이엠뱅크", "우리은행",
    "전북은행", "제주은행", "주식회사 카카오뱅크", "주식회사 케이뱅크", "주식회사 하나은행", "중소기업은행", "토스뱅크 주식회사",
    "한국스탠다드차타드은행",
]
SAVINGS_NAMES = [
    "BNK저축은행", "IBK저축은행", "JT저축은행", "JT친애저축은행", "KB저축은행", "OK저축은행", "SBI저축은행", "고려저축은행",
    "금화저축은행", "다올저축은행", "디비저축은행", "민국저축은행", "부림저축은행", "삼정저축은행", "세람저축은행", "센트럴저축은행",
    "솔브레인저축은행", "스마트저축은행", "스카이저축은행", "스타저축은행", "신한저축은행", "안양저축은행", "애큐온저축은행",
    "엔에이치저축은행", "영진저축은행", "예가람저축은행", "우리금융저축은행", "웰컴저축은행", "유안타저축은행", "융창저축은행",
    "인천저축은행", "조은저축은행", "키움예스저축은행", "키움저축은행", "페퍼저축은행", "푸른저축은행", "하나저축은행", "한국투자저축은행",
]
ALL_NAMES = BANK_NAMES + SAVINGS_NAMES
# 사용자가 쓰는 짧은 이름 → 공시 이름. **모델이 고르는 enum 은 공시 이름**이고 이 표는 프롬프트에 "이렇게 부르면 이 이름" 으로만
# 보인다. 별칭 사전으로 판정에 쓰지 않는다(`CLAUDE.md` 5번) — 출력에는 공시 이름만 있다
COMMON_ALIASES = {
    "카카오뱅크": "주식회사 카카오뱅크", "카뱅": "주식회사 카카오뱅크", "케이뱅크": "주식회사 케이뱅크", "하나은행": "주식회사 하나은행",
    "토스뱅크": "토스뱅크 주식회사", "토스": "토스뱅크 주식회사", "농협": "농협은행주식회사", "농협은행": "농협은행주식회사",
    "기업은행": "중소기업은행", "IBK기업은행": "중소기업은행", "SC제일은행": "한국스탠다드차타드은행", "SC": "한국스탠다드차타드은행",
    "iM뱅크": "아이엠뱅크", "대구은행": "아이엠뱅크", "KB국민은행": "국민은행", "KB": "국민은행", "우리": "우리은행", "신한": "신한은행",
    "NH": "농협은행주식회사", "DB저축은행": "디비저축은행", "NH저축은행": "엔에이치저축은행",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "object",
            "properties": {
                "group": {"type": ["string", "null"], "enum": ["bank", "savingsbank", None]},
                "banks": {"type": "array", "items": {"type": "string", "enum": ALL_NAMES}},
                "kinds": {"type": ["string", "null"], "enum": ["예금", "적금", None]},
                "term_months": {"type": ["integer", "null"]},
                "amount_deposit": {"type": ["integer", "null"]},
                "amount_monthly": {"type": ["integer", "null"]},
            },
            "required": ["group", "banks", "kinds", "term_months", "amount_deposit", "amount_monthly"],
            "additionalProperties": False,
        },
        "traded": {
            "type": "object",
            "properties": {
                "mentioned": {"type": "boolean"},
                "banks": {"type": "array", "items": {"type": "string", "enum": ALL_NAMES}},
            },
            "required": ["mentioned", "banks"],
            "additionalProperties": False,
        },
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": CONDITION_TYPES},
                    "bank": {"type": ["string", "null"], "enum": ALL_NAMES + [None]},
                    "value": {"type": "string", "enum": ["예", "아니오", "모름"]},
                    "evidence": {"type": "string"},
                },
                "required": ["type", "bank", "value", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scope", "traded", "answers"],
    "additionalProperties": False,
}


def _type_lines() -> str:
    return "\n".join(f"- {t}: {C.TYPE_LABEL.get(t, t)} · {C.ask_tail(t)}" for t in CONDITION_TYPES if t != "기타")


SYSTEM_PROMPT_V1 = f"""사용자가 예금·적금을 찾으면서 자기 상황을 한국어로 적었다. 그 말에서 **사용자가 실제로 말한 것만** 구조화한다.
추측하지 않는다. 말하지 않은 칸은 null 또는 빈 배열로 둔다. 직장·가족·성격·다른 재산처럼 아래 칸과 무관한 정보는 어디에도 넣지 않는다.

## scope — 무엇을 찾나
- group: "저축은행" 이라고 말했으면 savingsbank, 은행 이름을 댔거나 그냥 은행이면 bank, 말이 없으면 null
- banks: 사용자가 보고 싶다고 한 은행(후보를 좁히는 은행). 공시 이름으로 적는다(아래 표). 말이 없으면 []
- kinds: 예금 또는 적금 하나. 둘 다 보거나 말이 없으면 null
- term_months: 가입 기간(개월). "1년" 은 12, "6개월" 은 6. 없으면 null
- amount_deposit: 예금에 한 번에 넣을 금액(원). "3천만원" 은 30000000. 없으면 null
- amount_monthly: 적금에 매달 넣을 금액(원). "월 30만원" 은 300000. 없으면 null

## traded — 거래해 본 은행
- mentioned: 사용자가 거래 은행에 대해 말했으면 true (거래한 곳이 있든 없든). 말이 없으면 false 이고 banks 는 []
- banks: 거래해 본(계좌가 있는·주거래인·급여를 받는·카드를 쓰는) 은행. "거래하는 은행 없다·처음이다" 면 mentioned true 에 banks []

## answers — 조건에 대한 답
사용자가 아래 조건 중 어느 것에 대해 **직접 말한 것만** 담는다. 말하지 않은 조건은 담지 않는다.
- type: 조건 유형(아래 목록의 이름 그대로)
- bank: 그 조건이 특정 은행에 대한 것이면 그 은행의 공시 이름, 은행이 정해지지 않았으면 null.
  급여_연금이체·자동이체·주거래_장기거래_재예치·첫거래_신규고객·카드실적·타상품_보유동시가입 은 보통 은행이 붙는다
- value: "예" = 해당된다 또는 하겠다(할 수 있다) · "아니오" = 해당 안 된다 또는 안 하겠다(못 한다) · "모름" = 사용자가 모르겠다고 했다
- evidence: 그 판단의 근거가 된 사용자 문장 조각을 그대로

조건 유형:
{_type_lines()}

## 은행 이름 (사용자가 이렇게 부르면 → 공시 이름)
{json.dumps(COMMON_ALIASES, ensure_ascii=False)}
공시 이름 전체: {json.dumps(ALL_NAMES, ensure_ascii=False)}
"""


# v2 (2026-09-07 · v1 측정 뒤 · `prereg-27` §6 에 무엇을 고쳤는지 적었다). 고친 것 넷 —
#  ① 첫거래 뒤집힘: "처음이야 · 첫 거래야" 를 첫거래_신규고객 **아니오**로 냈다(v1 · 2건) → 뜻을 명시
#  ② 은행 이름 권역 혼동: "하나은행" 을 하나저축은행으로 → "저축은행" 낱말이 없으면 은행권 이름
#  ③ 거래 은행 누락: "오래 썼고 · 계좌 있어 · 급여 받아 · 카드 써" 는 전부 거래 은행 → traded 에 넣는다고 명시
#  ④ 자격 진술: "만 65세" 처럼 자격을 사실로 말하면 고객군_자격 예 (모름이 아니다)
SYSTEM_PROMPT_V2 = SYSTEM_PROMPT_V1 + """
## 자주 틀리는 자리 — 이렇게 읽는다
- "거긴 처음이야 · 첫 거래야 · 한 번도 안 써봤어" → 그 은행과 **첫거래_신규고객: 예** (첫 거래가 맞다는 뜻이다. 아니오가 아니다).
  그리고 traded 는 mentioned true, 그 은행은 banks 에 넣지 않는다(거래한 적이 없으니까)
- "오래 썼어 · 주거래야 · 계좌 있어 · 급여 받아 · 카드 써" → 그 은행은 **거래 은행**이다. traded.banks 에 넣는다.
  "오래 썼어 · 주거래" 는 주거래_장기거래_재예치: 예 이기도 하다
- 은행 이름은 권역을 지킨다 — 사용자가 "저축은행" 이라고 말하지 않았으면 **은행권 이름**을 고른다.
  "하나은행" → 주식회사 하나은행 (하나저축은행이 아니다) · "신한" → 신한은행 · "우리" → 우리은행 · "국민" → 국민은행
- "만 65세 · 장애인 · 기초생활수급자" 처럼 자격을 사실로 말하면 고객군_자격: 예. 궁금하다고만 해도 자격 자체는 말한 것이다
- "옮길 생각 없어 · 못 옮겨 · 안 해 · 싫어" → 그 조건 아니오. "상관없어 · 걸어둘 수 있어 · 할게" → 예
- 은행이 정해지지 않았는데 조건을 말하면 bank 는 null 로 둔다 (아무 은행도 붙이지 않는다)
"""
PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}


def call(text: str, url: str = DEFAULT_URL, model: str = "local", system: str = SYSTEM_PROMPT_V1,
         timeout: int = TIMEOUT) -> tuple[dict | None, float, str | None]:
    """문장 하나 → (파싱된 dict 또는 None, 걸린 초, 오류). **원문을 저장하지 않는다.**"""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": {"name": "r2", "schema": SCHEMA}},
        # Qwen3.5 — thinking 을 끈다 (`CLAUDE.md`). 다른 모델은 이 키를 무시한다
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(f"{url.rstrip('/')}/v1/chat/completions",
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001 — 실패도 결과다
        return None, time.monotonic() - t0, f"{type(e).__name__}: {str(e)[:120]}"
    raw = (out.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        return json.loads(raw), time.monotonic() - t0, None
    except json.JSONDecodeError:
        return None, time.monotonic() - t0, f"JSON 아님: {raw[:80]}"


def to_candidates(parsed: dict, plan_keys: set[str] | None = None) -> dict:
    """모델 출력 → 화면·측정이 쓰는 모양. **후보 집합 밖 키는 버린다.**

    반환: {"scope": {...}, "traded": [...] | None, "answers": [{"key", "value", "evidence"}], "dropped": [...]}
    `traded` 는 목록(거래 은행) 또는 None(말 안 함). "없다" 는 [] 다.
    """
    sc = parsed.get("scope") or {}
    tr = parsed.get("traded") or {}
    answers, dropped = [], []
    for a in parsed.get("answers") or []:
        key = C.type_key(a["type"], a.get("bank") or "", force=bool(a.get("bank")))
        if plan_keys is not None and key not in plan_keys:
            dropped.append({"key": key, "value": a["value"]})
            continue
        answers.append({"key": key, "value": a["value"], "evidence": a.get("evidence", "")})
    return {"scope": {"group": sc.get("group"), "banks": sc.get("banks") or [], "kinds": sc.get("kinds"),
                      "term": sc.get("term_months"), "amount_deposit": sc.get("amount_deposit"),
                      "amount_monthly": sc.get("amount_monthly")},
            "traded": (tr.get("banks") or []) if tr.get("mentioned") else None,
            "answers": answers, "dropped": dropped}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    url = DEFAULT_URL
    if "--url" in argv:
        i = argv.index("--url"); url = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit('사용법: python src/analysis/r2_parse.py "문장" [--url http://127.0.0.1:8081]')
    parsed, secs, err = call(argv[0], url)
    if err:
        raise SystemExit(f"실패 ({secs:.1f}s): {err}")
    print(json.dumps(to_candidates(parsed), ensure_ascii=False, indent=2))
    print(f"\n{secs:.1f}초")


if __name__ == "__main__":
    main()
