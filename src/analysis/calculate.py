# -*- coding: utf-8 -*-
"""사용자 상태로 상품별 실수령 금리를 계산한다 — `../../docs/spec/design.md` §2 계산기.

이 파일이 채우는 자리
    추출(R1)은 되는데 그걸로 **사용자별 금리를 계산하는 코드가 없었다.** 이슈 #2다.
    계산기 5단계 중 3번(사용자 상태로 충족 여부 판정)이 여기서 처음 구현된다.

    1. applies_to_term 이 false 인 항목 제거
    2. exclusive_group 은 합이 아니라 그룹 최댓값
    3. 사용자 상태로 충족 여부 판정          ← 이 파일
    4. 충족분 합계에 cap 적용
    5. 기본금리 + 위 값                     = 세전
    6. 세율 적용                            = 세후

**모르는 것을 추측하지 않는다.** 판정할 수 없는 조건이 있으면 하나의 숫자가 아니라
**범위**를 낸다 — 최소(확실히 충족되는 것만) ~ 최대(모르는 것을 다 충족으로 가정).
세금에서 두 시나리오를 보여주기로 한 것과 같은 방침이다.

## 공시 최고금리를 상한으로 건다 — 그리고 그게 무엇을 가리는지 적어둔다

계산값이 공시 최고금리를 넘으면 **공시 값으로 자른다.** 사용자가 공시보다 많이 받을
수는 없으므로 이 상한은 항상 참이다.

**왜 필요한가** — 계산값이 공시 최고금리를 넘는 행이 저축은행 12개월 297개 중 **182개**
였다. 상한이 없으면 공시에 없는 금리를 사용자에게 보여준다(관측된 최악 11.50% → 8.00%).

**넘치는 이유는 대부분 우리 잘못이 아니다** (E10). 전체 기간 705행 중 **682행(96.7%)이
공시 최고금리 = 기본금리인 행**이다 — 조건문에 "비대면 가입시 0.1%"가 적혀 있고 우리는
정확히 뽑았는데 공시가 그 값을 최고금리 칸에 넣지 않았다. **진짜 과다 추출은 23행(3.3%)뿐이다.**
그래서 층을 `공시미반영`과 `추출불확실`로 나눈다.

```
사용자에게      상한을 적용한 값을 보여준다        과대 진술이 불가능해진다
측정에는        상한 전 원값을 남긴다 (raw_hi)     추출이 나아졌는지 계속 잴 수 있다
```

닫는 것만 남기고 문제를 버리면 닫힘률이 자동으로 100%가 되어 개선을 측정할 수 없다.
그래서 **상품을 제외하지 않고 층 라벨을 붙인다**(아래 `TIERS`).

사용법:
    python src/analysis/calculate.py 20260825 --group savingsbank --top 10
    python src/analysis/calculate.py 20260826 --state 급여_연금이체,카드실적 --term 12
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_llm import CONDITION_TYPES, load_pairs  # noqa: E402
from finlife_rules import TOLERANCE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PATH = REPO_ROOT / "config" / "tax-2026.json"
OUT_DIR = REPO_ROOT / "data" / "pilot"

# 사용자가 O/X 로 답할 수 없는 유형 — `decisions/0005` 의 층 2
ALWAYS_MET = {"무조건_특판_이벤트"}      # 가입고객 모두에게 적용된다

# 공시가 우대금리 금액만 적고 **무슨 조건인지 안 밝힌** 항목에 붙이는 유형
# (`no_condition()` · `decisions/0019`). 추출 스키마의 17종에는 없다 — 추출기가 내는
# 값이 아니라 **우리가 판정 단계에서 붙이는 라벨**이라서 섞이면 안 된다.
UNCLEAR_TYPE = "조건불명_공시미기재"
UNDECIDABLE = {"판정불가_불특정", UNCLEAR_TYPE}   # 물어도 판정할 수 없다

# ── 금액·횟수 임계 (A안 · `../../docs/spec/prereg-06-matching-and-judgment.md` §1.3)
#
# 조건에 "3천만원 이상" · "6회 이상" 같은 임계가 붙어 있으면, 사용자가 "O" 라고
# 답했더라도 충족인지 알 수 없다. **추측하지 않고 판정 불가로 두어 범위에 넣는다.**
# 충족으로 계산하면 실제보다 높은 금리를 보여주고, 그게 잡으려던 실패다.
#
# 기간 한정("6개월 이상")은 여기서 빼는데, `applies_to_term` 이 이미 처리한다.
# 넣으면 121건이 아니라 205건이 판정 불가가 되어 과하게 흐려진다.
#
# 실측 — 조건 항목 1,051개 중 121개(11.5%)  금액 58 · 횟수·인원 64 (겹침 1)
# 단위 목록은 아래 MONEY_UNIT 과 같아야 한다 — 여기서 놓치면 임계인 줄 모르고
# 사용자 답을 그대로 충족으로 세어 과대 진술이 된다.
# **띄어쓰기가 없어도 잡아야 한다.** `(?![가-힣])` 만 두면 `"1천만원이상"` 이
# 안 잡혀서, 임계인 줄 모르고 사용자 "예" 답을 그대로 충족으로 세게 된다
# (36건 · 3.4% · 광주 27 · 안양 6 · 경남 3 — `decisions/0019`). 과대 진술 방향이다.
# `prereg-06` §1.1 이 `천만원` 단위 누락으로 겪은 것과 **같은 종류의 두 번째 구멍**이다.
THRESHOLD_MONEY = re.compile(
    r"\d[\d,]*\s*(천만원|백만원|십만원|억원|만원|천원|억|원)"
    r"(?:\s*(?:이상|이하|미만|초과|까지))?(?![가-힣])")
THRESHOLD_COUNT = re.compile(r"\d+\s*(회|건|명|개|일|주차|좌)\s*(이상|이내|초과|미만|까지)")


# 한 항목의 우대금리 상한. 이보다 크면 금리가 아니다 —
# AI 가 "5천만원 이상 가입" 에서 5000 · 5000000 을 rate 로 뽑은 사례가 2건 있었다
# (은행권 711개 항목 중 0.3%). 스키마에 상한이 없어 통과했다.
# 예적금 우대금리 한 항목이 20%p 를 넘는 경우는 없다 — 관측 최대는 9.0%p 다.
MAX_ITEM_RATE = 20.0


def sane_rate(item: dict) -> float:
    """항목의 금리. 상한을 넘으면 0으로 본다 (금액을 금리로 오인한 것)."""
    r = float(item.get("rate") or 0)
    return r if 0 <= r <= MAX_ITEM_RATE else 0.0


def has_threshold(item: dict) -> bool:
    """근거 문구에 금액·횟수 임계가 있는가. 있으면 사용자 답만으로 판정할 수 없다."""
    ev = item.get("evidence") or ""
    return bool(THRESHOLD_MONEY.search(ev) or THRESHOLD_COUNT.search(ev))


# ── B안 — 임계 수치를 파싱해 사용자에게 되묻는다 (`prereg-06` §1.3)
#
# A안은 임계가 붙은 조건을 판정 불가로 뒀다. B는 **수치를 물어서 판정한다.**
# 재추출($1)이 필요할 줄 알았는데 **필요 없다** — 근거 문구에 숫자가 이미 있다.
# 고유 임계 항목 56개 중 50개(89.3%)가 숫자 하나로 깔끔하게 파싱된다.
#
# 파싱되는 형태          "월 50만원 이상"  "자동이체 6회 이상"  "3천만원 이상 보유"
# 파싱 안 되는 형태      계단식 우대 6건 — 아래 LADDER 주석
#
# 사용자 답은 상태 딕셔너리에 **단위를 붙인 키**로 받는다. 유형만 O/X 로 받으면
# 금액인지 횟수인지 알 수 없어 엉뚱한 비교를 하게 된다.
#     state["자동이체"] = True            "자동이체 하십니까"       → 예
#     state["자동이체_횟수"] = 6           "월 몇 회 하십니까"       → 6회
#     state["잔액_평잔_가입금액_금액"] = 5_000_000
# 공시는 "5천만원" 처럼 한글 자릿수를 섞어 쓴다. **긴 단위를 먼저 시도해야 한다** —
# "천만원"을 "만원"으로 읽으면 5천만원이 5만원이 된다 (1,000배 오차).
MONEY_UNIT = {"원": 1, "천원": 1_000, "만원": 10_000,
              "십만원": 100_000, "백만원": 1_000_000, "천만원": 10_000_000,
              "억원": 100_000_000, "억": 100_000_000}
# **짝 정규식을 맞춘다** (`prereg-08`). 위 `THRESHOLD_MONEY` 는 `"500만원이상"` 의
# `이상` 을 흡수하는데 여기에는 그 부분이 없었다. 그래서 `has_threshold()` 는 "임계가
# 있다", `parse_threshold()` 는 "못 읽겠다" 를 내고 코드가 그것을 **계단식으로 오분류**했다.
# `단계불명`(되물어도 못 없앤다) 으로 나가던 문구 8종 중 대부분이 실은 임계 하나짜리였다.
#
# 같은 종류의 **세 번째 구멍**이다 — `천만원` 단위 누락(`prereg-06` §1.1) ·
# 붙여쓰기 미탐 36건(`0019`) · 짝 불일치(여기). 앞의 둘을 고칠 때 이 짝을 안 봤다.
MONEY_VALUE = re.compile(
    r"(\d[\d,]*)\s*(천만원|백만원|십만원|억원|만원|천원|억|원)"
    r"(?:\s*(?:이상|이하|미만|초과|까지))?(?![가-힣])")
COUNT_VALUE = re.compile(r"(\d+)\s*(?:회|건|명|개|일|주차|좌)\s*(이상|이내|초과|미만|까지)")
AT_LEAST = re.compile(r"(이상|초과|부터)")
AT_MOST = re.compile(r"(이내|미만|이하|까지)")


def parse_threshold(item: dict) -> tuple[str, float, str] | None:
    """근거 문구의 임계를 (단위, 값, 방향) 으로 읽는다. 애매하면 None 을 낸다.

    **애매한 것을 추측하지 않는다.** 숫자가 둘 이상이면 어느 것이 임계인지 알 수
    없으므로 판정 불가로 남긴다 — 대부분 계단식 우대다 (LADDER 주석 참고).
    """
    ev = item.get("evidence") or ""
    hits = [("금액", int(m.group(1).replace(",", "")) * MONEY_UNIT[m.group(2)])
            for m in MONEY_VALUE.finditer(ev)]
    hits += [("횟수", int(m.group(1))) for m in COUNT_VALUE.finditer(ev)]
    if len(hits) != 1:
        return None
    unit, value = hits[0]
    return unit, float(value), "최소" if AT_LEAST.search(ev) or not AT_MOST.search(ev) else "최대"


# 계단식 우대 — 하나의 조건에 임계가 여러 개이고 금리도 단계별로 다르다.
#
#     "자동이체 입금횟수 우대금리 : 최고 0.5%p - 5회이상 : 0.2%p,
#      10회이상 : 0.3%p, 15회이상 0.5%p"
#
# **추출기가 이걸 항목 하나로 접었다** (가장 높은 금리만 남겼다). 스키마에 단계를
# 담을 자리가 없기 때문이다. 판정 불가로 남긴다 — 사용자 답이 10회면 0.3%p 인데
# 우리는 0.5%p 만 안다. **추측하면 과대 진술이다.**
#
# **규모가 처음 센 것보다 훨씬 작다** (`prereg-08`). `prereg-06` §1.6 은 11문구라
# 적었는데, 그중 8문구는 계단이 아니라 **짝 정규식이 안 맞아 못 읽은 단일 임계**였다
# (위 `MONEY_VALUE` 주석). 진짜 계단은 3문구다.
#
#     "요구불평잔 : 0.2% -300만원이상 0.1%, 500만원이상 0.2%"
#     "신용(체크)카드결제실적 : 0.1% -전월결제금 300만원이상 0.05%, 500만원이상 0.1%"
#     "당 저축은행 APP 월1회 이상 로그인 기록 횟수에 따라 차등적용+2.0% (12회이상:2.0%)"
#
# 이 3문구는 그대로 `단계불명` 으로 낸다 (`prereg-06` §1.6 후보 A). 스키마에 `tiers` 를
# 넣는 후보 B 는 **기각했다** — 3문구를 위해 재추출하지 않는다. 사람이 정한 방향이
# "추출하기보다 질문" 이고, 질문으로 낼 수 있는 것은 위 8문구였다 (`prereg-08` §0).


def threshold_question(item: dict) -> tuple[str, str, float, str] | None:
    """이 조건을 판정하려면 무엇을 물어야 하는가. (상태 키, 단위, 값, 방향)"""
    parsed = parse_threshold(item)
    if parsed is None:
        return None
    unit, value, direction = parsed
    return f"{item.get('condition_type')}_{unit}", unit, value, direction


def question_for(item: dict, state: dict) -> dict | None:
    """판정 못 한 항목을 **되물을 질문**으로 바꾼다. 물어도 소용없으면 None.

    **문구를 그대로 인용한다.** 우리가 요약하면 사용자가 판단할 근거를 빼앗는다 —
    "ESG 실천 우대금리 1.00%" 처럼 공시가 무엇을 하라는지 안 밝힌 조건도, 원문을
    보여주고 "충족하십니까 / 모르겠습니다" 를 받는 것이 우리가 대신 추측하는 것보다 낫다.
    """
    kind = item.get("condition_type")
    if kind in UNDECIDABLE:
        return None                      # 추첨·랜덤 — 사용자도 은행도 미리 모른다
    answered = state.get(kind)
    if answered == UNSURE:
        return None                      # 이미 물었고 "모르겠다" 였다
    if answered and has_threshold(item):
        q = threshold_question(item)
        if q is None:
            return None                  # 계단식 — 수치를 받아도 금리를 모른다
        key, unit, need, direction = q
        return {"key": key, "kind": kind, "unit": unit, "need": need,
                "direction": direction, "evidence": item.get("evidence") or ""}
    if answered is None:
        return {"key": kind, "kind": kind, "unit": "예아니오", "need": None,
                "direction": None, "evidence": item.get("evidence") or ""}
    return None


def caveats_for(items_unknown: list[dict], items_met: list[dict], state: dict) -> list[str]:
    """왜 확정하지 못했는지 · 무엇을 주의해야 하는지 사유 코드로 모은다."""
    out = []
    for it in items_unknown:
        kind = it.get("condition_type")
        if kind == UNCLEAR_TYPE:
            out.append("조건불명")       # 공시가 조건을 안 적었다 — 우리 잘못이 아니다
        elif kind in UNDECIDABLE:
            out.append("추첨")           # 랜덤·추첨 — 은행도 미리 모른다
        elif state.get(kind) == UNSURE:
            out.append("모름")
        elif state.get(kind) and has_threshold(it):
            out.append("수치필요" if threshold_question(it) else "단계불명")
        else:
            out.append("미응답")
    if any(it.get("condition_type") in ONGOING for it in items_met):
        out.append("이행필요")
    seen, uniq = set(), []
    for c in out:                        # 순서를 지키면서 중복만 뺀다
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq

# ── 자기일관성 — 같은 문구는 같은 유형으로 통일한다 (`decisions/0020`)
#
# **무엇을 고치나** — 추출기가 **같은 근거 문구를 행마다 다른 유형으로** 분류한다.
# 고유 문구 372종 중 **9종 · 항목 47개(4.5%)**가 그렇다.
#
#     12개   "신규고객 또는 정기예금 중도해지고객 우대이율 0.75%p"  {첫거래 6, 주거래 6}
#      4개   "아파트관리비 이체"                       {급여_연금이체 2, 기타 1, 자동이체 1}
#      4개   "출산예정인자-배우자 포함"                  {고객군_자격 3, 기타 1}
#      3개   "온라인.재예치우대"                       {주거래 2, 비대면_채널가입 1}
#
# 같은 문구인데 상품마다 다른 질문으로 가면, **어떤 상품은 되묻고 어떤 상품은 안 묻는다.**
# 사용자가 보는 화면이 이유 없이 갈린다.
#
# **이건 별칭 사전이 아니다.** `CLAUDE.md` 5번이 금지한 것은 손으로 쓴 매핑표
# (`"아파트관리비 이체"` -> `자동이체`)다. 여기서 쓰는 것은 **데이터에 이미 있는 표**이고,
# 사람이 정하는 값이 하나도 없다. 다수결이 바뀌면 표도 따라 바뀐다.
#
# **한계를 분명히 적는다 — 이 규칙은 분산을 줄이지 편향을 줄이지 않는다.**
# `"아파트관리비 이체"`는 다수결이 `급여_연금이체`(2표)로 가는데 **틀린 답**이다
# (아파트관리비는 자동이체다). 4:1로 흔들리던 것이 **4:0으로 일관되게 틀리는** 것으로
# 바뀐다. 화면은 일관돼지고 정답률은 그대로다. 정답률을 올리려면 추출을 고쳐야 한다
# (`prereg-07` · A군 재추출).
#
# **동점이면 손대지 않는다.** 6:6인 문구가 하나 있는데(`"신규고객 또는 정기예금
# 중도해지고객..."`), 다수결로 정할 근거가 없으면 정하지 않는다. 그게 이 프로젝트가
# 반복해 온 규칙이다 — 모르는 것을 추측하지 않는다.


def unify_types(llm: dict) -> tuple[dict, dict]:
    """같은 근거 문구에 붙은 유형을 다수결로 통일한다. (바뀐 payload, 통계)"""
    votes: dict[str, Counter] = {}
    for p in llm.get("pairs", []):
        for it in (p.get("parsed") or {}).get("items", []) or []:
            ev = (it.get("evidence") or "").strip()
            if ev:
                votes.setdefault(ev, Counter())[it.get("condition_type")] += 1
    winner, tied = {}, 0
    for ev, c in votes.items():
        if len(c) < 2:
            continue
        top = c.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            tied += 1                     # 동점 — 근거가 없으면 정하지 않는다
            continue
        winner[ev] = top[0][0]
    n_changed = 0
    for p in llm.get("pairs", []):
        parsed = p.get("parsed") or {}
        items = parsed.get("items")
        if not items:
            continue
        new = []
        for it in items:
            ev = (it.get("evidence") or "").strip()
            want = winner.get(ev)
            if want and want != it.get("condition_type"):
                it = {**it, "condition_type": want}
                n_changed += 1
            new.append(it)
        parsed["items"] = new
    return llm, {"문구": len(winner), "동점": tied, "바뀐 항목": n_changed}


# ── 조건이 아닌 문구를 걸러낸다 (`decisions/0019` · `prereg-06` §1.8)
#
# **무엇을 잡나** — 공시가 **금리 숫자만 적고 무슨 조건인지 안 밝힌 문구**다.
# 사람이 표본 40건을 읽다가 나왔다.
#
#     "우대이율 6개월 이상 2.20%"        부산은행. 이게 조건문의 전부다
#     "계약기간 24개월 이상"             가입기간이다. applies_to_term 이 처리할 자리
#     "12개월 정기예금(대면) 기본금리(연 3.70%)+ 기본 우대금리(연 0.10%)"
#
# **왜 그냥 두면 안 되나** — 셋 다 사용자 화면에서 나쁜 방향으로 샌다.
#   `기타` 로 갔으면          "해당되십니까" 를 묻고, "예" 면 2.20%p 를 다 준 것으로 센다
#   `무조건_특판_이벤트` 로 갔으면  **아무것도 안 물어도 항상 충족**이다. 4건이 여기 있었다
# 공시가 무슨 조건인지 한 글자도 안 적었는데 우리가 "받는다" 고 계산해 보여주는 것이다.
# 이 프로젝트가 막으려던 피해 사례가 정확히 그 모양이다.
#
# **규칙 — 문구를 하드코딩하지 않는다.** 숫자와 껍데기 말을 걷어내고 **아무것도 안
# 남으면** 그건 조건이 아니다. `기타` 40건 중 정확히 13건을 집어낸다(넘치지도 모자라지도
# 않는다). 재추출이 필요 없어 비용은 $0 이다.
#
#     "우대이율 6개월 이상 2.20%"  ->  ""              조건 아님
#     "계약기간 24개월 이상"        ->  ""              조건 아님
#     "소중한 날"                 ->  "소중한날"        조건이다. 묻는다
#     "아파트관리비 이체"           ->  "아파트관리비이체"  조건이다
#
# **금액·횟수 임계가 붙은 것은 제외한다.** "1천만원 이상" 은 숫자를 걷어내면 빈 문자열이
# 되지만 **진짜 조건**이다. `has_threshold()` 로 먼저 걸러야 오탐이 안 난다.
#
# 남은 것을 둘로 가른다 — **금리 표기가 있느냐**로 가른다.
#   금리가 없다  "계약기간 24개월 이상"     항목 자체가 아니다.  **뺀다**
#   금리가 있다  "우대이율 6개월 이상 2.20%" 금액은 공시가 알려줬다. **금리는 남기고
#                                        판정 불가로 둔다** — 빼면 정보가 사라진다
NO_COND_NUM = re.compile(
    r"\d[\d,\.]*\s*(?:%p|%|개월|년|일|회|건|명|개|원|만원|천만원|억원|점|p)?")
NO_COND_SHELL = re.compile(
    r"(우대이율|우대금리|기본금리|기본|정기예금|정기적금|계약기간|가입기간|"
    r"최대|최고|최저|이상|미만|이하|초과|연|제|대면|비대면|적용|해당|"
    r"금리|이율|주기|변동|회전|시|의|및|또는|등|\(|\)|:|·|~|\+|-|,|\s)")
HAS_RATE = re.compile(r"\d[\d,\.]*\s*%")


def no_condition(item: dict) -> str | None:
    """조건이 아닌 문구인가. `"제외"` · `"조건불명"` · None 중 하나를 낸다."""
    if has_threshold(item):
        return None                        # "1천만원 이상" — 숫자를 걷어내도 진짜 조건이다
    ev = item.get("evidence") or ""
    if NO_COND_SHELL.sub("", NO_COND_NUM.sub("", ev)).strip():
        return None                        # 무언가 남았다 — 사용자에게 물을 말이 있다
    return "조건불명" if HAS_RATE.search(ev) else "제외"


# ── 질문 예산과 우선순위 (`../../docs/spec/prereg-06-matching-and-judgment.md` §2.3(1))
#
# **왜 예산이 필요한가** — 되묻기를 넣으니 은행권 범위가 0이 됐다. 그런데 실측해 보니
# **메인 층 수는 질문에 전혀 안 변하고**(은행권 64 고정), **범위 폭 평균은 질문 수의
# 단조 감소 함수**였다. 즉 "질문을 많이 만들면 지표가 좋아진다" 는 구멍이 열려 있었다.
# 선행 저장소에서 `"UNSUPPORTED"` 만 반환하는 상수 스텁이 1·2·3순위 지표를 전부 이긴
# 것과 같은 구조다. **답할 리 없는 질문 25개를 만들어도 확정률은 오른다.**
#
# 그래서 **질문 개수를 재기 전에 못 박고, 예산 안에서만 지표를 잰다**(`decisions/0018`).
# 예산을 넘는 질문은 화면에 띄우든 말든 자유지만 **평가 지표에는 안 들어간다.**
ASK_BUDGET = 12          # 평가에 반영하는 질문 개수. 수확 체감이 여기서 꺾인다

# **우선순위 규칙도 같이 못 박는다.** 안 그러면 "상위 12개" 를 사후에 고르는 우회가
# 생긴다 — 결과를 보고 유리한 질문 12개를 상위로 올리면 예산 제약이 무력해진다.
#
#   1순위   상품 커버리지 내림차순 — 그 질문 하나가 판정을 여는 상품 수
#   2순위   질문 키 사전순 — **내용에 무관한 기준을 일부러 골랐다.** 금리 크기 같은
#           의미 있는 기준을 2순위로 두면 시스템이 추출값을 키워 순위를 밀어올릴 수 있다
#
# 동점은 실제로 예산 경계에 걸린다 — 은행권 11·12위가 둘 다 7상품(`고객군_자격`·`기타`),
# 저축은행 11·12위가 둘 다 4상품이다. **누가 예산 안에 드는지를 2순위가 정한다.**
#
# 질문 하나의 단위는 **조건 유형 하나**다(`decisions/0016`). 유형 여러 개를 한 질문으로
# 합쳐 예산을 아끼는 우회를 막는다. 수치 후속 질문(`_금액`·`_횟수`)은 별도로 센다.


# ── 상태바 — 남은 질문이 절대 늘어나지 않게 한다 (`decisions/0024`)
#
# **문제** — `rank_questions()` 는 **지금 물을 수 있는** 질문만 낸다. 유형에 "예" 라고
# 답하면 수치 후속 질문이 새로 생기므로 **남은 수가 늘어난다.** 실측으로 은행권 6곳 ·
# 저축은행 12곳에서 줄지 않거나 늘었다 (15번째 뒤 5개 → 16번째 뒤 6개).
#
# 상태바가 뒤로 가면 사용자는 "끝이 안 나는구나" 로 읽는다.
#
# **해법 — 처음부터 "모두 예" 를 가정한 최대치를 분모로 쓴다.** 그러면 답할 때마다
# 남은 수가 **구조적으로** 줄어든다. "아니오"·"모르겠다" 는 그 유형의 수치 후속까지
# 같이 지우므로 2~3개씩 줄어든다 — 조건을 못 채우는 사용자일수록 빨리 끝난다.
#
#     은행권 22개 = 유형 15 + 수치 후속 7      저축은행 27개 = 유형 13 + 수치 후속 14
#
# 이 집합은 **아무것도 안 물은 상태에서 추출 데이터만으로 미리 계산된다.** 시뮬레이션이
# 필요 없다. 실측으로 전부 답했을 때의 실제 질문 수(22 · 27)와 정확히 일치한다.


def question_plan(rows: list[dict], by_pair: dict) -> dict[str, set[str]]:
    """`{조건 유형: {수치 후속 질문 키}}`. "모두 예" 를 가정한 최대 질문 집합이다."""
    plan: dict[str, set[str]] = {}
    for row in rows:
        got = by_pair.get(row["pair_id"])
        if not got or not got.get("schema_ok"):
            continue
        for it in (got["parsed"].get("items") or []):
            if not it.get("applies_to_term"):
                continue
            verdict = no_condition(it)
            if verdict == "제외":
                continue
            kind = UNCLEAR_TYPE if verdict == "조건불명" else it.get("condition_type")
            if kind in UNDECIDABLE or kind in ALWAYS_MET:
                continue                      # 물어도 소용없다 — 추첨·항상 충족
            plan.setdefault(kind, set())
            q = threshold_question(it) if has_threshold(it) else None
            if q:
                plan[kind].add(q[0])
    return plan


def questions_left(plan: dict[str, set[str]], state: dict) -> int:
    """화면에 띄울 남은 질문 수. 이 값은 답할 때마다 절대 늘어나지 않는다."""
    n = 0
    for kind, subs in plan.items():
        answered = state.get(kind)
        if answered is None:
            n += 1 + len(subs)                # 아직 안 물었다 — 후속까지 상정한다
        elif answered is False or answered == UNSURE:
            n += 0                            # 아니다/모른다 — 후속도 물을 필요가 없다
        else:
            n += sum(1 for s in subs if s not in state)
    return n


def rank_questions(scored: list[dict]) -> list[tuple[str, dict]]:
    """되물을 질문을 **고정된 우선순위**로 줄 세운다. 위 주석이 그 규칙이다."""
    asks: dict[str, dict] = {}
    for s in scored:
        for q in s.get("questions", []):
            slot = asks.setdefault(q["key"], {"unit": q["unit"], "codes": set(),
                                              "needs": set(), "kind": q["kind"],
                                              "evidence": set()})
            slot["codes"].add(s["code"])
            if q["need"] is not None:
                slot["needs"].add(q["need"])
            if q["evidence"]:
                slot["evidence"].add(q["evidence"][:74])
    return sorted(asks.items(), key=lambda kv: (-len(kv[1]["codes"]), kv[0]))


# 층 라벨 — 제외하지 않고 라벨로 가른다. 메인 화면은 이 라벨로 자른다
#
# `공시미반영` 을 따로 둔 이유 (E10, 2026-08-26)
#     처음에는 넘치는 행 전부를 `추출불확실`(우리 잘못)로 묶었다. 세어 보니 틀렸다 —
#     넘침 705행 중 682행(96.7%)이 **공시 최고금리 = 기본금리** 인 행이었다.
#     조건문에 "비대면 가입시 0.1%" 가 적혀 있고 우리는 정확히 뽑았는데, 공시가
#     그 0.1% 를 최고금리 칸에 넣지 않은 것이다. 우리 잘못이 아니다.
#     진짜 과다 추출은 23행(3.3%)뿐이었다.
#
#     두 층은 사용자에게 완전히 다른 말을 해야 한다 —
#     하나는 "공시가 이상하다", 하나는 "우리 해석이 불확실하다".
TIERS = {
    "확정":       "조건 합계가 공시와 맞고, 사용자가 모든 조건에 답했다",
    "범위":       "합계는 맞지만 사용자가 답하지 않은 조건이 있다",
    "공시미반영":  "조건문에는 우대금리가 있는데 공시 최고금리에 반영돼 있지 않다 — 은행 확인 필요",
    "설명부족":    "공시 최고금리의 일부가 조건으로 설명되지 않는다 — 광고 금리 근거 없음",
    "추출불확실":  "우리가 공시보다 많이 뽑았다 — 조건별 배분을 신뢰할 수 없다",
    "계산불가":    "조건 항목을 하나도 뽑지 못했다",
}
MAIN_TIERS = ("확정", "범위")            # 메인 화면에 올리는 층

# ── 못 채운 사유 (`decisions/0016`)
#
# 조건을 판정하지 못하는 이유가 넷이고, **셋은 되물어서 없앨 수 있다.**
# 없앨 수 없는 둘은 우리가 모르는 게 아니라 **공시가 안 알려주는 것**이다.
# 그럴 때는 조용히 빼지 않고 "이 사유로 실제 금리가 다를 수 있다"고 말한다.
#
#   되물으면 없어진다      안 물어봄 · 수치를 안 받음 · 사용자가 모른다고 답함
#   되물어도 안 없어진다   추첨·랜덤 지급 · 단계별 금리가 공시에 안 나옴
CAVEAT = {
    "미응답":    "답하지 않은 조건이 있습니다. 답하면 금리가 확정됩니다",
    "수치필요":  "금액·횟수를 답하면 금리가 확정됩니다",
    "모름":      "사용자가 모른다고 답한 조건이 있어 금리를 확정할 수 없습니다",
    "추첨":      "추첨·랜덤으로 주는 우대금리가 포함돼 있어 실제 금리는 더 낮을 수 있습니다",
    "단계불명":  "충족 정도에 따라 금리가 달라지는 조건이 있는데 공시에 단계가 다 나와 있지 "
                 "않습니다. 실제 금리는 표시된 최대보다 낮을 수 있습니다",
    "이행필요":  "가입 후 계속 실천해야 받는 우대금리가 포함돼 있습니다. 중단하면 그만큼 낮아집니다",
    # 되물어도 없앨 수 없는 셋째 사유 (`decisions/0019`). 앞의 둘과 성격이 다르다 —
    # 우리가 못 읽은 것도, 사용자가 모르는 것도 아니고 **공시가 안 적은 것**이다.
    # 그래서 문장이 갈 곳을 알려주며 끝나야 한다. 우리가 대신 추측하지 않는 대신,
    # 사용자를 막다른 길에 세워두지도 않는다.
    "조건불명":  "우대금리 금액은 공시에 있는데 무슨 조건을 채워야 받는지는 나와 있지 "
                 "않습니다. 표시된 최대 금리를 실제로 받을 수 있는지 은행에 전화해 "
                 "확인해 보세요",
    # 넷째 — 되물어도 못 없앤다 (`decisions/0022`). 공시가 "중복 적용 불가" 를 분명히
    # 안 밝혀서 우리가 두 해석을 다 열어 둔 것이다. 사용자 상태와 무관하다.
    "중복우대불명": "여러 우대조건이 함께 적용되는지 하나만 적용되는지 공시가 분명하지 "
                   "않습니다. 함께 적용되지 않으면 실제 금리는 표시된 최대보다 낮습니다",
}

# 가입 후에 계속 해야 하는 유형 — 답을 받았어도 "이행 조건" 을 붙여 보여준다.
# 사용자가 "대중교통 이용하겠다" 고 답한 것은 사실이 아니라 **약속**이다.
ONGOING = {"실천_미션_인증", "자동이체", "카드실적", "급여_연금이체", "목표달성_납입실적"}

# 사용자가 "모르겠다" 고 답한 것을 표시하는 값. 안 물어본 것(None)과 구분해야
# 되물을 목록에서 뺄 수 있다 — 이미 물었고 답이 "모름" 이면 다시 물어도 소용없다.
UNSURE = "모름"

# 사용자가 "아니오" 라고 답한 것. `condition_met()` 은 처음부터 `False` 를 처리했는데
# **입력 경로가 없었다** — `--state` 가 True·숫자·`모름` 만 만들었다. 그래서 지금까지
# 모든 측정이 "예" 로만 답한 사용자였다 (`decisions/0024`).
#
# **"모르겠다" 와 "아니오" 는 lo 에서 완전히 같고 hi 에서만 다르다.**
#     lo = group_totals(met)          충족 확인된 것만 더한다 — 모름도 아니오도 안 들어간다
#     hi = group_totals(met+unknown)  모름은 들어가고 아니오는 안 들어간다
# 그래서 과대 진술 방어선은 **lo** 다. 모름을 아니오로 바꿔 hi 까지 내리면 방어가 아니라
# **단정**이 된다 — 아무것도 모른다고 답한 사용자에게 확정 65/67 이 나온다 (`0024` 실측).
DENY = "아니오"

# 사용자에게 보여줄 문장 — 층마다 말이 달라야 한다
TIER_MESSAGE = {
    "공시미반영": "조건문에 우대금리가 적혀 있으나 공시 최고금리에는 반영되지 않았습니다. "
                  "실제로 받을 수 있는지 은행에 확인이 필요합니다",
    "설명부족":   "광고 최고금리의 일부는 공시된 조건으로 설명되지 않습니다",
    "추출불확실": "이 상품의 조건 해석에 확신이 없습니다",
    "계산불가":   "조건을 읽어내지 못해 금리를 계산할 수 없습니다",
}


def load_tax() -> dict:
    """세율표를 읽는다. 코드에 박지 않는 이유는 세법이 매년 바뀌기 때문이다."""
    return json.loads(TAX_PATH.read_text(encoding="utf-8"))


def condition_met(item: dict, state: dict) -> bool | None:
    """이 조건을 사용자가 충족하는가. 모르면 None 을 낸다 — 추측하지 않는다."""
    kind = item.get("condition_type")
    if kind in ALWAYS_MET:
        return True
    if kind in UNDECIDABLE:
        return None
    value = state.get(kind)
    if value is None or value == UNSURE:
        return None
    if value and has_threshold(item):
        # B안 — 임계 수치를 물어서 받았으면 비교한다. 없으면 판정 불가(A안과 같다)
        q = threshold_question(item)
        if q is None:
            return None                       # 계단식 우대 등 — 임계가 하나가 아니다
        key, _unit, need, direction = q
        got = state.get(key)
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            return None                       # 아직 안 물어봤다
        ok = got >= need if direction == "최소" else got <= need
        return (not ok) if item.get("polarity") == "must_not_have" else ok
    return (not value) if item.get("polarity") == "must_not_have" else bool(value)


# ── 배타 그룹을 범위로 처리한다 (`decisions/0022` · `prereg-06` §2.3(1))
#
# **왜** — `exclusive_group` 라벨을 절반쯤 못 믿는다. 그룹이 붙은 행에서 공시 폭에
# 맞는 쪽을 세어 보니 **최댓값 35 : 합산 32 : 둘 다 틀림 26**(은행권)이었다.
# `iM함께예금`은 `g1` 에 `[0.1 x 5]` 가 들어 있는데 공시 폭이 0.45라 **다섯 개가 다
# 더해져야** 맞는다 — 중복 적용 불가가 아니라 별개 조건 다섯을 한 그룹으로 묶은 것이다.
#
# 공식이 틀린 게 아니라 **라벨을 못 믿는다.** 그러면 배타인지 아닌지도 **모르는 것**이고,
# 이 프로젝트는 모르는 것을 범위로 낸다(`0015`·`0016`·`0017`).
#
#     최댓값(보수) = 중복 적용 불가가 맞다면
#     합산(낙관)   = 중복 적용 가능하다면. 공시 최고금리 상한에 걸린다
#
# 그룹이 없으면 두 값이 같아지므로, 이 처리는 **그룹이 붙은 행에서만 범위를 넓힌다.**


def group_totals(chosen: list[dict]) -> tuple[float, float]:
    """(보수 합계, 낙관 합계). 배타 그룹을 믿을 때와 안 믿을 때다."""
    plain, groups = 0.0, {}
    for it in chosen:
        rate = sane_rate(it)
        gid = it.get("exclusive_group")
        if gid:
            groups.setdefault(gid, []).append(rate)
        else:
            plain += rate
    lo = plain + sum(max(v) for v in groups.values())
    hi = plain + sum(sum(v) for v in groups.values())
    return round(lo, 4), round(hi, 4)


def has_group(items: list[dict]) -> bool:
    """배타 그룹이 붙은 항목이 있는가 — 있으면 `중복우대불명` 사유가 붙는다."""
    return any(it.get("exclusive_group") for it in items)


def bonus_range(items: list[dict], cap: float | None, state: dict) -> dict:
    """충족분 합계의 최소~최대.

    최소는 **확실히 충족되는 것만, 배타 그룹은 최댓값만**(가장 보수적),
    최대는 **모르는 것까지 다 충족 + 배타 그룹도 다 더함**(가장 낙관적)이다.
    낙관 쪽은 공시 최고금리 상한에 걸리므로 광고 금리를 넘을 수 없다.
    """
    live = [it for it in items if it.get("applies_to_term")]
    met, unmet, unknown = [], [], []
    for it in live:
        verdict = condition_met(it, state)
        (met if verdict is True else unmet if verdict is False else unknown).append(it)

    lo, _ = group_totals(met)                 # 보수 — 배타를 믿는다
    _, hi = group_totals(met + unknown)       # 낙관 — 배타를 안 믿는다
    if cap is not None and live:
        lo, hi = min(lo, cap), min(hi, cap)
    return {"lo": lo, "hi": hi, "met": met, "unmet": unmet, "unknown": unknown}


def after_tax(rate: float, tax: dict, exempt: bool = False) -> tuple[float, float]:
    """세후 금리와 적용 세율. 1층(원천징수)·2층(비과세) 까지만 다룬다."""
    r = 0.0 if exempt else tax["일반과세"]["합계"]
    return round(rate * (1 - r), 4), r


def evaluate(row: dict, extracted: dict, state: dict, tax: dict) -> dict:
    """상품 한 행을 사용자 상태로 채점한다."""
    raw_items = extracted.get("items", []) if extracted else []
    # 조건이 아닌 문구를 먼저 갈라낸다 (`no_condition()` · `decisions/0019`).
    #   "제외"      금리도 조건도 없다 — 항목 자체가 아니다. 버린다
    #   "조건불명"   금액은 공시가 알려줬다 — 금리는 남기되 **판정 불가로 못 박는다**
    # 판정 불가로 두면 질문도 안 만들어지고(`question_for` 의 UNDECIDABLE 경로)
    # 항상 충족도 되지 않는다. 사용자에게는 범위와 사유로 나간다.
    items, n_unclear = [], 0
    for it in raw_items:
        verdict = no_condition(it)
        if verdict == "제외":
            continue
        if verdict == "조건불명":
            it = {**it, "condition_type": UNCLEAR_TYPE}
            n_unclear += 1
        items.append(it)
    cap = extracted.get("cap") if extracted else None
    rng = bonus_range(items, cap, state)
    thr_unknown = [it for it in rng["unknown"]
                   if state.get(it.get("condition_type")) and has_threshold(it)]
    n_threshold = len(thr_unknown)
    # 되물으면 판정할 수 있는 것과, 물어도 판정할 수 없는 것(계단식)을 가른다
    ask, ladder = [], 0
    for it in thr_unknown:
        q = threshold_question(it)
        if q is None:
            ladder += 1
        else:
            ask.append(q)
    # 임계뿐 아니라 **못 판정한 모든 항목**을 되묻는다 (`decisions/0016`)
    questions = [q for q in (question_for(it, state) for it in rng["unknown"]) if q]
    caveat_codes = caveats_for(rng["unknown"], rng["met"], state)
    # 답해도 금리가 안 바뀌면(범위 폭 0) 그 사유는 사용자에게 소음이다 — 뺀다.
    # 우대금리가 0인 조건이거나 상한에 이미 걸린 경우다. 남기는 것은 실제로 금리를
    # 낮출 수 있는 사유뿐이다 (이행필요·추첨·단계불명).
    if rng["hi"] == rng["lo"]:
        caveat_codes = [c for c in caveat_codes
                        if c not in ("미응답", "수치필요", "모름")]
    base = row["base"]
    gross_lo, gross_hi = round(base + rng["lo"], 4), round(base + rng["hi"], 4)
    exempt = bool(state.get("_비과세종합저축_대상"))

    # 공시 최고금리를 조건으로 설명할 수 있는가 (닫힘률과 같은 판정)
    live_all = [i for i in items if i.get("applies_to_term")]
    # 배타 그룹을 믿을 때(보수)와 안 믿을 때(낙관)를 둘 다 낸다 (`decisions/0022`).
    # 라벨을 절반쯤 못 믿으므로 **어느 한쪽을 고르지 않고 밴드로 판정한다** —
    # 공시 폭이 [보수, 낙관] 안에 들어오면 설명된 것으로 본다.
    dec_lo, dec_hi = group_totals(live_all)
    if cap is not None and live_all:
        dec_lo, dec_hi = min(dec_lo, cap), min(dec_hi, cap)
    band = dec_hi - dec_lo > 1e-9          # 배타 그룹이 실제로 폭을 만들었나
    # 보고용 미설명 폭 — 밴드 밖으로 벗어난 만큼만 센다. 안에 들어오면 0 이다
    if row["gap"] > dec_hi + TOLERANCE:
        unexplained = round(row["gap"] - dec_hi, 3)      # 모자람
    elif row["gap"] < dec_lo - TOLERANCE:
        unexplained = round(row["gap"] - dec_lo, 3)      # 넘침
    else:
        unexplained = 0.0

    # 공시 최고금리 상한. 사용자가 공시보다 많이 받을 수는 없다
    raw_lo, raw_hi = gross_lo, gross_hi
    gross_lo = min(gross_lo, row["max"])
    gross_hi = min(gross_hi, row["max"])
    net_lo, rate_used = after_tax(gross_lo, tax, exempt)
    net_hi, _ = after_tax(gross_hi, tax, exempt)

    # 폭 0 을 먼저 가른다 — 이 행에서는 어떤 추출도 "넘침"이 된다 (0 보다 크면 초과다).
    # 여기 있는 상품을 `추출불확실` 로 묶으면 우리 잘못이 아닌 것을 우리 탓으로 표시한다.
    gap_zero = abs(row["gap"]) <= TOLERANCE
    has_bonus = any(sane_rate(i) > 0 for i in items if i.get("applies_to_term"))
    if gap_zero:
        tier = "공시미반영" if has_bonus else "확정"
    elif not items:
        tier = "계산불가"
    elif unexplained < -TOLERANCE:
        tier = "추출불확실"
    elif unexplained > TOLERANCE:
        tier = "설명부족"
    else:
        tier = "범위" if rng["unknown"] else "확정"
    # 배타 그룹이 폭을 만들었으면 사용자에게 이유를 말한다 (`decisions/0022`).
    # 층 라벨만 후해지고 사용자가 모르면 그게 과대 진술이다 — `조건불명`(`0019`)과 같다.
    if band and tier in MAIN_TIERS:
        caveat_codes = caveat_codes + ["중복우대불명"]

    return {
        "tier": tier,
        "message": TIER_MESSAGE.get(tier, ""),
        "raw_hi": raw_hi, "clamped": raw_hi > row["max"] + 0.001,
        "declared_lo": dec_lo, "declared_hi": dec_hi, "band": band,
        "name": row["name"], "kind": row["kind"], "code": row["code"], "term": row["term"],
        "base": base, "disclosed_max": row["max"],
        "gross_lo": gross_lo, "gross_hi": gross_hi,
        "net_lo": net_lo, "net_hi": net_hi, "tax_rate": rate_used,
        "n_threshold": n_threshold, "n_ladder": ladder,
        "questions": questions,
        "caveats": caveat_codes,
        "caveat_text": [CAVEAT[c] for c in caveat_codes],
        "ask": [{"key": k, "unit": u, "need": v, "direction": d} for k, u, v, d in ask],
        "n_met": len(rng["met"]), "n_unmet": len(rng["unmet"]), "n_unknown": len(rng["unknown"]),
        "met": [i["condition_type"] for i in rng["met"]],
        "unmet": [i["condition_type"] for i in rng["unmet"]],
        "unknown": [i["condition_type"] for i in rng["unknown"]],
        "cap": cap,
        "explainable": abs(unexplained) <= TOLERANCE,
        "unexplained_pp": unexplained,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, term, top, state_arg, order = "bank", 12, 10, "", "hi"
    for flag in ("--group", "--term", "--top", "--state", "--sort"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            v = argv[i + 1]
            group = v if flag == "--group" else group
            term = int(v) if flag == "--term" else term
            top = int(v) if flag == "--top" else top
            state_arg = v if flag == "--state" else state_arg
            order = v if flag == "--sort" else order
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/calculate.py YYYYMMDD "
                         "[--group bank|savingsbank] [--term 12] [--state 유형,유형] "
                         "[--sort hi|lo] [--top 10]")
    if order not in ("hi", "lo"):
        raise SystemExit("--sort 는 hi (다 채웠을 때 순) 또는 lo (확정된 값 순) 다")
    stamp = argv[0]
    suffix = "" if group == "bank" else f"_{group}"

    # 사용자 상태: --state 에 적은 유형만 true, 나머지는 모름(None)
    #   유형              → 그 조건을 한다 (O)
    #   유형=아니오         → 안 한다 (X). hi 에서도 빠진다 (`decisions/0024`)
    #   유형=모름          → 물었지만 모른다. lo 에서만 빠지고 hi 에는 남는다
    #   유형_횟수=6        → 월 6회 한다        (B안 · 임계 비교에 쓴다)
    #   유형_금액=50만원    → 평잔 50만원        (만원·억원 단위를 그대로 쓸 수 있다)
    picked = [s.strip() for s in state_arg.split(",") if s.strip()]
    unknown_names = [q.partition("=")[0].strip() for q in picked]
    unknown_names = [q for q in unknown_names if q not in CONDITION_TYPES
                     and not (q.rpartition("_")[2] in ("금액", "횟수")
                              and q.rpartition("_")[0] in CONDITION_TYPES)]
    if unknown_names:
        raise SystemExit(f"모르는 조건 유형: {unknown_names}\n가능한 값: {CONDITION_TYPES}")
    state = {}
    for tok in picked:
        name, _, raw = tok.partition("=")
        name, raw = name.strip(), raw.strip()
        if not raw:
            state[name] = True
            continue
        if raw == UNSURE:                 # "유형=모름" — 물었지만 답을 모른다
            state[name] = UNSURE
            continue
        if raw == DENY:                   # "유형=아니오" — 안 한다. hi 에서도 빠진다
            state[name] = False
            continue
        m = re.fullmatch(r"(\d[\d,]*)\s*(억원|만원|천원|원)?", raw)
        if not m:
            raise SystemExit(f"수치를 읽을 수 없다: {tok}")
        state[name] = float(int(m.group(1).replace(",", ""))
                            * MONEY_UNIT.get(m.group(2) or "원", 1))
        state.setdefault(name.rpartition("_")[0], True)   # 수치를 답했으면 그 조건은 한다
    tax = load_tax()

    rows, pairs = load_pairs(stamp, group)
    llm_path = OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    if not llm_path.exists():
        raise SystemExit(f"추출 결과가 없다: {llm_path.relative_to(REPO_ROOT)}\n"
                         f"먼저 extract_llm.py 를 돌린다")
    llm = json.loads(llm_path.read_text(encoding="utf-8"))
    llm, unified = unify_types(llm)          # 같은 문구는 같은 유형으로 (`decisions/0020`)
    by_pair = {p["pair_id"]: p for p in llm["pairs"]}

    scored = []
    for row in rows:
        if row["term"] != term:
            continue
        got = by_pair.get(row["pair_id"])
        parsed = got["parsed"] if (got and got["schema_ok"]) else None
        scored.append(evaluate(row, parsed, state, tax))

    print(f"사용자 상태  {picked or '(아무 것도 답하지 않음)'}")
    print(f"가입기간     {term}개월 · 스냅샷 {stamp} ({group})")
    print(f"세율         {tax['일반과세']['합계'] * 100:.1f}% · {tax['적용_시점']} "
          f"· 확인 상태 {tax['확인_상태']}")
    if unified["바뀐 항목"]:
        print(f"유형 통일     문구 {unified['문구']}종 · 항목 {unified['바뀐 항목']}개 "
              f"(동점이라 남긴 문구 {unified['동점']}종) · decisions/0020")
    print(f"대상 상품    {len(scored)}\n")
    if not scored:
        raise SystemExit(f"{term}개월 상품이 없다. --term 을 바꿔본다")

    # ── 정렬 (`decisions/0017`)
    #
    # 기본은 **최대 순**이다 — "조건을 다 채웠을 때 얼마인가" 로 줄을 세우고, 답을
    # 받을수록 깎이며 후보가 바뀐다. 행원이 물어가며 좁히는 것과 같은 흐름이다.
    #
    # **최소 순으로 시작하면 사실상 기본금리 순이 된다.** 조건이 좋은 상품이 전부 묻힌다
    # (카카오뱅크 우리아이적금은 최대 5.92%인데 최소 순 첫 화면에 안 보인다). 두 정렬의
    # 첫 화면은 상위 3위가 0/3 겹치고, **전부 답하면 3/3 일치한다** — 끝점은 같고 다른
    # 것은 무엇을 먼저 보여주는지다.
    #
    # 최대 순의 위험은 **첫 화면이 은행 광고와 같은 숫자**라는 것이다 (최대 = 공시
    # 최고금리인 상품이 은행권 83.5% · 저축은행 96.3%). 그래서 두 가지를 강제한다.
    #   1. 최대값을 단독으로 쓰지 않는다 — 항상 범위로 쓴다 (`design.md` 화면 계약)
    #   2. 최대값 옆에 **남은 조건 수**를 붙인다 — 그 금리가 무료가 아님을 같이 보여준다
    if order == "hi":
        scored.sort(key=lambda x: (-x["net_hi"], -x["net_lo"], x["name"]))
    else:
        scored.sort(key=lambda x: (-x["net_lo"], -x["net_hi"], x["name"]))
    main = [s for s in scored if s["tier"] in MAIN_TIERS]
    rest = [s for s in scored if s["tier"] not in MAIN_TIERS]

    def show(items: list[dict], label: str) -> None:
        if not items:
            return
        head = "다 채웠을 때 순" if order == "hi" else "확정된 값 순"
        print(f"\n■ {label} ({len(items)}) · {head}")
        print(f"{'순':>3} {'상품':<26}{'세후 확정~최대':>17}{'세전':>13}  {'층':<11}남은 조건")
        print("-" * 104)
        for i, s in enumerate(items[:top], 1):
            span = (f"{s['net_lo']:.2f}" if s["net_lo"] == s["net_hi"]
                    else f"{s['net_lo']:.2f}~{s['net_hi']:.2f}")
            gspan = (f"{s['gross_lo']:.2f}" if s["gross_lo"] == s["gross_hi"]
                     else f"{s['gross_lo']:.2f}~{s['gross_hi']:.2f}")
            note = ""
            if s["tier"] == "설명부족":
                note = f" 근거없음 {s['unexplained_pp']:+.2f}%p"
            elif s["tier"] == "추출불확실":
                note = f" 과다 {s['unexplained_pp']:+.2f}%p"
            elif s["tier"] == "공시미반영":
                note = f" 조건문 우대 {-s['unexplained_pp']:.2f}%p (공시 미반영)"
            if s["clamped"]:
                note += f" [상한 {s['raw_hi']:.2f}->{s['gross_hi']:.2f}]"
            if s.get("caveats"):
                note += "  주의:" + "·".join(s["caveats"])
            # 남은 조건 수를 금리 옆에 붙인다 — 최대값이 무료가 아님을 같이 보여준다
            if s["net_hi"] > s["net_lo"]:
                left = f"남은 {s['n_unknown']}개"
            elif s["n_unknown"]:
                left = f"남은 {s['n_unknown']}개 (금리 영향 없음)"
            else:
                left = f"확정 (충족{s['n_met']}/미충족{s['n_unmet']})"
            print(f"{i:>3} {s['name'][:25]:<26}{span:>16}%{gspan:>12}%  {s['tier']:<11}"
                  f"{left:<22}{note}")

    show(main, "메인 - 계산할 수 있는 상품")
    show(rest, "아래 섹션 - 주의가 붙는 상품")

    # ── 상태바 — 숫자 둘을 나란히 놓는다 (`decisions/0024`)
    #
    # 남은 질문 수 **하나만** 보여주면 "모르겠다" 가 "아니오" 와 똑같이 진전으로 보인다.
    # 둘 다 질문을 지우지만 "모르겠다" 는 금리를 하나도 좁히지 못한다. 실측으로 끝까지
    # 갔을 때 확정이 **예 64 · 아니오 65 · 모르겠다 4** 다 — 확정 수가 그 차이를 정확히
    # 가른다. 나란히 놓으면 사용자가 "모르겠다" 의 대가를 **스스로 보고**, 우리가 답을
    # 강요하지는 않는다.
    plan = question_plan([r for r in rows if r["term"] == term], by_pair)
    left_n = questions_left(plan, state)
    total_n = questions_left(plan, {})
    n_fixed = sum(1 for s in main if s["tier"] == "확정")
    done = total_n - left_n
    bar_w = 40
    filled = 0 if not total_n else round(done / total_n * bar_w)
    print("\n" + "-" * 102)
    print(f"진행       [{'#' * filled}{'.' * (bar_w - filled)}]  "
          f"답한 질문 {done}/{total_n} · 남은 질문 {left_n}개")
    print(f"성과       금리가 정해진 상품 {n_fixed}/{len(main)}개"
          f"   <- '모르겠다' 는 이 숫자를 움직이지 못한다")

    tiers = Counter(s["tier"] for s in scored)
    n_clamped = sum(1 for s in scored if s["clamped"])
    print("\n" + "-" * 102)
    print("층 분포")
    for name, desc in TIERS.items():
        if tiers[name]:
            mark = "메인" if name in MAIN_TIERS else "  "
            print(f"  {mark} {name:<11}{tiers[name]:>4}  {desc}")
    # 되물을 질문 — 답 하나가 상품 몇 개를 확정으로 옮기는지 큰 것부터
    # ── 되물을 질문 (`decisions/0016`)
    #
    # **모르면 전부 되묻는다.** 질문은 유형 하나에 하나다 — 상품마다 임계가 달라도
    # "월 몇 회 하십니까" 는 한 번 물으면 되고 비교는 상품별로 각자 한다.
    # 근거 문구를 그대로 인용해서, 공시가 애매한 조건도 사람이 판단할 수 있게 한다.
    #
    # 순서는 `rank_questions()` 가 정한다 — **고정된 규칙이다**(`decisions/0018`).
    # 여기서 임의로 다시 정렬하면 예산 제약이 무력해진다.
    ordered = rank_questions(scored)

    def fmt(need: float, unit: str) -> str:
        if unit != "금액":
            return f"{need:,.0f}회"
        return f"{need / 10000:,.0f}만원" if need >= 10000 else f"{need:,.0f}원"

    if ordered:
        print()
        print(f"되물을 질문 — 답 하나가 상품 몇 개를 확정으로 옮기나 "
              f"(decisions/0016 · 평가 예산 {ASK_BUDGET}개 · decisions/0018)")
        for key, slot in ordered[:ASK_BUDGET]:
            if slot["needs"]:
                needs = " · ".join(fmt(v, slot["unit"]) for v in sorted(slot["needs"])[:4])
                more = "" if len(slot["needs"]) <= 4 else f" +{len(slot['needs']) - 4}"
                tail = f"임계 {needs}{more}"
            else:
                tail = "예 / 아니오 / 모르겠다"
            print(f"    {key:<30}상품 {len(slot['codes']):>3}개   {tail}")
            for ev in sorted(slot["evidence"])[:2]:
                print(f"        공시 문구  \"{ev}\"")
        if len(ordered) > ASK_BUDGET:
            print(f"    --- 여기까지가 평가 예산 {ASK_BUDGET}개 ---")
            print(f"    ... 그리고 {len(ordered) - ASK_BUDGET}개 더 "
                  f"(물어도 되지만 평가 지표에는 안 들어간다)")
        print(f"    → --state '{ordered[0][0]}=<값>' · 안 하면 '{ordered[0][0]}=아니오'"
              f" · 모르면 '{ordered[0][0]}=모름'")

    # 되물어도 못 채우는 사유 — 사용자에게 보여줄 문장 그대로
    codes = Counter(c for s in scored for c in s.get("caveats", []))
    hard = [c for c in ("조건불명", "중복우대불명", "추첨", "단계불명", "모름") if codes[c]]
    if hard:
        print()
        print("되물어도 못 채우는 사유 — 이 문장을 사용자에게 보여준다")
        for c in hard:
            print(f"    {c:<10}상품 {codes[c]:>3}개")
            print(f"        \"{CAVEAT[c]}\"")
    if codes["이행필요"]:
        print()
        print(f"이행 조건이 붙는 상품 {codes['이행필요']}개")
        print(f'        "{CAVEAT["이행필요"]}"')
    n_ladder = sum(s.get("n_ladder", 0) for s in scored)
    if n_ladder:
        print(f"\n물어도 판정할 수 없는 조건 {n_ladder}건 — 계단식 우대다")
        print('    "5회이상 0.2%p, 10회이상 0.3%p, 15회이상 0.5%p" 처럼 단계마다 금리가 다른데')
        print("    추출 스키마에 단계를 담을 자리가 없어 가장 높은 금리만 남아 있다")
    print(f"\n공시 최고금리 상한에 걸린 상품 {n_clamped}/{len(scored)}"
          f"   <- 상한이 없으면 공시에 없는 금리를 보여준다")
    print("상한은 증상만 막는다. 넘치는 상품은 우리 추출 문제이고 raw_hi 로 남겨 측정에 쓴다")

    out = OUT_DIR / f"recommend{suffix}_{stamp}_{term}m.json"
    out.write_text(json.dumps({"snapshot": stamp, "group": group, "term": term,
                               "state": state, "tax": tax["적용_시점"],
                               "products": scored}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
