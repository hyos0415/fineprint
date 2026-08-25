# -*- coding: utf-8 -*-
"""우대조건 파싱·층 분류 규칙 (`docs/spec/prereg-02-pilot.md` §2 규칙 A~D).

두 스크립트(build_pilot_sample.py · build_gold.py)가 같은 규칙을 쓰도록 한 곳에 둔다.
규칙을 고치면 사전등록 문서를 함께 고친다 — 문서와 코드가 어긋나면 사전등록이 무의미해진다.

규칙 요약
  A 금리 항목이 0개일 때: 폭(최고−기본)이 0이면 조건없음, 폭이 있으면 안닫힘.
    리터럴 목록은 **데이터에서 확인된 5개만** 쓴다(§2 주석).
  B "최대/최고 우대금리" 줄은 항목이 아니라 상한으로만 쓴다.
  C "각 연0.10%p" 형태는 앞에 모인 금리 없는 항목 수 × 그 금리로 센다.
  D 한 줄에 금리가 여럿이면 최댓값 하나만 센다(구간별 금리).
"""
from __future__ import annotations

import re

# 데이터에서 실제로 확인된 것만 (예금 38 + 적금 59 전수, 2026-08-24 스냅샷)
#   없음 5 · 해당없음 3 · 해당사항없음 3 · 우대조건없음 3 · 해당무 1
NO_CONDITION_LITERALS = {"없음", "해당없음", "해당사항없음", "우대조건없음", "해당무"}
LEADING_MARKS = "▶※*·-●○□■◆:>〉 \t"

# 규칙 B′ — 상한 표기 변형. 실제 공시에서 확인된 네 가지 어순을 모두 인식한다.
#   "최고우대금리: 연0.45%p" / "최고 연 2.20%p" / "우대이율 최대 2.5%"
#   "우대이율(최대 0.90%p)" / "최고 0.4%p 추가 우대금리 제공"
CAP_HEADER = re.compile(
    r"(?:최대|최고)\s*(?:우대)?(?:금리|이율)"                       # 최고우대금리 …
    r"|(?:우대|가산|추가)\s*(?:이?율|금리)\s*[:：(（]?\s*(?:최대|최고)"   # 우대이율 최대 / 가산금리 최고              # 우대이율 최대 / 우대금리 최대한도 / 우대이율(최대
    r"|^[\s*※▶·-]*(?:최대|최고)\s*(?:연\s*)?\d+(?:\.\d+)?\s*%"   # 줄머리가 최고/최대 + 숫자
    r"|(?:최대|최고)\s*(?:연\s*)?\d+(?:\.\d+)?\s*%\s*p?\s*(?:추가|제공|우대|적용)"  # 최고 0.4%p 추가 / 최고 2.1%p 우대금리 적용
)
# 규칙 E — "중복 적용 불가"가 명시된 상품은 항목 합계가 성립하지 않는다.
# 표기 위치가 상품마다 달라(앞·뒤·괄호) 자동 분해가 위험하므로, 감지만 하고
# 실제 합계는 사람이 확정한 override(gold_overrides.json)를 쓴다.
EXCLUSIVE = re.compile(r"중복\s*적용\s*불가|중복적용\s*불가|중복\s*불가|중복\s*제외")
# 규칙 G — 기간별 대안 항목. "3~5개월" "6~11개월" "12개월제" 같은 범위가 붙은 항목은
# 우리 기간(12개월)을 포함하는 것만 센다. 적용 범위 밖 항목을 더하면 합계가 부푼다.
# 가입기간 차등을 가리키는 표기만 인식한다. 셋 중 하나여야 한다.
#   범위형   3~5개월
#   "제"형   12개월제 · 1년제
#   나열형   "1년: 0.6%p, 2년: 0.7%p" 처럼 한 줄에 기간 표기가 2개 이상
# 단독 "5년이상"은 제외한다 — "거래기간 5년이상"처럼 가입기간이 아닌 경우가 있다(오탐).
TERM_MONTH_RANGE = re.compile(r"(\d{1,2})\s*[~\-–]\s*(\d{1,2})\s*개월")
TERM_EXPLICIT = re.compile(r"(\d{1,2})\s*개월\s*제|(\d{1,2})\s*년\s*제")
TERM_LISTED = re.compile(r"(\d{1,2})\s*(개월|년)\s*(?:미만|이상|이내)?\s*[::,]?\s*(?=연?\s*\d)")
TARGET_TERM = 12


def doc_has_term_tiers(text: str) -> bool:
    """조건문 전체에 기간별 차등이 있는가.

    차등이 한 줄 안에 나열되기도 하고("1년: 0.6, 2년: 0.7"), 줄 사이에 걸리기도 한다
    ("1년미만 0.10 / 1년이상 0.20"). 그래서 나열형 표기는 **문서 단위로** 센다.
    """
    return len(TERM_LISTED.findall(text)) >= 2


def _term_markers(line: str, term: int, listed_ok: bool = False) -> list[tuple[int, bool]]:
    """(문자 위치, 우리 기간에 해당하는가) 목록. 비어 있으면 기간 표기가 없는 줄이다."""
    found: list[tuple[int, bool]] = []
    for m in TERM_MONTH_RANGE.finditer(line):
        found.append((m.start(), int(m.group(1)) <= term <= int(m.group(2))))
    for m in TERM_EXPLICIT.finditer(line):
        months = int(m.group(1)) if m.group(1) else int(m.group(2)) * 12
        found.append((m.start(), months == term))
    listed = [(m.start(), (int(m.group(1)) * (12 if m.group(2) == "년" else 1)), m.group(0))
              for m in TERM_LISTED.finditer(line)]
    if len(listed) >= 2 or (listed_ok and listed):   # 문서에 차등이 있으면 한 개도 인정
        for pos, months, raw in listed:
            hit = months == term
            if "미만" in raw:
                hit = term < months
            elif "이상" in raw:
                hit = term >= months
            found.append((pos, hit))
    return sorted(found)


def term_applies(line: str, term: int = TARGET_TERM, listed_ok: bool = False) -> bool:
    """항목에 가입기간 차등이 붙어 있으면 우리 기간을 포함하는지 본다 (규칙 G)."""
    markers = _term_markers(line, term, listed_ok)
    return True if not markers else any(hit for _, hit in markers)


def value_for_term(line: str, values: list[tuple[int, float]], term: int,
                   listed_ok: bool = False) -> float:
    """한 줄에 기간별 값이 여러 개면 우리 기간의 값을 고른다 (규칙 G′).

    values 는 (문자 위치, 금리) 목록이다. 기간 표기가 없으면 최댓값을 쓴다(규칙 D).
    """
    markers = _term_markers(line, term, listed_ok)
    if len(markers) < 2:
        return max(v for _, v in values)
    best = None
    for pos, hit in markers:
        if not hit:
            continue
        after = [v for p, v in values if p >= pos]      # 그 기간 표기 뒤에 오는 값
        if after:
            best = after[0] if best is None else max(best, after[0])
    return best if best is not None else max(v for _, v in values)
EACH_RATE = re.compile(r"각\s*(?:연\s*)?(\d+\.?\d*)\s*%\s*p?")
RATE = re.compile(r"(\d+\.?\d*)\s*%\s*p?")
BULLET = re.compile(r"^\s*(?:[-*·]|[①-⑳]|\d{1,2}\s*[.)]|[가-하]\s*[.)])")
ITEM_RATE_MAX = 3.0          # 우대금리 한 항목으로 볼 수 있는 상한 %p
TOLERANCE = 0.06             # 산수 일치 허용 오차 %p


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def normalize_literal(text: str) -> str:
    """리터럴 비교용 정규화 — 공백 제거 + 앞머리 기호 제거 (예: '▶ 해당사항없음')."""
    return squash(text).lstrip(LEADING_MARKS)


def is_no_condition_literal(text: str) -> bool:
    normalized = normalize_literal(text)
    return normalized == "" or normalized in NO_CONDITION_LITERALS


def _rated_values(line: str) -> list[tuple[int, float]]:
    """줄 안의 (위치, 금리) 목록. 우대금리로 볼 수 있는 범위만."""
    return [(m.start(), float(m.group(1))) for m in RATE.finditer(line)
            if 0 < float(m.group(1)) <= ITEM_RATE_MAX]


def parse_bonus_items(text: str, term: int = TARGET_TERM) -> tuple[list[float], float | None]:
    """조건문에서 우대금리 항목 목록과 상한을 뽑는다 (규칙 B·C·D·G·G′)."""
    items: list[float] = []
    cap: float | None = None
    pending = 0                                   # 금리 없이 나열된 항목 수
    tiers = doc_has_term_tiers(text)               # 문서 전체에 기간 차등이 있는가
    for line in (ln.strip() for ln in re.split(r"[\n\r]+", text) if ln.strip()):
        if CAP_HEADER.search(line):               # B·B′ — 상한 헤더는 항목이 아니다
            found = RATE.search(line)
            if found:
                value = float(found.group(1))
                cap = value if cap is None else max(cap, value)   # 상·하위 상한이 함께 있으면 큰 쪽
            continue
        each = EACH_RATE.search(line)
        if each:                                  # C — "각 연0.10%p"
            items += [float(each.group(1))] * max(pending, 1)
            pending = 0
            continue
        values = _rated_values(line)
        if values:
            if term_applies(line, term, tiers):   # G — 적용 기간 밖 항목은 세지 않는다
                items.append(value_for_term(line, values, term, tiers))   # D·G′
            pending = 0
        elif BULLET.match(line):
            pending += 1
    return items, cap


def declared_bonus(text: str, term: int = TARGET_TERM) -> tuple[float, float | None]:
    items, cap = parse_bonus_items(text, term)
    total = sum(items)
    return (min(total, cap) if (items and cap is not None) else total), cap


def has_exclusive_group(text: str) -> bool:
    """'중복 적용 불가'가 명시됐는가 (규칙 E — 합계 대신 사람이 확정한 값을 쓴다)."""
    return bool(EXCLUSIVE.search(text))


def classify(text: str, gap: float, term: int = TARGET_TERM) -> str:
    """층을 판정한다. 자동 판정은 초안이며, 파일럿 30문항은 사람이 확인한다(§2 완화 조치)."""
    if is_no_condition_literal(text):
        return "조건없음"
    items, cap = parse_bonus_items(text, term)
    if not items:                                 # A — 금리 표기가 없다
        return "조건없음" if abs(gap) < 0.01 else "안닫힘"
    total = sum(items)
    declared = min(total, cap) if cap is not None else total
    return "닫힘" if abs(declared - gap) <= TOLERANCE else "안닫힘"


def parse_items_with_text(text: str, term: int = TARGET_TERM) -> list[dict]:
    """우대 항목을 (라벨 문구, 금리)로 뽑는다.

    규칙 C 때문에 필요하다 — "각 연0.10%p"는 앞에 나열된 금리 없는 항목들에 나눠 붙는다.
    검토 시트(사람 판정)와 층 분류가 같은 항목 목록을 보게 하려고 한 함수로 둔다.
    """
    out: list[dict] = []
    pending: list[str] = []
    tiers = doc_has_term_tiers(text)
    for line in (ln.strip() for ln in re.split(r"[\n\r]+", text) if ln.strip()):
        if CAP_HEADER.search(line):
            continue
        each = EACH_RATE.search(line)
        if each:
            rate = float(each.group(1))
            if pending:
                out += [{"label": p, "rate": rate, "via": "각N%p"} for p in pending]
            else:
                out.append({"label": line, "rate": rate, "via": "각N%p"})
            pending = []
            continue
        values = _rated_values(line)
        if values:
            if term_applies(line, term, tiers):   # G
                out.append({"label": line, "rate": value_for_term(line, values, term, tiers),
                            "via": "직접"})
            pending = []
        elif BULLET.match(line):
            pending.append(line)
    return out
