# -*- coding: utf-8 -*-
"""파일럿 응답을 채점한다 (`docs/spec/prereg-02-pilot.md` §4.1 · §5 · §7).

채점은 최대한 결정론으로 한다.
  rate_percent   → 값 비교 (소수 둘째 자리)
  verdict        → computable / unknown 값 비교
  conditions_met → 포함 비교 (진단용, 판정 미반영)
  schema_valid   → JSON 블록 파싱 성공 여부. 실패는 실패로 집계

자동 분류하는 실패 유형: F3(단정) · F4(최고금리) · F5(상한 무시) · F7(과잉 회피).
F1·F2·F6은 사람 확인이 필요하므로 후보만 표시한다.

사용법: python src/pilot/score.py <model_tag> [YYYYMMDD]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = REPO_ROOT / "data" / "pilot"
TOL = 0.005

JSON_BLOCK = re.compile(r"\{[^{}]*\"verdict\"[^{}]*\}")


def parse_block(text: str) -> dict | None:
    hits = JSON_BLOCK.findall(text or "")
    for raw in reversed(hits):                       # 마지막 블록이 최종 답
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def judge(gold: dict, sample: dict, block: dict | None) -> dict:
    """한 응답을 판정한다. gold는 build_gold 산출, sample은 상품 메타."""
    if block is None:
        return {"schema_valid": False, "correct": False, "ftypes": ["schema"]}
    rate, verdict = block.get("rate_percent"), block.get("verdict")
    ftypes, expected = [], gold["gold"]

    if expected is None:                             # 안닫힘 — 정답은 "알 수 없다"
        correct = verdict == "unknown"
        if verdict == "computable":
            ftypes.append("F3")                      # 확인 불가인데 단정
    else:
        correct = verdict == "computable" and isinstance(rate, (int, float)) \
            and abs(float(rate) - expected) <= TOL
        if verdict == "unknown":
            ftypes.append("F7")                      # 계산 가능한데 회피
        elif isinstance(rate, (int, float)):
            if abs(float(rate) - sample["max_rate"]) <= TOL and expected != sample["max_rate"]:
                ftypes.append("F4")                  # 최고금리로 답
            cap = sample.get("cap")
            if cap is not None and float(rate) > sample["base_rate"] + cap + TOL:
                ftypes.append("F5")                  # 상한 무시
            if not correct and "F4" not in ftypes and float(rate) > expected + TOL:
                ftypes.append("F1?")                 # 미충족 조건을 충족으로 가정 (후보)
            if not correct and float(rate) < expected - TOL:
                ftypes.append("F1-under?")           # 충족 조건을 빠뜨림 (후보)
    return {"schema_valid": True, "correct": correct, "ftypes": ftypes,
            "rate": rate, "verdict": verdict, "conditions_met": block.get("conditions_met")}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        raise SystemExit("사용법: python src/pilot/score.py <model_tag> [YYYYMMDD]")
    tag = sys.argv[1]
    stamp = sys.argv[2] if len(sys.argv) > 2 else "20260824"

    gold = {g["qid"]: g for g in json.loads(
        (PILOT_DIR / f"gold_draft_{stamp}.json").read_text(encoding="utf-8"))["items"]}
    sample = {s["qid"]: s for s in json.loads(
        (PILOT_DIR / f"sample_{stamp}.json").read_text(encoding="utf-8"))["items"]}
    raw = json.loads((PILOT_DIR / "raw" / f"{tag}_{stamp}.json").read_text(encoding="utf-8"))

    per_q: dict[str, list[dict]] = {}
    for run in raw["runs"]:
        block = parse_block(run["text"]) if not run["error"] else None
        per_q.setdefault(run["qid"], []).append(judge(gold[run["qid"]], sample[run["qid"]], block))

    rows, ftype_counter = [], Counter()
    for qid, judged in per_q.items():
        correct = sum(1 for j in judged if j["correct"]) * 2 >= len(judged)   # k>1이면 과반
        ftypes = sorted({f for j in judged for f in j["ftypes"]})
        schema = all(j["schema_valid"] for j in judged)
        rows.append({"qid": qid, "stratum": gold[qid]["stratum"], "pattern": gold[qid]["pattern"],
                     "gold": gold[qid]["gold"], "got": judged[0].get("rate"),
                     "verdict": judged[0].get("verdict"), "correct": correct,
                     "schema_valid": schema, "ftypes": ftypes})
        if not correct:
            for f in ftypes:
                ftype_counter[f] += 1

    print(f"[{raw['model_tag']}] {raw['model_id']} · k={raw['k']} · 스냅샷 {stamp}\n")
    print(f"{'qid':4s} {'층':6s} {'상태':6s} {'정답':>10s} {'응답':>10s} {'verdict':11s} {'판정':4s} 유형")
    for r in sorted(rows, key=lambda x: x["qid"]):
        g = "알수없다" if r["gold"] is None else f"{r['gold']:.2f}%"
        got = "-" if r["got"] is None else f"{r['got']}"
        mark = "OK" if r["correct"] else "X"
        print(f"{r['qid']:4s} {r['stratum']:6s} {r['pattern']:6s} {g:>10s} {got:>10s} "
              f"{str(r['verdict']):11s} {mark:4s} {','.join(r['ftypes'])}")

    by_stratum = Counter(r["stratum"] for r in rows)
    ok_stratum = Counter(r["stratum"] for r in rows if r["correct"])
    computable = [r for r in rows if r["stratum"] in ("닫힘", "조건없음")]
    over_abstain = [r for r in computable if "F7" in r["ftypes"]]

    print(f"\n■ 층별 정답 (총 {sum(ok_stratum.values())}/{len(rows)})")
    for st in ("닫힘", "안닫힘", "조건없음"):
        if by_stratum[st]:
            print(f"   {st:6s} {ok_stratum[st]:2d}/{by_stratum[st]:2d}")
    print(f"\n■ schema_valid : {sum(1 for r in rows if r['schema_valid'])}/{len(rows)}")
    print(f"■ F7 과잉 회피 : {len(over_abstain)}/{len(computable)} "
          f"({len(over_abstain)/max(len(computable),1)*100:.0f}%) — §5.1 제약: 20% 초과면 안닫힘 성적 배제")
    print(f"■ 오답 {len(rows) - sum(ok_stratum.values())}건의 유형 분포: {dict(ftype_counter)}")


if __name__ == "__main__":
    main()
