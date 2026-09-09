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
# v3 (2026-09-07 · 2차 `prereg-28`) — 규칙을 늘리는 대신 **예시**를 보인다. v2 에서 4B 가 규칙이 늘자 없는 조건을 채웠다.
# 예시 문장은 DEV·TEST 어느 표본에도 없는 것이다
FEWSHOT = [
    ("농협은행 주거래고 급여도 거기로 받아. 적금 매달 20만원 2년",
     {"scope": {"group": "bank", "banks": ["농협은행주식회사"], "kinds": "적금", "term_months": 24, "amount_deposit": None,
                "amount_monthly": 200000},
      "traded": {"mentioned": True, "banks": ["농협은행주식회사"]},
      "answers": [{"type": "주거래_장기거래_재예치", "bank": "농협은행주식회사", "value": "예", "evidence": "농협은행 주거래고"},
                  {"type": "급여_연금이체", "bank": "농협은행주식회사", "value": "예", "evidence": "급여도 거기로 받아"}]}),
    ("전북은행은 처음 써봐. 카드는 안 만들 거야",
     {"scope": {"group": "bank", "banks": ["전북은행"], "kinds": None, "term_months": None, "amount_deposit": None, "amount_monthly": None},
      "traded": {"mentioned": True, "banks": []},
      "answers": [{"type": "첫거래_신규고객", "bank": "전북은행", "value": "예", "evidence": "전북은행은 처음 써봐"},
                  {"type": "카드실적", "bank": "전북은행", "value": "아니오", "evidence": "카드는 안 만들 거야"}]}),
    ("예금 1년에 4천만원. 요즘 야근이 많아서 정신없어",
     {"scope": {"group": None, "banks": [], "kinds": "예금", "term_months": 12, "amount_deposit": 40000000, "amount_monthly": None},
      "traded": {"mentioned": False, "banks": []},
      "answers": []}),
    ("다올저축은행이랑 인천저축은행 예금 있어. 이번엔 다른 저축은행 적금으로",
     {"scope": {"group": "savingsbank", "banks": [], "kinds": "적금", "term_months": None, "amount_deposit": None, "amount_monthly": None},
      "traded": {"mentioned": True, "banks": ["다올저축은행", "인천저축은행"]},
      "answers": []}),
]
SYSTEM_PROMPT_V3 = SYSTEM_PROMPT_V1 + "\n## 예시 — 이렇게 읽는다 (말한 것만 · 무관한 말은 무시 · 처음이다 = 첫거래 예)\n" + "\n".join(
    f"입력: {t}\n출력: {json.dumps(o, ensure_ascii=False)}" for t, o in FEWSHOT) + "\n"
# v4 (DEV 2판) — v3 에 예시 둘을 더한다: "거래 있어" 는 거래 은행일 뿐 주거래가 아니다 · 미션과 목표 납입은 다른 조건이다
FEWSHOT_V4 = FEWSHOT + [
    ("경남은행이랑 광주은행 둘 다 거래 있어. 예금 볼게",
     {"scope": {"group": "bank", "banks": [], "kinds": "예금", "term_months": None, "amount_deposit": None, "amount_monthly": None},
      "traded": {"mentioned": True, "banks": ["경남은행", "광주은행"]},
      "answers": []}),
    ("만보 걷기 챌린지 같은 거 재미있어서 잘 해",
     {"scope": {"group": None, "banks": [], "kinds": None, "term_months": None, "amount_deposit": None, "amount_monthly": None},
      "traded": {"mentioned": False, "banks": []},
      "answers": [{"type": "실천_미션_인증", "bank": None, "value": "예", "evidence": "챌린지 같은 거 재미있어서 잘 해"}]}),
]
SYSTEM_PROMPT_V4 = SYSTEM_PROMPT_V1 + "\n## 예시 — 이렇게 읽는다 (말한 것만 · 무관한 말은 무시 · 처음이다 = 첫거래 예 · 거래 있다 ≠ 주거래)\n" + "\n".join(
    f"입력: {t}\n출력: {json.dumps(o, ensure_ascii=False)}" for t, o in FEWSHOT_V4) + "\n"
PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2, "v3": SYSTEM_PROMPT_V3, "v4": SYSTEM_PROMPT_V4}


# ── v5 (2026-09-07 · 2차 TEST 뒤 · `prereg-28` §7) — 은행을 두 목록(보고 싶은 · 거래하는)에 나눠 담지 않고 **문장에 나온 은행마다
# 역할을 붙인다**. TEST 에서 거래 은행 오답 2건이 전부 "보고 싶은 은행을 거래로" · "거래 없다고 한 은행을 거래로" 였다 — 목록 둘이
# 섞인 것이다. 역할을 명시적으로 고르게 하면 부정("거래 없고")이 빠질 자리가 줄어든다.
ROLES = ["거래함", "거래없음", "보고싶음"]
SCHEMA_V5 = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "object",
            "properties": {
                "group": {"type": ["string", "null"], "enum": ["bank", "savingsbank", None]},
                "kinds": {"type": ["string", "null"], "enum": ["예금", "적금", None]},
                "term_months": {"type": ["integer", "null"]},
                "amount_deposit": {"type": ["integer", "null"]},
                "amount_monthly": {"type": ["integer", "null"]},
            },
            "required": ["group", "kinds", "term_months", "amount_deposit", "amount_monthly"],
            "additionalProperties": False,
        },
        # 문장에 나온 은행 **전부**, 하나씩 역할을 붙여서. 같은 은행에 역할이 둘이면 두 항목
        "banks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": ALL_NAMES},
                    "role": {"type": "string", "enum": ROLES},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "role", "evidence"],
                "additionalProperties": False,
            },
        },
        # "거래하는 은행 없어 · 처음이야" 처럼 은행 이름 없이 거래가 없다고 말했나
        "says_no_bank_relations": {"type": "boolean"},
        "answers": SCHEMA["properties"]["answers"],
    },
    "required": ["scope", "banks", "says_no_bank_relations", "answers"],
    "additionalProperties": False,
}

SYSTEM_PROMPT_V5 = f"""사용자가 예금·적금을 찾으면서 자기 상황을 한국어로 적었다. 그 말에서 **사용자가 실제로 말한 것만** 구조화한다.
추측하지 않는다. 말하지 않은 칸은 null 또는 빈 배열로 둔다. 직장·가족·성격·다른 재산처럼 아래 칸과 무관한 정보는 어디에도 넣지 않는다.

## scope — 무엇을 찾나
- group: "저축은행" 이라고 말했으면 savingsbank, 은행 이름을 댔거나 그냥 은행이면 bank, 말이 없으면 null
- kinds: 예금 또는 적금 하나. 둘 다 보거나 말이 없으면 null
- term_months: 가입 기간(개월). "1년" 은 12. 없으면 null
- amount_deposit: 예금에 한 번에 넣을 금액(원). "3천만원" 은 30000000. 없으면 null
- amount_monthly: 적금에 매달 넣을 금액(원). "월 30만원" 은 300000. 없으면 null

## banks — 문장에 나온 은행 **전부**, 하나씩 역할을 붙인다
- 거래함   그 은행과 거래가 있다 — 계좌 있다 · 주거래 · 급여 받는다 · 카드 쓴다 · 오래 썼다 · 써봤다
- 거래없음  그 은행과 거래가 없다 — "거래 없어" · "처음이야" · "첫 거래야" · "안 써봤어"
- 보고싶음  그 은행의 상품을 보고 싶다 · 그 은행으로 좁히고 싶다
같은 은행이 두 역할이면 항목을 둘 만든다 (예: "우리은행 주거래고 우리 적금 볼래" → 거래함 + 보고싶음).
**"거래 없고" 라고 한 은행을 거래함으로 두지 않는다. 보고 싶다고만 한 은행을 거래함으로 두지 않는다.**
evidence 에는 그 역할의 근거가 된 문장 조각을 그대로 적는다.

## says_no_bank_relations — 은행 이름 없이 "거래하는 은행 없어 · 저축은행은 처음이야" 라고 했으면 true

## answers — 조건에 대한 답 (사용자가 **직접 말한 것만**)
- type: 조건 유형(아래 목록의 이름 그대로) · bank: 그 조건이 특정 은행에 대한 것이면 공시 이름, 아니면 null
- value: "예" = 해당된다·하겟다·할 수 있다 · "아니오" = 해당 안 된다·안 하겟다·못 한다 · "모름" = 모르겠다고 했다
- evidence: 근거가 된 문장 조각 그대로
조건 유형:
{_type_lines()}

## 은행 이름 (이렇게 부르면 → 공시 이름 · "저축은행" 이라고 말하지 않았으면 은행권 이름을 고른다)
{json.dumps(COMMON_ALIASES, ensure_ascii=False)}
공시 이름 전체: {json.dumps(ALL_NAMES, ensure_ascii=False)}

## 예시
입력: 농협은행 주거래고 급여도 거기로 받아. 적금 매달 20만원 2년
출력: {json.dumps({"scope": {"group": "bank", "kinds": "적금", "term_months": 24, "amount_deposit": None, "amount_monthly": 200000},
                  "banks": [{"name": "농협은행주식회사", "role": "거래함", "evidence": "농협은행 주거래고"}],
                  "says_no_bank_relations": False,
                  "answers": [{"type": "주거래_장기거래_재예치", "bank": "농협은행주식회사", "value": "예", "evidence": "농협은행 주거래고"},
                              {"type": "급여_연금이체", "bank": "농협은행주식회사", "value": "예", "evidence": "급여도 거기로 받아"}]}, ensure_ascii=False)}
입력: 전북은행은 처음 써봐. 전북은행 예금 보고 있어. 카드는 안 만들 거야
출력: {json.dumps({"scope": {"group": "bank", "kinds": "예금", "term_months": None, "amount_deposit": None, "amount_monthly": None},
                  "banks": [{"name": "전북은행", "role": "거래없음", "evidence": "전북은행은 처음 써봐"},
                            {"name": "전북은행", "role": "보고싶음", "evidence": "전북은행 예금 보고 있어"}],
                  "says_no_bank_relations": False,
                  "answers": [{"type": "첫거래_신규고객", "bank": "전북은행", "value": "예", "evidence": "전북은행은 처음 써봐"},
                              {"type": "카드실적", "bank": "전북은행", "value": "아니오", "evidence": "카드는 안 만들 거야"}]}, ensure_ascii=False)}
입력: 예금 1년에 4천만원. 거래하는 은행은 없어. 요즘 야근이 많아서 정신없어
출력: {json.dumps({"scope": {"group": None, "kinds": "예금", "term_months": 12, "amount_deposit": 40000000, "amount_monthly": None},
                  "banks": [], "says_no_bank_relations": True, "answers": []}, ensure_ascii=False)}
입력: 광주은행 거래는 없고 경남은행만 써. 광주은행 적금이 좋아 보여서
출력: {json.dumps({"scope": {"group": "bank", "kinds": "적금", "term_months": None, "amount_deposit": None, "amount_monthly": None},
                  "banks": [{"name": "광주은행", "role": "거래없음", "evidence": "광주은행 거래는 없고"},
                            {"name": "경남은행", "role": "거래함", "evidence": "경남은행만 써"},
                            {"name": "광주은행", "role": "보고싶음", "evidence": "광주은행 적금이 좋아 보여서"}],
                  "says_no_bank_relations": False, "answers": []}, ensure_ascii=False)}
"""
PROMPTS["v5"] = SYSTEM_PROMPT_V5
SCHEMAS = {"v1": SCHEMA, "v2": SCHEMA, "v3": SCHEMA, "v4": SCHEMA, "v5": SCHEMA_V5}

VERIFY_SCHEMA = {"type": "object", "properties": {"거래한다고_말했나": {"type": "string", "enum": ["예", "아니오"]}},
                 "required": ["거래한다고_말했나"], "additionalProperties": False}
VERIFY_PROMPT = ("사용자 문장 하나와 은행 이름 하나를 준다. 사용자가 그 은행과 **실제로 거래한다**(계좌가 있다 · 주거래 · 급여를 받는다 · "
                 "카드를 쓴다 · 오래 썼다 · 써봤다)고 말했으면 \"예\". 그 은행 상품을 보고 싶다고만 했거나, 거래가 없다·처음이다라고 했거나, "
                 "그 은행을 말하지 않았으면 \"아니오\". 추측하지 않는다.")


def verify_traded(text: str, bank: str, url: str = DEFAULT_URL) -> tuple[bool | None, float]:
    """두 번째 호출 — 거래 은행 후보 하나를 문장에 대조한다 (`prereg-28` §7 방안 ②). (True/False/None=실패, 초)."""
    user = f"문장: {text}\n은행: {bank}\n이 은행과 거래한다고 말했나?"
    parsed, secs, err = call(user, url, system=VERIFY_PROMPT, schema=VERIFY_SCHEMA)
    if err or not parsed:
        return None, secs
    return parsed.get("거래한다고_말했나") == "예", secs


def call(text: str, url: str = DEFAULT_URL, model: str = "local", system: str = SYSTEM_PROMPT_V1,
         timeout: int = TIMEOUT, schema: dict | None = None) -> tuple[dict | None, float, str | None]:
    """문장 하나 → (파싱된 dict 또는 None, 걸린 초, 오류). **원문을 저장하지 않는다.**"""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": {"name": "r2", "schema": schema or SCHEMA}},
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


def _squash(s: str) -> str:
    return "".join((s or "").split())


def evidence_in_text(evidence: str, text: str) -> bool:
    """근거 조각이 **원문에 글자 그대로** 있나 (띄어쓰기만 무시). 없으면 모델이 지어낸 답이다 (`prereg-28` 근거 대조 필터)."""
    ev = _squash(evidence)
    return len(ev) >= 2 and ev in _squash(text)


def to_candidates(parsed: dict, plan_keys: set[str] | None = None, text: str | None = None) -> dict:
    """모델 출력 → 화면·측정이 쓰는 모양. **후보 집합 밖 키는 버리고, 근거가 원문에 없는 답도 버린다.**

    반환: {"scope": {...}, "traded": [...] | None, "answers": [{"key", "value", "evidence"}], "dropped": [...]}
    `traded` 는 목록(거래 은행) 또는 None(말 안 함). "없다" 는 [] 다.
    `dropped` 항목의 `why` 가 "후보밖" 또는 "근거없음" 이다 — 2차(`prereg-28`)에서 둘을 따로 센다.
    `text` 를 주면 근거 대조를 한다. 원문은 이 함수 안에서만 쓰고 저장하지 않는다.
    """
    sc = parsed.get("scope") or {}
    if "banks" in parsed and "traded" not in parsed:          # v5 — 은행마다 역할
        roles = parsed.get("banks") or []
        want = [b["name"] for b in roles if b["role"] == "보고싶음"]
        have = [b["name"] for b in roles if b["role"] == "거래함"]
        mentioned = bool(parsed.get("says_no_bank_relations")) or any(b["role"] in ("거래함", "거래없음") for b in roles)
        sc = {**sc, "banks": list(dict.fromkeys(want))}
        tr = {"mentioned": mentioned, "banks": list(dict.fromkeys(have))}
    else:
        tr = parsed.get("traded") or {}
    answers, dropped = [], []
    for a in parsed.get("answers") or []:
        # 기관은 **기관 상대 유형에만** 붙인다 — 상태 키의 규칙(`type_key`)이 그렇다. 모델이 쿠폰·고객군 같은 기관 무관
        # 유형에 은행을 붙여도 키는 유형 이름 하나다 (DEV v3 에서 `쿠폰_코드_추천인@케이뱅크` 가 그렇게 나왔다)
        bank = (a.get("bank") or "") if a["type"] in C.INSTITUTION_RELATIVE else ""
        key = C.type_key(a["type"], bank, force=bool(bank))
        if plan_keys is not None and key not in plan_keys:
            dropped.append({"key": key, "value": a["value"], "why": "후보밖"})
            continue
        if text is not None and not evidence_in_text(a.get("evidence", ""), text):
            dropped.append({"key": key, "value": a["value"], "why": "근거없음"})
            continue
        answers.append({"key": key, "value": a["value"], "evidence": a.get("evidence", "")})
    return {"scope": {"group": sc.get("group"), "banks": sc.get("banks") or [], "kinds": sc.get("kinds"),
                      "term": sc.get("term_months"), "amount_deposit": sc.get("amount_deposit"),
                      "amount_monthly": sc.get("amount_monthly")},
            "traded": (tr.get("banks") or []) if tr.get("mentioned") else None,
            "answers": answers, "dropped": dropped}


# ── 화면용 (2026-09-09 · `prereg-29` · `0060` D2·D3·D6) — 스코프 다섯 칸만 낸다. 조건 답·거래 은행은 여기서 나가지 않는다
PREFILL_TIMEOUT = 30          # 폼 요청에 실리는 호출이다 — 120초를 기다리게 하지 않는다
# 금액 두 칸은 **미리 채우지 않는다** (2026-09-09 · `0060` 반증 조건 4 발동 · `prereg-29` §7). 사람 세션에서 한글 숫자 "오천만원" 을
# 세 번 연속 500만원으로 읽었다. 아라비아 숫자("3천만원")는 맞았지만, 관측 뒤에 규칙을 좁히지 않는다 — 조항대로 뺀다. 모델 출력에는 남아 있고 읽지 않는다
PREFILL_FIELDS = ("group", "company", "kinds", "term")


def prefill(text: str, url: str = DEFAULT_URL) -> tuple[dict[str, str], float, str | None]:
    """문장 하나 → 0단계 폼의 네 칸 값 (권역·은행·예금/적금·기간 · 문자열 · 폼에 그대로 꽂는 모양). `(칸, 초, 오류)`.

    v5(은행 역할 스키마) **한 번** 호출한다 (`prereg-29` §2). 읽는 것은 scope 네 칸과 "보고싶음" 역할의 은행만이다 —
    "거래함"·"거래없음" 과 answers 는 **읽지 않는다**(`0060` D1·D3). 모델이 null 로 둔 칸은 결과에 없다.
    원문은 호출에만 쓰고 저장하지 않는다. 빈 문장은 호출하지 않고 빈 dict 를 돌려준다.
    """
    if not text or not text.strip():
        return {}, 0.0, None
    parsed, secs, err = call(text.strip(), url, system=SYSTEM_PROMPT_V5, schema=SCHEMA_V5, timeout=PREFILL_TIMEOUT)
    if err or not parsed:
        return {}, secs, err or "빈 응답"
    cand = to_candidates(parsed)
    sc = cand["scope"]
    out: dict[str, str] = {}
    if sc.get("group") in ("bank", "savingsbank"):
        out["group"] = sc["group"]
    if sc.get("banks"):
        out["company"] = ",".join(sc["banks"])
    if sc.get("kinds") in ("예금", "적금"):
        out["kinds"] = sc["kinds"]
    if isinstance(sc.get("term"), int) and 1 <= sc["term"] <= 60:
        out["term"] = str(sc["term"])
    # amount_deposit · amount_monthly 는 내지 않는다 — 위 PREFILL_FIELDS 주석
    return out, secs, None


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
