# -*- coding: utf-8 -*-
"""추출기 A(규칙 파서) vs B(제한 스키마 LLM) 비교 — `docs/spec/prereg-03-extraction.md` §2.1 · §3~5.

지표마다 분석 단위가 다르다. 사전등록(`decisions/0005`)에 고정된 그대로 쓴다.

    닫힘률 (주 지표)      행 단위        개발 집합 62.8%와 같은 단위여야 비교가 된다
    가중 닫힘률 (부 지표)  조건문 동일가중  행 수 많은 조건문 몇 개에 끌려갔는지 본다
    McNemar 유의검정       (조건문,기간) 쌍  같은 텍스트를 중복해 세지 않는다
    95% 신뢰구간          조건문 클러스터 부트스트랩  실질 표본은 행 수가 아니다

**왜 이렇게 나누나** — 홀드아웃 1,090행이 서로 다른 조건문 75종에서만 나온다. 행 단위로
McNemar를 돌리면 같은 텍스트를 평균 14.5번 세는 것이고 p값이 실제보다 작아져 B의 우위를
과대 판정한다.

표준 라이브러리만 쓴다 (scipy 없이 McNemar 정확검정·Wilcoxon·부트스트랩을 직접 계산).

사용법:
    python src/analysis/compare_extractors.py 20260825 --group savingsbank
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_llm import CONDITION_TYPES, load_pairs  # noqa: E402
from finlife_rules import TOLERANCE, parse_bonus_items  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "pilot"
BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 20260825      # 사전등록 §2.1에 고정
THRESHOLD_PP = 5.0             # 판정 임계 %p (§5)


# ─── 추출기 두 개 ────────────────────────────────────────────────────────────

def declared_rules(text: str, term: int) -> tuple[float, float | None, int]:
    """A 규칙 파서. 반환값 (합계, 상한, 항목 수)."""
    items, cap = parse_bonus_items(text, term)
    total = sum(items)
    return (min(total, cap) if (items and cap is not None) else total), cap, len(items)


def declared_llm(parsed: dict) -> tuple[float, float | None, int]:
    """B 제한 스키마 LLM. 반환값 (합계, 상한, 항목 수).

    가입기간에 해당하지 않는 항목은 제외하고, `exclusive_group`으로 묶인 항목은
    합하지 않고 그 그룹의 최댓값만 센다("중복 적용 불가"). 마지막에 상한을 씌운다 —
    A와 같은 순서다.
    """
    items = [it for it in parsed.get("items", []) if it.get("applies_to_term")]
    total, groups = 0.0, {}
    for it in items:
        rate = float(it.get("rate") or 0)
        group = it.get("exclusive_group")
        if group:
            groups[group] = max(groups.get(group, 0.0), rate)
        else:
            total += rate
    total = round(total + sum(groups.values()), 4)
    cap = parsed.get("cap")
    return (min(total, cap) if (items and cap is not None) else total), cap, len(items)


# ─── 검정·구간 (표준 라이브러리) ──────────────────────────────────────────────

def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 정확검정 양측 p값. 불일치쌍 b+c 중 b가 관측될 확률 기반 이항검정."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def wilcoxon_signed_rank(diffs: list[float]) -> tuple[float, int]:
    """부호순위검정 양측 p값 (정규근사 · 동순위 보정). 반환값 (p, 0이 아닌 차이 수).

    쌍마다 닫힘 비율의 차이를 쓴다 — 이질적인 쌍(한 쌍 안에 gap이 여러 개)을
    이진화하지 않고 다룰 수 있다. n<20이면 정규근사가 부정확하므로 함께 알린다.
    """
    nz = [d for d in diffs if d != 0]
    n = len(nz)
    if n == 0:
        return 1.0, 0
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:                                    # 동순위는 평균 순위를 준다
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    mean = n * (n + 1) / 4
    tie_groups = Counter(abs(d) for d in nz)
    tie_corr = sum(t ** 3 - t for t in tie_groups.values()) / 48
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24 - tie_corr)
    if sd == 0:
        return 1.0, n
    z = (abs(w_plus - mean) - 0.5) / sd             # 연속성 보정
    p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    return max(0.0, min(1.0, p)), n


def cluster_bootstrap_ci(by_text: dict, seed: int, reps: int,
                         weighted: bool = False) -> tuple[float, float]:
    """조건문을 복원추출해 닫힘률 차이(B−A)의 95% 구간을 낸다.

    조건문에 딸린 행 **전체를 함께** 뽑는다. 행을 개별로 뽑으면 클러스터 구조를
    무시해 구간이 실제보다 좁아진다.
    """
    keys = list(by_text)
    rng = random.Random(seed)
    diffs = []
    for _ in range(reps):
        picked = [by_text[rng.choice(keys)] for _ in keys]
        if weighted:                      # 조건문마다 동일 가중
            a = sum(sum(x["a_closed"] for x in rows) / len(rows) for rows in picked)
            b = sum(sum(x["b_closed"] for x in rows) / len(rows) for rows in picked)
            diffs.append((b - a) / len(picked) * 100)
            continue
        n = sum(len(rows) for rows in picked)
        if not n:
            continue
        a = sum(r["a_closed"] for rows in picked for r in rows)
        b = sum(r["b_closed"] for rows in picked for r in rows)
        diffs.append((b - a) / n * 100)
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[min(int(0.975 * len(diffs)), len(diffs) - 1)]
    return lo, hi


# ─── 본체 ────────────────────────────────────────────────────────────────────

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
        raise SystemExit("사용법: python src/analysis/compare_extractors.py YYYYMMDD "
                         "[--group bank|savingsbank]")
    stamp = argv[0]
    suffix = "" if group == "bank" else f"_{group}"

    rows, pairs = load_pairs(stamp, group)
    llm_path = OUT_DIR / f"extract_llm{suffix}_{stamp}.json"
    llm = json.loads(llm_path.read_text(encoding="utf-8"))
    by_pair = {p["pair_id"]: p for p in llm["pairs"]}
    if len(by_pair) != len(pairs):
        raise SystemExit(f"B의 결과가 {len(by_pair)}쌍뿐이다 (필요 {len(pairs)}) — "
                         f"extract_llm.py를 --limit 없이 다시 돌린다")

    # 행마다 두 추출기를 채점한다. 스키마 위반·호출 실패는 '닫히지 않음 + 항목 0개'로 센다.
    scored, type_counter = [], Counter()
    for row in rows:
        pair = pairs[row["pair_id"]]
        got = by_pair[row["pair_id"]]
        a_sum, a_cap, a_n = declared_rules(pair["text"], row["term"])
        if got["schema_ok"]:
            b_sum, b_cap, b_n = declared_llm(got["parsed"])
        else:
            b_sum, b_cap, b_n = 0.0, None, 0
        a_diff, b_diff = abs(a_sum - row["gap"]), abs(b_sum - row["gap"])
        scored.append({**row, "text": pair["text"],
                       "a_sum": a_sum, "a_cap": a_cap, "a_n": a_n,
                       "a_diff": round(a_diff, 3), "a_closed": a_n > 0 and a_diff <= TOLERANCE,
                       "b_sum": b_sum, "b_cap": b_cap, "b_n": b_n,
                       "b_diff": round(b_diff, 3), "b_closed": b_n > 0 and b_diff <= TOLERANCE,
                       "schema_ok": got["schema_ok"]})
    for got in llm["pairs"]:
        if got["schema_ok"]:
            for it in got["parsed"]["items"]:
                type_counter[it["condition_type"]] += 1

    n = len(scored)
    a_closed = sum(r["a_closed"] for r in scored)
    b_closed = sum(r["b_closed"] for r in scored)
    a_rate, b_rate = a_closed / n * 100, b_closed / n * 100

    print(f"추출기 비교 · 스냅샷 {stamp} ({group}) · {llm['model_id']}")
    print(f"조건 있는 행 {n} · (조건문,기간) 쌍 {len(pairs)} · 서로 다른 조건문 "
          f"{len({r['text'] for r in scored})}")
    print()
    print("■ 주 지표 — 닫힘률 (행 단위)")
    print(f"    A 규칙 파서      {a_closed:5d}/{n} = {a_rate:5.1f}%")
    print(f"    B 제한 스키마    {b_closed:5d}/{n} = {b_rate:5.1f}%")
    print(f"    차이 (B−A)                    {b_rate - a_rate:+5.1f}%p")

    # 부 지표 1 — 가중 닫힘률 (조건문마다 동일 가중)
    by_text = defaultdict(list)
    for r in scored:
        by_text[r["text"]].append(r)
    a_w = sum(sum(x["a_closed"] for x in v) / len(v) for v in by_text.values()) / len(by_text) * 100
    b_w = sum(sum(x["b_closed"] for x in v) / len(v) for v in by_text.values()) / len(by_text) * 100
    w_lo, w_hi = cluster_bootstrap_ci(by_text, BOOTSTRAP_SEED, BOOTSTRAP_N, weighted=True)
    split = (b_rate - a_rate >= THRESHOLD_PP) != (b_w - a_w >= THRESHOLD_PP)
    print()
    print(f"□ 가중 닫힘률 (조건문 {len(by_text)}종 동일 가중)")
    print(f"    A {a_w:5.1f}%   B {b_w:5.1f}%   차이 {b_w - a_w:+5.1f}%p"
          f"   CI [{w_lo:+.1f}%p, {w_hi:+.1f}%p]")
    if split:
        print("    ⚠ 주 지표와 판정이 갈린다 — 사전등록(decisions/0005)에 따라 "
              "**가중 닫힘률을 판정에 쓴다**")

    # 신뢰구간 — 조건문 클러스터 부트스트랩
    lo, hi = cluster_bootstrap_ci(by_text, BOOTSTRAP_SEED, BOOTSTRAP_N)
    print()
    print(f"□ 닫힘률 차이 95% 신뢰구간 (조건문 클러스터 부트스트랩 {BOOTSTRAP_N}회, "
          f"seed {BOOTSTRAP_SEED})")
    print(f"    [{lo:+.1f}%p, {hi:+.1f}%p]   폭 ±{(hi - lo) / 2:.1f}%p")

    # 지표 전제 점검 — 닫힘률은 (최고금리 − 기본금리)가 우대금리 합계를 담고 있다고
    # 전제한다. 그 전제가 깨지면 어떤 추출도 맞을 수 없다.
    zero_gap = sum(1 for r in scored if r["gap"] == 0)
    print()
    print("□ 지표 전제 점검 — 실제 금리폭(최고−기본)이 0인 행")
    print(f"    {zero_gap}/{n} = {zero_gap / n * 100:.1f}%")
    if zero_gap / n > 0.5:
        print("    ⚠ 조건문이 있는데 최고금리 = 기본금리인 행이 과반이다. 이 행들은")
        print("      **어떤 추출로도 닫을 수 없다** — 공시가 우대금리를 최고금리 필드에")
        print("      반영하지 않는 것이다. §8 두 번째 반증 조건(지표가 안 맞음)에 해당한다")

    # McNemar — 쌍 단위. 쌍의 행이 여러 gap을 가지면 과반으로 이진화한다(동수는 닫히지 않음).
    pair_rows = defaultdict(list)
    for r in scored:
        pair_rows[r["pair_id"]].append(r)
    b_only = c_only = 0
    prop_diffs = []
    for v in pair_rows.values():
        pa = sum(x["a_closed"] for x in v) / len(v)
        pb = sum(x["b_closed"] for x in v) / len(v)
        prop_diffs.append(pb - pa)
        ca, cb = pa > 0.5, pb > 0.5
        if cb and not ca:
            b_only += 1
        elif ca and not cb:
            c_only += 1
    p_mc = mcnemar_exact(b_only, c_only)
    p_wx, n_nz = wilcoxon_signed_rank(prop_diffs)
    hetero = sum(1 for v in pair_rows.values() if len({x["gap"] for x in v}) > 1)
    print()
    print(f"□ McNemar 정확검정 (쌍 {len(pair_rows)} 단위 · 과반 규칙 · "
          f"gap이 여러 개인 쌍 {hetero})")
    print(f"    B만 닫힘 {b_only} · A만 닫힘 {c_only} · 불일치쌍 {b_only + c_only}")
    print(f"    p = {p_mc:.4f}")
    print(f"□ Wilcoxon 부호순위검정 (쌍별 닫힘 비율 차 · 이진화 없음)")
    print(f"    0이 아닌 차 {n_nz} · p = {p_wx:.4f}"
          f"{'   ※ n<20이라 정규근사가 부정확하다' if 0 < n_nz < 20 else ''}")

    # 부 지표 2 — 회피를 막는 제약
    a_zero = sum(1 for r in scored if r["a_n"] == 0) / n * 100
    b_zero = sum(1 for r in scored if r["b_n"] == 0) / n * 100
    n_items = sum(type_counter.values())
    etc = type_counter.get("기타", 0)
    bad_schema = sum(1 for p in llm["pairs"] if not p["schema_ok"])
    print()
    print("□ 회피 방지 지표 (§4)")
    print(f"    항목 0개 비율   A {a_zero:5.1f}%   B {b_zero:5.1f}%   "
          f"차이 {b_zero - a_zero:+5.1f}%p")
    if b_zero - a_zero >= 5.0:
        print("    ⚠ B가 A보다 5%p 이상 높다 — 닫힘률과 무관하게 우위 불인정 (§5)")
    print(f"    `기타` 비율     {etc}/{n_items} = {etc / max(n_items, 1) * 100:.1f}% (항목 기준)")
    print(f"    스키마 위반     {bad_schema}/{len(llm['pairs'])} 쌍")

    print()
    print("□ 불일치 폭 분포 (|합계 − 실제폭|)")
    print(f"    {'구간':>16}   {'A':>5} {'B':>5}")
    for lo_d, hi_d in ((0.0, 0.06), (0.06, 0.3), (0.3, 1.0), (1.0, 3.0), (3.0, 1e9)):
        ca = sum(1 for r in scored if r["a_n"] and lo_d < r["a_diff"] <= hi_d)
        cb = sum(1 for r in scored if r["b_n"] and lo_d < r["b_diff"] <= hi_d)
        if ca or cb:
            label = f"{lo_d:.2f} < d <= {hi_d:.2f}" if hi_d < 1e9 else f"{lo_d:.2f} < d"
            print(f"    {label:>16}   {ca:5d} {cb:5d}")

    print()
    print("□ 상한(cap) 인식률")
    for tag, keyn in (("A", "a_cap"), ("B", "b_cap")):
        got_cap = sum(1 for r in scored if r[keyn] is not None)
        print(f"    {tag}  {got_cap}/{n} = {got_cap / n * 100:.1f}%")

    usage = llm.get("usage_total", {})
    cost = usage.get("input_tokens", 0) / 1e6 * 1.0 + usage.get("output_tokens", 0) / 1e6 * 5.0
    print()
    print("□ 비용·시간")
    print(f"    A  ~0 (로컬 정규식) · 1초 미만")
    print(f"    B  ${cost:.2f} · {llm.get('elapsed_s', 0):.0f}초 · 호출 {llm.get('n_called')}쌍")

    print()
    print("□ 유형 분포 (B가 고른 열거값)")
    for name in CONDITION_TYPES:
        cnt = type_counter.get(name, 0)
        if cnt:
            print(f"    {name:<24} {cnt:4d} ({cnt / max(n_items, 1) * 100:4.1f}%)")

    # §5 판정표
    print()
    # 판정에 쓰는 차이: 주 지표와 가중 닫힘률이 갈리면 가중 쪽이다 (decisions/0005)
    diff = (b_w - a_w) if split else (b_rate - a_rate)
    basis = "가중 닫힘률" if split else "닫힘률(행)"
    if b_zero - a_zero >= 5.0:
        verdict = "우위 불인정 — B의 항목 0개 비율이 A보다 5%p 이상 높다"
    elif diff >= THRESHOLD_PP and p_mc < 0.05:
        verdict = "제한 스키마 채택 — 추출 시점 형식 제한이 답이다"
    elif diff <= -THRESHOLD_PP and p_mc < 0.05:
        verdict = "제한 스키마 기각 — 규칙 파서를 본선으로 쓴다"
    else:
        verdict = "규칙 파서 유지 — 차이가 임계 안이거나 유의하지 않다"
    print(f"■ 사전등록 판정 (§5 판정표 · 근거 지표 {basis} {diff:+.1f}%p, p={p_mc:.4f})")
    print(f"    {verdict}")
    falsifier = []
    if a_rate < 40 and b_rate < 40:
        falsifier.append("§8 두 번째 — A·B 모두 닫힘률 40% 미만. 지표 자체가 이 공시에 "
                         "맞지 않을 가능성을 검토한다")
    if a_rate - 62.8 >= 15:
        falsifier.append("§8 세 번째 — A의 홀드아웃 닫힘률이 개발 집합보다 +15%p 이상")
    if falsifier:
        print()
        print("■ 반증 조건 발동 — 위 판정보다 이것이 앞선다")
        for f in falsifier:
            print(f"    {f}")

    out = OUT_DIR / f"compare{suffix}_{stamp}.json"
    out.write_text(json.dumps({
        "snapshot": stamp, "group": group, "model_id": llm["model_id"],
        "n_rows": n, "n_pairs": len(pair_rows), "n_texts": len(by_text),
        "closure_rate": {"a": a_rate, "b": b_rate, "diff_pp": diff},
        "weighted_closure_rate": {"a": a_w, "b": b_w, "diff_pp": b_w - a_w},
        "bootstrap_ci_pp": [lo, hi], "bootstrap": {"reps": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
        "mcnemar": {"b_only": b_only, "a_only": c_only, "p": p_mc, "hetero_pairs": hetero},
        "wilcoxon": {"n_nonzero": n_nz, "p": p_wx},
        "zero_item_rate": {"a": a_zero, "b": b_zero},
        "etc_rate": etc / max(n_items, 1) * 100, "schema_violations": bad_schema,
        "type_distribution": dict(type_counter), "cost_usd_b": cost,
        "weighted_ci_pp": [w_lo, w_hi], "zero_gap_rows": zero_gap,
        "verdict": verdict, "verdict_basis": basis,
        "falsifiers_fired": falsifier, "rows": scored,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
