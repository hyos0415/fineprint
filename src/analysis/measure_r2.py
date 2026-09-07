# -*- coding: utf-8 -*-
"""R2 측정 — 표본 20문장 × 모델 하나 → `prereg-27` §3 지표 (이슈 #73).

무엇을 재나
    잘못 채운 답 · 빠뜨린 답 · 스코프 다섯 칸 정확도 · 거래 은행 일치 · 지연 · (모델 무관) 라벨을 state 에 넣었을 때 질문 수 변화.

지키는 것
    - 모델 입출력 원문을 파일에 남기지 않는다 (`0042` D3 · 합성 문장이라도 운영과 같은 규칙으로 잰다). 남기는 것은 집계와
      틀린 항목의 (키, 값) 뿐이다
    - 정답표(`r2_sample.py`)는 측정 뒤 고치지 않는다. 프롬프트를 고치면 `--label` 로 판을 갈라 저장한다

사용법:
    python src/analysis/measure_r2.py --model qwen3.5-4b [--url http://127.0.0.1:8081] [--label v1]
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask_budget as AB  # noqa: E402
import calculate as C  # noqa: E402
import r2_parse as R2  # noqa: E402
from r2_sample2 import SETS  # noqa: E402
from r2_sample3 import TEST2  # noqa: E402

SETS = {**SETS, "test2": TEST2}      # test2 — `prereg-28` §7 (은행 역할 스키마) 를 한 번 재는 새 평가 표본
S: list[dict] = []          # `--set` 으로 고른다 (기본 dev). 2차(`prereg-28`)부터 dev/test 를 가른다

STAMPS = {"bank": "20260826", "savingsbank": "20260825"}


def plan_keys(group: str, banks: list[str], kinds: str | None) -> tuple[set[str], int]:
    """그 스코프의 후보 집합에서 나올 수 있는 상태 키와 "전부 답하면" 질문 수."""
    rows, bp = AB.load(STAMPS[group], group, 12)
    rows = C.scope_rows(rows, ",".join(banks) if banks else None, kinds)
    if not rows:
        return set(), 0
    plan = C.question_plan(rows, bp)
    return set(plan.keys()) | {C.TRADED_KEY}, C.questions_left(plan, {})


def value_axis(sample: dict) -> dict:
    """모델 무관 — 라벨 답을 state 에 넣으면 질문이 몇 개 주나 (`prereg-27` P6)."""
    sc = sample["scope"]
    group = sc["group"] or "bank"
    rows, bp = AB.load(STAMPS[group], group, 12)
    rows = C.scope_rows(rows, ",".join(sc["banks"]) if sc["banks"] else None, sc["kinds"])
    if not rows:
        return {"전체": 0, "라벨 뒤": 0, "감소": 0}
    plan = C.question_plan(rows, bp)
    total = C.questions_left(plan, {})
    state = {k: ({"예": True, "아니오": False, "모름": C.UNSURE}[v]) for k, v in sample["answers"].items() if k in plan}
    if sample["traded"] is not None:
        state[C.TRADED_KEY] = sample["traded"]
    left = C.questions_left(plan, state)
    return {"전체": total, "라벨 뒤": left, "감소": total - left}


def score(sample: dict, cand: dict, keys: set[str] | None = None) -> dict:
    """라벨과 대조. **잘못 채운 답은 두 겹으로 센다** — 모델이 낸 것 전부(`raw`)와 후보 집합 필터 뒤 화면에 갈 것(`shown`).

    첫 판(v1)에서 필터가 뜻이 뒤집힌 답 셋을 조용히 걸러 냈다("처음이야" → 첫거래 아니오 · 하나은행 → 하나저축은행).
    화면 안전은 `shown` 이 말하지만 모델의 신뢰도는 `raw` 가 말한다 — 둘 다 적는다.
    빠뜨린 답은 **후보 집합에 있는 라벨**만 센다 — 그 스코프에서 물을 수 없는 조건을 안 채운 것은 빠뜨린 것이 아니다.
    """
    label = dict(sample["answers"])
    also = dict(sample.get("also_ok") or {})
    pred = {a["key"]: a["value"] for a in cand["answers"]}
    raw_pred = {**pred, **{d["key"]: d["value"] for d in cand["dropped"]}}
    wrong = [(k, v) for k, v in pred.items() if label.get(k) != v and also.get(k) != v]
    wrong_raw = [(k, v) for k, v in raw_pred.items() if label.get(k) != v and also.get(k) != v]
    askable = {k: v for k, v in label.items() if keys is None or k in keys}
    missed = [(k, v) for k, v in askable.items() if pred.get(k) != v]
    sc, ls = cand["scope"], sample["scope"]
    fields = {"권역": (sc["group"] or None) == ls["group"],
              "은행": sorted(sc["banks"]) == sorted(ls["banks"]),
              "상품군": (sc["kinds"] or None) == ls["kinds"],
              "기간": sc["term"] == ls["term"],
              "금액": (sc["amount_deposit"] or None) == ls["amount_deposit"] and (sc["amount_monthly"] or None) == ls["amount_monthly"]}
    traded_ok = (sorted(cand["traded"]) if cand["traded"] is not None else None) == \
                (sorted(sample["traded"]) if sample["traded"] is not None else None)
    return {"wrong": wrong, "wrong_raw": wrong_raw, "missed": missed, "n_askable": len(askable),
            "fields": fields, "traded_ok": traded_ok, "traded_got": cand["traded"], "dropped": cand["dropped"]}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    url, model, label, which, evidence, verify = R2.DEFAULT_URL, "model", "v1", "dev", True, False
    verify_dropped: list[tuple] = []
    for flag in ("--url", "--model", "--label", "--set", "--no-evidence-filter", "--verify"):
        if flag in argv:
            i = argv.index(flag)
            if flag == "--no-evidence-filter":
                evidence = False; argv = argv[:i] + argv[i + 1:]; continue
            if flag == "--verify":
                verify = True; argv = argv[:i] + argv[i + 1:]; continue
            v = argv[i + 1]
            url = v if flag == "--url" else url
            model = v if flag == "--model" else model
            label = v if flag == "--label" else label
            which = v if flag == "--set" else which
            argv = argv[:i] + argv[i + 2:]
    global S
    S = SETS[which]
    print(f"=== R2 측정 · 모델 {model} · 프롬프트 {label} · 표본 {which} {len(S)}문장 · 근거 필터 {'켬' if evidence else '끔'}"
          f" · 거래 은행 재확인 {'켬' if verify else '끔'} ===\n")
    results, secs, n_label = [], [], 0
    for s in S:
        group = s["scope"]["group"] or "bank"
        keys, _ = plan_keys(group, s["scope"]["banks"], s["scope"]["kinds"])
        if label == "hybrid":
            # 두 호출 — 조건 답·스코프는 v3(짧은 프롬프트 · 답이 정확), 은행 목록은 v5(은행마다 역할 · 거래/보고싶음이 안 섞임)
            parsed, sec, err = R2.call(s["text"], url, system=R2.PROMPTS["v3"], schema=R2.SCHEMAS["v3"])
            parsed5, sec5, err5 = R2.call(s["text"], url, system=R2.PROMPTS["v5"], schema=R2.SCHEMAS["v5"])
            sec += sec5
            if not err and not err5:
                parsed = {**parsed, "banks": parsed5.get("banks", []),
                          "says_no_bank_relations": parsed5.get("says_no_bank_relations", False)}
                parsed.pop("traded", None); parsed["scope"] = {**parsed["scope"]}
                parsed["scope"].pop("banks", None)
            err = err or err5
        else:
            parsed, sec, err = R2.call(s["text"], url, system=R2.PROMPTS[label], schema=R2.SCHEMAS.get(label))
        if err:
            secs.append(sec)
            results.append({"n": s["n"], "error": err}); print(f"  {s['n']:>2}  실패 {sec:5.1f}s  {err}"); continue
        cand = R2.to_candidates(parsed, keys or None, s["text"] if evidence else None)
        # 방안 ② — 거래 은행 후보를 한 은행씩 두 번째 호출로 대조한다 (`prereg-28` §7). 뺀 것을 정답/오답으로 센다
        if verify and cand["traded"]:
            kept = []
            for b in cand["traded"]:
                ok_b, vs = R2.verify_traded(s["text"], b, url); sec += vs
                if ok_b is False:
                    verify_dropped.append((s["n"], b, b in (s["traded"] or [])))   # (문장, 은행, 정답이었나)
                else:
                    kept.append(b)
            cand["traded"] = kept
        secs.append(sec)
        r = score(s, cand, keys or None); r["n"] = s["n"]; r["value"] = value_axis(s); results.append(r)
        n_label += r["n_askable"]
        flag = "  " if not r["wrong_raw"] else ("✗ " if r["wrong"] else "△ ")
        print(f"  {s['n']:>2} {flag}{sec:5.1f}s  틀림 화면 {len(r['wrong'])} · 원출력 {len(r['wrong_raw'])} · 빠짐 {len(r['missed'])} · "
              f"스코프 {sum(r['fields'].values())}/5 · 거래 {'○' if r['traded_ok'] else '×'}"
              + (f"   ← {r['wrong_raw']}" if r["wrong_raw"] else ""))
    ok = [r for r in results if "error" not in r]
    wrong = sum(len(r["wrong"]) for r in ok); missed = sum(len(r["missed"]) for r in ok)
    wrong_raw = sum(len(r["wrong_raw"]) for r in ok)
    # 필터가 무엇을 걸렀나 — 근거 없음으로 걸린 것 중 **오답이었던 것**과 **정답이었던 것**(억울하게 걸린 것)
    ev_dropped = [(r["n"], d) for r in ok for d in r["dropped"] if d.get("why") == "근거없음"]
    by_n = {s["n"]: s for s in S}
    ev_bad = sum(1 for n, d in ev_dropped if by_n[n]["answers"].get(d["key"]) != d["value"] and (by_n[n].get("also_ok") or {}).get(d["key"]) != d["value"])
    ev_good = len(ev_dropped) - ev_bad
    fields = {f: sum(r["fields"][f] for r in ok) for f in ("권역", "은행", "상품군", "기간", "금액")}
    traded = sum(r["traded_ok"] for r in ok)
    # 번호로 찾는다 — TEST 표본은 101 부터라 순번이 아니다 (첫 TEST 실행이 여기서 죽었다 · `prereg-28` §6)
    reductions = [r["value"]["감소"] for r in ok if by_n[r["n"]]["answers"] or by_n[r["n"]]["traded"] is not None]
    print("\n" + "-" * 80)
    print(f"  잘못 채운 답   화면 {wrong} (필터 뒤 · 관문은 0) · 원출력 {wrong_raw} (모델이 낸 것 전부)")
    print(f"  근거 필터      걸러낸 오답 {ev_bad} · 걸러낸 정답(억울) {ev_good}")
    print(f"  빠뜨린 답     {missed} / 물을 수 있는 라벨 {n_label} ({missed / n_label * 100:.0f}%)")
    print(f"  스코프 칸      " + " · ".join(f"{f} {v}/{len(ok)}" for f, v in fields.items())
          + f"  → {sum(fields.values()) / (5 * len(ok)) * 100:.0f}%")
    # (다) 틀린 은행 — 라벨에 없는 은행을 거래 목록에 넣은 수 (`prereg-28` §2)
    wrong_banks = sum(1 for r in ok for b in (r.get("traded_got") or []) if b not in (by_n[r["n"]]["traded"] or []))
    print(f"  거래 은행     일치 {traded}/{len(ok)} · **틀린 은행 넣음 {wrong_banks}** (관문 0)")
    if verify:
        vb = sum(1 for _, _, was_right in verify_dropped if not was_right); vg = len(verify_dropped) - vb
        print(f"  재확인 호출    뺀 오답 {vb} · 뺀 정답(억울) {vg}")
    print(f"  지연         중앙값 {statistics.median(secs):.1f}s · 최대 {max(secs):.1f}s")
    print(f"  가치(라벨 기준) 답이 있는 문장 {len(reductions)}개 · 질문 감소 중앙값 {statistics.median(reductions) if reductions else 0} · "
          f"합 {sum(reductions)}")
    print(f"  JSON 실패     {len(S) - len(ok)}")
    out = C.OUT_DIR / f"r2_measure_{model}_{label}_{which}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"model": model, "prompt": label, "set": which, "evidence_filter": evidence,
                               "ev_dropped_bad": ev_bad, "ev_dropped_good": ev_good,
                               "n": len(S), "wrong": wrong, "wrong_raw": wrong_raw, "missed": missed,
                               "n_label": n_label, "fields": fields, "traded_ok": traded,
                               "latency_median": statistics.median(secs), "latency_max": max(secs),
                               "value_reductions": reductions, "json_fail": len(S) - len(ok),
                               "per_sentence": [{k: v for k, v in r.items() if k != "value"} | {"value": r.get("value")}
                                                for r in results]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out.relative_to(C.REPO_ROOT)} (git 제외 · 문장 원문 없음)")


if __name__ == "__main__":
    main()
