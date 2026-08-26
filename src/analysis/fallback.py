# -*- coding: utf-8 -*-
"""폴백 구조 채점 — `../../docs/spec/prereg-04-fallback.md` §4 규칙 그대로.

폴백 규칙 (사전등록 §4에 실행 전 고정)
    1. A(규칙 파서 v3)를 돌린다
    2. |A 합계 − 폭| <= 0.06 이면 A 결과를 채택하고 끝낸다
    3. 아니면 B(제한 스키마 LLM)를 돌린다
    4. |B 합계 − 폭| <= 0.06 이면 B 결과를 채택한다
    5. 둘 다 안 맞으면 **B 결과를 채택하고** "계산불가" 층으로 라벨한다
       (B 는 condition_type 을 갖고 있어 사용자별 계산에 쓸 수 있다)

**게이트는 검사이지 예측이 아니다.** "이 문장은 어려워 보인다"로 고르지 않고,
싼 것을 먼저 돌려 산수가 맞는지 보고 넘긴다.

분모는 **폭 > 0 행만**이다 (사전등록 §2). 폭 = 0 행은 어떤 추출도 맞을 수 없으므로
분모에서 빼고 별도로 센다.

사용법:
    python src/analysis/fallback.py 20260826
    python src/analysis/fallback.py 20260825 --group savingsbank
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_extractors import declared_llm, declared_rules, mcnemar_exact  # noqa: E402
from extract_llm import load_pairs  # noqa: E402
from finlife_rules import TOLERANCE, parse_bonus_items_v3  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "pilot"


def declared_rules_v3(text: str, term: int) -> tuple[float, float | None, int]:
    """A 는 규칙 v3 를 쓴다 (사전등록 §8 — v3 고정)."""
    items, cap = parse_bonus_items_v3(text, term)
    total = sum(items)
    return (min(total, cap) if (items and cap is not None) else total), cap, len(items)


def score(rows: list[dict], pairs: list[dict], by_pair: dict) -> list[dict]:
    """행마다 A · B · 폴백을 채점한다."""
    out = []
    for row in rows:
        text = pairs[row["pair_id"]]["text"]
        a_sum, _a_cap, a_n = declared_rules_v3(text, row["term"])
        got = by_pair.get(row["pair_id"])
        if got and got["schema_ok"]:
            b_sum, _b_cap, b_n = declared_llm(got["parsed"])
        else:
            b_sum, b_n = 0.0, 0
        a_sig = round(a_sum - row["gap"], 3)
        b_sig = round(b_sum - row["gap"], 3)
        a_ok, b_ok = abs(a_sig) <= TOLERANCE, abs(b_sig) <= TOLERANCE

        # 폴백 — 사전등록 §4 규칙 그대로
        if a_ok:
            f_from, f_sig, f_n, called = "A", a_sig, a_n, False
        else:
            f_from, f_sig, f_n, called = "B", b_sig, b_n, True
        out.append({**row, "a_sig": a_sig, "b_sig": b_sig, "a_n": a_n, "b_n": b_n,
                    "a_ok": a_ok, "b_ok": b_ok,
                    "f_from": f_from, "f_sig": f_sig, "f_n": f_n,
                    "f_ok": abs(f_sig) <= TOLERANCE, "llm_called": called})
    return out


def summarize(scored: list[dict], label: str) -> dict:
    n = len(scored)
    if not n:
        return {}

    def block(prefix: str) -> dict:
        ok = sum(1 for r in scored if r[f"{prefix}_ok"])
        over = sum(1 for r in scored if r[f"{prefix}_sig"] > TOLERANCE)
        under = sum(1 for r in scored if r[f"{prefix}_sig"] < -TOLERANCE)
        zero_n = sum(1 for r in scored if r[f"{prefix}_n"] == 0)
        return {"ok": ok, "rate": round(ok / n * 100, 1),
                "over": over, "under": under, "zero_items": zero_n,
                "zero_rate": round(zero_n / n * 100, 1)}

    a, b, f = block("a"), block("b"), block("f")
    called = sum(1 for r in scored if r["llm_called"])
    b_only = sum(1 for r in scored if r["b_ok"] and not r["a_ok"])
    a_only = sum(1 for r in scored if r["a_ok"] and not r["b_ok"])

    print(f"\n{'=' * 78}\n{label} · 폭>0 {n}행\n{'=' * 78}")
    print(f"{'':<14}{'맞음':>12}{'넘침':>8}{'모자람':>8}{'항목0개':>10}")
    for name, blk in (("A 규칙 v3", a), ("B 제한스키마", b), ("폴백", f)):
        print(f"{name:<14}{blk['ok']:>5} ({blk['rate']:>4.1f}%){blk['over']:>8}"
              f"{blk['under']:>8}{blk['zero_items']:>6} ({blk['zero_rate']:>4.1f}%)")
    print(f"\n  폴백 − A  {f['rate'] - a['rate']:+.1f}%p"
          f"     폴백 − B  {f['rate'] - b['rate']:+.1f}%p")
    print(f"  LLM 호출  {called}/{n} = {called / n * 100:.1f}%")
    print(f"  A만 맞음 {a_only} · B만 맞음 {b_only} · McNemar p={mcnemar_exact(b_only, a_only):.4f}")
    return {"n": n, "a": a, "b": b, "f": f,
            "llm_called": called, "llm_rate": round(called / n * 100, 1),
            "a_only": a_only, "b_only": b_only,
            "mcnemar_p": mcnemar_exact(b_only, a_only)}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group = "bank"
    if "--group" in argv:
        i = argv.index("--group")
        group = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/fallback.py YYYYMMDD "
                         "[--group bank|savingsbank]")
    stamp = argv[0]
    suffix = "" if group == "bank" else f"_{group}"

    rows, pairs = load_pairs(stamp, group)
    llm_path = OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    if not llm_path.exists():
        raise SystemExit(f"B 결과가 없다: {llm_path.relative_to(REPO_ROOT)}")
    llm = json.loads(llm_path.read_text(encoding="utf-8"))
    by_pair = {p["pair_id"]: p for p in llm["pairs"]}
    if len(by_pair) < len(pairs):
        raise SystemExit(f"B 결과가 {len(by_pair)}쌍뿐이다 (필요 {len(pairs)}) — "
                         f"extract_llm.py 를 --limit 없이 다시 돌린다")

    pos = [r for r in rows if r["gap"] > 0]
    zero = [r for r in rows if r["gap"] <= 0]
    print(f"스냅샷 {stamp} ({group}) · {llm['model_id']}")
    print(f"조건 있는 행 {len(rows)} → 분모(폭>0) {len(pos)} · "
          f"분모에서 뺀 폭 0 행 {len(zero)}")
    print(f"  ※ 폭 0 행은 '공시미반영' 층으로 별도 보고한다 (사전등록 §2)")

    scored = score(pos, pairs, by_pair)
    result = summarize(scored, f"{group} 판정")

    # 진짜 과다 추출 — 분모가 이미 폭>0 이므로 넘침이 곧 진짜 과다다
    print(f"\n  진짜 과다 추출 (분모가 폭>0 이므로 넘침 = 진짜 과다)")
    print(f"    A {result['a']['over']} · B {result['b']['over']} · 폴백 {result['f']['over']}")

    out = OUT_DIR / f"fallback{suffix}_{stamp}.json"
    out.write_text(json.dumps({"snapshot": stamp, "group": group,
                               "n_condition_rows": len(rows), "n_zero_gap": len(zero),
                               "summary": result, "rows": scored},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
