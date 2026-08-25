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
# ─────────────────────────────────────────────────────────────────────────────
# v3 — 규칙 H·I (`../../docs/spec/prereg-05-rules-refinement.md` §3)
#
# v2(`parse_bonus_items`)는 **그대로 둔다.** 파일럿 30문항과 gold가 v2로 만들어졌고,
# 고치면 그 결과를 재현할 수 없다. v3는 별도 함수로 두고 채점기에서 골라 쓴다.
#
# 규칙 H — 중첩 상한. 한 줄에 "최고/최대 N%p"가 있을 때
#     항목 표시(①·1.·- 등)가 **있으면**  → 그 줄은 **항목**이고 기여값은 N이다 (항목별 상한)
#     항목 표시가 **없으면**            → 그 줄은 **문서 상한**이다
#   그리고 항목별 상한이 붙은 줄 뒤의 **더 깊은 층** 줄은 그 항목의 하위 상세이므로
#   세지 않는다. "중복 적용 불가"가 붙은 줄도 같다 — 뒤따르는 ①② 는 그 항목의 대안이다.
#
# 규칙 I — 대안 묶음. 같은 축(회차·주차·일·개·명)으로 값이 나열되면 합이 아니라 최댓값이다.
#   고객유형 머리글(신규고객/기존고객)로 갈린 묶음도 묶음별 합의 최댓값을 쓴다.
# ─────────────────────────────────────────────────────────────────────────────

# 항목 표시의 깊이. 숫자 < 동그라미 < 기호 < 표시 없음 순으로 깊어진다.
MARK_LEVELS = (
    (1, re.compile(r"^\s*(?:\d{1,2}\s*[.)]|[가-하]\s*[.)])")),
    (2, re.compile(r"^\s*[①-⑳]")),
    (3, re.compile(r"^\s*[-*·▶※●○□■◆]")),
)
NO_MARK_LEVEL = 99
SUBCAP = re.compile(r"(?:최고|최대)\s*(?:연\s*)?(\d+\.?\d*)\s*%")
# 문서 상한을 선언하는 줄. **줄머리에 앵커를 건다** — `CAP_HEADER`는 앵커가 없어서
# "1. 자동이체 입금횟수 우대금리 : 최고 0.5%p" 처럼 조건을 서술한 뒤 자기 상한을 붙인
# 줄까지 문서 상한으로 삼켰다. 그게 규칙 H가 고치려는 오류다.
#   상한 줄   "* 최고우대금리: 연0.45%p" · "* 우대이율 (최대 1.35%p)" · "최고 연 2.00%p"
#   항목 줄   "1. 자동이체 입금횟수 우대금리 : 최고 0.5%p"  ← 앞에 조건 서술이 있다
# 줄머리에서만 상한으로 본다 — 앞에 조건 서술이 오면 항목이다
CAP_LINE = re.compile(
    r"^(?:최대|최고)"
    r"|^(?:우대|가산|추가)\s*(?:이?율|금리)(?:\s*최대한도)?\s*[:：(（]?\s*(?:최대|최고)"
)
# 줄 어디에 있어도 상한 선언인 형태 (v2 CAP_HEADER에 있던 것을 잇는다)
#   "거래조건에 따라 최고 2.1%p 우대금리 적용"  ·  "합산 최대 연 0.2%p 우대"
CAP_ANYWHERE = re.compile(
    r"(?:최대|최고)\s*(?:연\s*)?\d+\.?\d*\s*%\s*p?\s*(?:추가|제공|우대|적용)"
    r"|합산\s*(?:최대|최고)"
)
LEADING_MARK_CHARS = re.compile(
    r"^[\s*※▶·\-●○□■◆①-⑳]*(?:(?:\d{1,2}|[가-하])\s*[.)]\s*)?")

# ── 규칙 J — 기간 라벨 (`../../docs/spec/prereg-05-rules-refinement.md` §3) ──
# 줄머리가 "12개월 …" · "1년제 …" 처럼 **기간 라벨로 시작**하면 그 줄은 그 기간의 것이다.
# 기존 `TERM_LISTED`는 기간 뒤에 숫자가 바로 와야 잡히므로
# "다. 12개월 특판 우대이율 : 0.55%" 같은 형태를 놓쳤다.
#   J1  라벨이 하나뿐이고 우리 기간과 맞지 않으면 그 줄을 세지 않는다
#   J2  라벨 + 최고/최대 가 함께 있으면 그 기간의 **문서 상한**이다 (항목이 아니다)
TERM_LABEL_HEAD = re.compile(r"^(\d{1,2})\s*(개월|년)\s*(?:제)?\s*(이상|초과|미만|이하)?")
TERM_LABEL_ANY = re.compile(r"(\d{1,2})\s*(개월|년)\s*(?:제)?")


def _leading_term_applies(bare: str, term: int) -> bool | None:
    """줄머리 기간 라벨이 우리 기간에 해당하는가. 라벨이 없거나 여럿이면 None."""
    head = TERM_LABEL_HEAD.match(bare)
    if not head or len(TERM_LABEL_ANY.findall(bare)) != 1:
        return None
    months = int(head.group(1)) * (12 if head.group(2) == "년" else 1)
    bound = head.group(3)
    if bound in ("이상", "초과"):
        return term >= months
    if bound in ("미만", "이하"):
        return term <= months
    return term == months
# 대안 축 — 줄머리 라벨이 "숫자 + 단위"인 것만 본다. 문장 중간의 "6회이상"에 걸리지 않게.
ALT_AXIS = re.compile(r"^\s*(?:[-*·▶※●○□■◆]|[①-⑳])?\s*(\d{1,3})\s*(회차|주차|일|개|명)(?![가-힣])")
CUSTOMER_GROUP = re.compile(r"^\s*(신규고객|기존고객|개인형|기업형)\s*[:：]?\s*$")


def _mark_level(line: str) -> int:
    for level, pattern in MARK_LEVELS:
        if pattern.match(line):
            return level
    return NO_MARK_LEVEL


def parse_bonus_items_v3(text: str, term: int = TARGET_TERM) -> tuple[list[float], float | None]:
    """우대금리 항목과 상한을 뽑는다 (규칙 B·C·D·G·G′ + H·I)."""
    tiers = doc_has_term_tiers(text)
    cap: float | None = None
    groups: list[list[float]] = [[]]          # 고객유형 묶음. 기본은 하나
    pending = 0                               # 금리 없이 나열된 항목 수 (규칙 C)
    skip_deeper_than: int | None = None       # 규칙 H — 하위 상세를 건너뛴다
    alt_run: list[tuple[int, float]] = []     # 규칙 I — (깊이, 금리)

    def flush_alt() -> None:
        """모인 대안 묶음을 최댓값 하나로 접는다 (규칙 I).

        묶음이 한 줄뿐이면 대안이 아니라 그냥 항목이므로 `ITEM_RATE_MAX`를 다시 건다.
        """
        nonlocal alt_run
        if len(alt_run) >= 2:
            groups[-1].append(max(v for _, v in alt_run))
        elif alt_run and alt_run[0][1] <= ITEM_RATE_MAX:
            groups[-1].append(alt_run[0][1])
        alt_run = []

    for line in (ln.strip() for ln in re.split(r"[\n\r]+", text) if ln.strip()):
        level = _mark_level(line)
        if skip_deeper_than is not None and level > skip_deeper_than:
            continue                          # 하위 상세 — 상위 항목에 이미 포함됐다
        skip_deeper_than = None

        if CUSTOMER_GROUP.match(line):        # 규칙 I — 고객유형 묶음이 열린다
            flush_alt()
            groups.append([])
            pending = 0
            continue

        bare = LEADING_MARK_CHARS.sub("", line)

        if _leading_term_applies(bare, term) is False:   # 규칙 J1 — 다른 기간의 줄이다
            flush_alt()
            pending = 0
            continue

        if TERM_LABEL_HEAD.match(bare) and SUBCAP.search(line):  # 규칙 J2 — 기간별 상한
            flush_alt()
            on_line = [(m.start(), float(m.group(1))) for m in RATE.finditer(line)
                       if float(m.group(1)) > 0]
            if on_line:
                value = value_for_term(line, on_line, term, tiers)
                cap = value if cap is None else max(cap, value)
            pending = 0
            continue

        if CAP_LINE.match(bare) or CAP_ANYWHERE.search(line):   # 규칙 B — 상한 선언 줄
            flush_alt()
            found = RATE.search(line)
            if found:
                value = float(found.group(1))
                cap = value if cap is None else max(cap, value)
            pending = 0
            continue

        subcap = SUBCAP.search(line)
        if subcap:
            flush_alt()
            # 기간 표기가 함께 있으면 기간에 맞는 값을 고른다 (규칙 G′). 항목별 상한 줄에도
            # 기간별 값이 붙는다 — "최대 1.15% (3개월 0.80% / 6,9개월 0.90% / 12개월 1.15%)"
            if _term_markers(line, term, tiers):
                on_line = [(m.start(), float(m.group(1))) for m in RATE.finditer(line)
                           if float(m.group(1)) > 0]
                value = value_for_term(line, on_line, term, tiers) if on_line \
                    else float(subcap.group(1))
            else:
                value = float(subcap.group(1))
            if level == NO_MARK_LEVEL:            # 표시 없는 줄의 최고/최대는 문서 상한
                cap = value if cap is None else max(cap, value)
            else:                                 # 규칙 H — 항목별 상한
                # ITEM_RATE_MAX를 걸지 않는다. 이 값은 공시가 "최대"라고 **명시한**
                # 그 항목 묶음의 상한이므로, 한 항목으로 볼 수 있는 크기를 넘어도
                # 정상이다 (예: "매일 우대금리 … (최대 연 3.10%p)").
                if term_applies(line, term, tiers):
                    groups[-1].append(value)
                skip_deeper_than = level
            pending = 0
            continue

        each = EACH_RATE.search(line)
        if each:                              # 규칙 C — "각 연0.10%p"
            flush_alt()
            groups[-1] += [float(each.group(1))] * max(pending, 1)
            pending = 0
            continue

        # 대안 묶음은 "둘 중 하나"이므로 최댓값이 한 항목 크기를 넘어도 정상이다
        # (예: "31일 저금 성공 시 : 연 9.0%"). 그래서 축이 맞는 줄에는 상한을 걸지 않는다.
        # 단 묶음이 한 줄뿐이면 대안이 아니므로 flush_alt()에서 상한을 다시 적용한다.
        is_alt = bool(ALT_AXIS.match(line))
        raw = [(m.start(), float(m.group(1))) for m in RATE.finditer(line)
               if float(m.group(1)) > 0]
        values = raw if is_alt else [v for v in raw if v[1] <= ITEM_RATE_MAX]
        if not values:
            if level != NO_MARK_LEVEL:
                pending += 1                  # 금리 없이 나열된 항목
            continue

        pending = 0
        if not term_applies(line, term, tiers):            # 규칙 G
            flush_alt()
            continue
        rate = value_for_term(line, values, term, tiers)   # 규칙 D·G′
        if is_alt:                                         # 규칙 I — 대안 축
            if alt_run and alt_run[-1][0] != level:
                flush_alt()
            alt_run.append((level, rate))
            continue
        flush_alt()
        groups[-1].append(rate)
        if EXCLUSIVE.search(line):            # 규칙 H — 뒤따르는 ①② 는 이 항목의 대안이다
            skip_deeper_than = level

    flush_alt()
    groups = [g for g in groups if g]
    if not groups:
        return [], cap
    if len(groups) == 1:
        return groups[0], cap
    return max(groups, key=sum), cap         # 규칙 I — 고객유형 묶음은 합이 큰 쪽 하나


def declared_bonus_v3(text: str, term: int = TARGET_TERM) -> tuple[float, float | None]:
    items, cap = parse_bonus_items_v3(text, term)
    total = sum(items)
    return (min(total, cap) if (items and cap is not None) else total), cap
