# -*- coding: utf-8 -*-
"""파일럿 정답(gold) 초안과 사람이 확정할 검토 시트를 만든다.

`docs/spec/prereg-02-pilot.md` §4의 정답 규칙을 구현한다.
  조건없음 층 → 기본금리
  닫힘 층     → 기본금리 + 충족된 우대금리 합 (상한 적용)
  안닫힘 층   → "알 수 없다" (하한 = 기본 + 충족 우대)

**출력은 초안이다.** 사전등록 §4는 정답을 "사람이 원문을 보고 확정한 조건표"에서
계산하도록 정했고, §2는 층 판정도 사람이 확인하도록 정했다. 이 스크립트는 그 확인을
받을 시트를 만드는 데까지만 관여한다. 자동 매핑은 상태 변수 키워드 초안까지다.

사용법: python src/analysis/build_gold.py [YYYYMMDD]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finlife_rules import parse_items_with_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = REPO_ROOT / "data" / "pilot"

# prereg §3의 7변수 초안 매핑용 키워드 (추출 시점 유형 제한 — 별칭 사전이 아니다)
STATE_KEYWORDS = {
    "급여이체": ["급여", "월급"],
    "자동이체": ["자동이체", "자동납입", "공과금"],
    "카드실적": ["카드"],
    "첫거래": ["첫거래", "첫 거래", "최초", "신규고객", "첫만남", "보유이력이 없", "미보유"],
    "비대면가입": ["인터넷", "모바일", "비대면", "스마트", "온라인", "앱"],
    "청약보유": ["청약"],
    "기존예치잔액": ["평잔", "총수신", "요구불"],
    "통장미발급": ["통장미발급", "통장 미발급", "무통장", "종이통장", "전자통장", "통장미발행"],
}
# "미발급"은 뺐다 — 통장미발급이 이제 상태 변수라 부정 조건으로 볼 필요가 없다.
# "제외"도 뺐다 — "만기달 제외한 계약기간의 1/2" 처럼 부정 조건이 아닌 문구를 잡았다(오탐).
NEGATIVE_MARKERS = ["없는", "없이", "미보유", "미가입", "않은"]

AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(천만원|백만원|만원)\s*이상")
MONTHS = re.compile(r"(\d+)\s*개월\s*이상")
COUNT = re.compile(r"(\d+)\s*(?:회|건)\s*이상")
RATIO = re.compile(r"(\d+)\s*/\s*(\d+)\s*이상")
UNIT = {"만원": 10_000, "백만원": 1_000_000, "천만원": 10_000_000}


def extract_threshold(line: str) -> dict | None:
    """조건이 요구하는 임계값을 뽑는다 (금액 / 개월 / 횟수 / 기간비율)."""
    found = AMOUNT.search(line)
    if found:
        return {"kind": "amount", "value": float(found.group(1)) * UNIT[found.group(2)],
                "text": found.group(0)}
    found = MONTHS.search(line)
    if found:
        return {"kind": "months", "value": int(found.group(1)), "text": found.group(0)}
    found = RATIO.search(line)
    if found:
        return {"kind": "ratio", "value": int(found.group(1)) / int(found.group(2)),
                "text": found.group(0)}
    found = COUNT.search(line)
    if found:
        return {"kind": "count", "value": int(found.group(1)), "text": found.group(0)}
    return None


def meets(var: str, state: dict, threshold: dict | None) -> bool:
    """상태가 그 조건을 충족하는가. 임계가 있으면 수치로 비교한다 (prereg §3)."""
    if var == "첫거래":
        return bool(state["첫거래"])
    if var == "비대면가입":
        return bool(state["비대면가입"])
    if var == "청약보유":
        return bool(state["청약보유"])
    if var == "통장미발급":
        return bool(state["통장미발급"])
    if var == "카드실적":
        have = state["카드_월결제액"]
        return have >= threshold["value"] if (threshold and threshold["kind"] == "amount") else have > 0
    if var == "급여이체":
        if threshold and threshold["kind"] == "amount":
            return state["급여_월입금액"] >= threshold["value"]
        if threshold and threshold["kind"] == "months":
            return state["급여_개월수"] >= threshold["value"]
        return state["급여_월입금액"] > 0
    if var == "자동이체":
        if threshold and threshold["kind"] == "ratio":
            return state["자동이체_기간비율"] >= threshold["value"]
        if threshold and threshold["kind"] == "count":
            return state["자동이체_월건수"] >= threshold["value"]
        return state["자동이체_월건수"] > 0
    if var == "기존예치잔액":
        have = state["기존예치잔액"]
        return have >= threshold["value"] if (threshold and threshold["kind"] == "amount") else have > 0
    return False


def map_state(line: str) -> tuple[list[str], bool]:
    matched = [var for var, kws in STATE_KEYWORDS.items() if any(k in line for k in kws)]
    return matched, any(m in line for m in NEGATIVE_MARKERS)


def load_overrides() -> dict:
    path = Path(__file__).resolve().parent / "gold_overrides.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("products", {})


OVERRIDES = load_overrides()


def draft_gold(item: dict) -> dict:
    base, cap, state = item["base_rate"], item["cap"], item["state"]
    rows = []
    ov = OVERRIDES.get(item["product_code"], {})
    stratum = ov.get("stratum") or item["stratum"]
    skip = ov.get("ignore_lines", [])
    for parsed in parse_items_with_text(item["spcl_cnd"]):
        if any(marker in parsed["label"] for marker in skip):
            continue
        matched, negative = map_state(parsed["label"])
        threshold = extract_threshold(parsed["label"])
        if negative and matched:
            # 부정 조건("보유이력이 없는 경우")은 상태 변수 의미로 그대로 판정된다.
            # 우리 변수 `첫거래`가 이미 "이 은행과 거래한 적이 없음"을 뜻하므로
            # 별도 극성 반전이 필요 없다 (2026-08-25 확정).
            decision = "충족" if all(meets(v, state, threshold) for v in matched) else "미충족"
        elif not matched:
            decision = "미충족(상태변수 없음)"
        else:
            decision = "충족" if all(meets(v, state, threshold) for v in matched) else "미충족"
        rows.append({**parsed, "states": matched, "negative": negative,
                     "threshold": threshold["text"] if threshold else None, "decision": decision})

    earned = sum(r["rate"] for r in rows if r["decision"] == "충족")
    if cap is not None:
        earned = min(earned, cap)
    lower = round(base + earned, 3)
    if stratum == "조건없음":
        gold, kind = base, "단일값"
    elif stratum == "닫힘":
        gold, kind = lower, "단일값"
    else:
        gold, kind = None, f"알 수 없다 (하한 {lower:.2f}%)"
    return {"qid": item["qid"], "stratum": stratum, "pattern": item["state_pattern"],
            "product": item["product_name"], "base": base, "cap": cap,
            "earned": round(earned, 3), "gold": gold, "gold_kind": kind, "rows": rows}


def gold_text(draft: dict) -> str:
    return draft["gold_kind"] if draft["gold"] is None else f"{draft['gold']:.2f}%"


def write_review_sheet(sample: dict, drafts: list[dict], stamp: str) -> Path:
    head = [
        f"# 파일럿 검토 시트 (스냅샷 {stamp})",
        "",
        "사전등록 `docs/spec/prereg-02-pilot.md` §2·§4에 따라 **사람이 확인할 두 가지**를 담았다.",
        "",
        "1. **층 판정** — 자동 분류가 맞는지. 파싱이 우대금리가 아닌 숫자를 항목으로 읽는",
        "   경우가 있다(예: `· 만기 해지 시 : 연 2.50% 제공`)",
        "2. **조건 매핑** — 각 우대 항목이 어떤 상태 변수에 걸리는지",
        "",
        "```",
        "층 판정   : 닫힘 | 안닫힘 | 조건없음",
        "조건 매핑 : 급여이체 · 자동이체 · 카드실적 · 첫거래 · 비대면가입 · 청약보유",
        "            해당없음 = 우리 상태 변수로 표현되지 않는 조건 (→ 항상 미충족)",
        "            부정     = 그 상태가 '없어야' 충족되는 조건",
        "            무시     = 우대금리 항목이 아님 (파싱 오류)",
        "```",
        "",
        "이 파일은 git에 커밋하지 않는다.",
        "",
    ]
    body = []
    for item, draft in zip(sample["items"], drafts):
        body += [f"## {item['qid']} · {item['product_name']} ({item['bank']})",
                 "",
                 f"- 기본 {item['base_rate']}% → 최고 {item['max_rate']}%"
                 f" (폭 {item['gap']:+.2f}) · 상한 {item['cap'] if item['cap'] is not None else '없음'}",
                 f"- 자동 층 판정: **{item['stratum']}** · 상태패턴 {item['state_pattern']}",
                 f"- 정답 초안: **{gold_text(draft)}**",
                 "",
                 "| 층 판정 확인 | |", "|---|---|", "| 자동 판정이 맞는가? | (맞음 / 틀림 → 올바른 층) |",
                 "",
                 "| 우대 항목 (공시 원문) | 금리 | 임계 | 자동 초안 | 자동 판정 | 확인 |",
                 "|---|---|---|---|---|---|"]
        if not draft["rows"]:
            body.append("| *(우대금리 항목이 파싱되지 않았다 — 원문 확인 필요)* | | | | | |")
        for r in draft["rows"]:
            drafted = "부정?" if r["negative"] else (", ".join(r["states"]) or "해당없음")
            body.append(f"| {r['label'].replace('|', '/')[:60]} | {r['rate']} | {r.get('threshold') or '-'} "
                        f"| {drafted} | {r['decision']} | |")
        body.append("")
    out = PILOT_DIR / f"gold_review_{stamp}.md"
    out.write_text("\n".join(head + body), encoding="utf-8")
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    stamp = sys.argv[1] if len(sys.argv) > 1 else "20260824"
    path = PILOT_DIR / f"sample_{stamp}.json"
    if not path.exists():
        raise SystemExit(f"표본이 없다: {path} — build_pilot_sample.py를 먼저 돌린다")
    sample = json.loads(path.read_text(encoding="utf-8"))
    drafts = [draft_gold(it) for it in sample["items"]]

    out = PILOT_DIR / f"gold_draft_{stamp}.json"
    out.write_text(json.dumps({"snapshot": stamp, "items": drafts}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    sheet = write_review_sheet(sample, drafts, stamp)

    print(f"{'qid':4s} {'층':6s} {'상태':6s} {'상품':26s} {'기본':>5s} {'획득':>5s} {'정답 초안':>14s}")
    for d in drafts:
        gold = "알 수 없다" if d["gold"] is None else f"{d['gold']:.2f}%"
        print(f"{d['qid']:4s} {d['stratum']:6s} {d['pattern']:6s} {d['product'][:26]:26s} "
              f"{d['base']:5} {d['earned']:5} {gold:>14s}")
    total_rows = sum(len(d["rows"]) for d in drafts)
    mapped = sum(1 for d in drafts for r in d["rows"] if r["decision"] in ("충족", "미충족"))
    negative = sum(1 for d in drafts for r in d["rows"] if r["negative"])
    print(f"\n우대 항목 {total_rows}개 · 상태변수 매핑 {mapped}개 ({mapped/max(total_rows,1)*100:.0f}%) "
          f"· 부정조건 후보 {negative}개")
    print(f"초안 → {out.relative_to(REPO_ROOT)}")
    print(f"검토 시트 → {sheet.relative_to(REPO_ROOT)}  ← 사람이 채운다")


if __name__ == "__main__":
    main()
