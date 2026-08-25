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
    r"|우대\s*(?:이?율|금리)\s*[(（]?\s*(?:최대|최고)"              # 우대이율 최대 / 우대금리 최대한도 / 우대이율(최대
    r"|^[\s*※▶·-]*(?:최대|최고)\s*(?:연\s*)?\d+(?:\.\d+)?\s*%"   # 줄머리가 최고/최대 + 숫자
    r"|(?:최대|최고)\s*(?:연\s*)?\d+(?:\.\d+)?\s*%\s*p?\s*(?:추가|제공)"  # 최고 0.4%p 추가
)
# 규칙 E — "중복 적용 불가"가 명시된 상품은 항목 합계가 성립하지 않는다.
# 표기 위치가 상품마다 달라(앞·뒤·괄호) 자동 분해가 위험하므로, 감지만 하고
# 실제 합계는 사람이 확정한 override(gold_overrides.json)를 쓴다.
EXCLUSIVE = re.compile(r"중복\s*적용\s*불가|중복적용\s*불가|중복\s*불가|중복\s*제외")
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


def parse_bonus_items(text: str) -> tuple[list[float], float | None]:
    """조건문에서 우대금리 항목 목록과 상한을 뽑는다 (규칙 B·C·D)."""
    items: list[float] = []
    cap: float | None = None
    pending = 0                                   # 금리 없이 나열된 항목 수
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
        values = [v for v in (float(x) for x in RATE.findall(line)) if 0 < v <= ITEM_RATE_MAX]
        if values:
            items.append(max(values))             # D — 줄 안에서는 최댓값 하나
            pending = 0
        elif BULLET.match(line):
            pending += 1
    return items, cap


def declared_bonus(text: str) -> tuple[float, float | None]:
    items, cap = parse_bonus_items(text)
    total = sum(items)
    return (min(total, cap) if (items and cap is not None) else total), cap


def has_exclusive_group(text: str) -> bool:
    """'중복 적용 불가'가 명시됐는가 (규칙 E — 합계 대신 사람이 확정한 값을 쓴다)."""
    return bool(EXCLUSIVE.search(text))


def classify(text: str, gap: float) -> str:
    """층을 판정한다. 자동 판정은 초안이며, 파일럿 30문항은 사람이 확인한다(§2 완화 조치)."""
    if is_no_condition_literal(text):
        return "조건없음"
    items, cap = parse_bonus_items(text)
    if not items:                                 # A — 금리 표기가 없다
        return "조건없음" if abs(gap) < 0.01 else "안닫힘"
    total = sum(items)
    declared = min(total, cap) if cap is not None else total
    return "닫힘" if abs(declared - gap) <= TOLERANCE else "안닫힘"


def parse_items_with_text(text: str) -> list[dict]:
    """우대 항목을 (라벨 문구, 금리)로 뽑는다.

    규칙 C 때문에 필요하다 — "각 연0.10%p"는 앞에 나열된 금리 없는 항목들에 나눠 붙는다.
    검토 시트(사람 판정)와 층 분류가 같은 항목 목록을 보게 하려고 한 함수로 둔다.
    """
    out: list[dict] = []
    pending: list[str] = []
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
        values = [v for v in (float(x) for x in RATE.findall(line)) if 0 < v <= ITEM_RATE_MAX]
        if values:
            out.append({"label": line, "rate": max(values), "via": "직접"})
            pending = []
        elif BULLET.match(line):
            pending.append(line)
    return out
