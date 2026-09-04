# -*- coding: utf-8 -*-
"""비교 리포트 — 상품 하나의 "왜 이 금리인가" 를 숫자 칸까지 코드가 채운다.

이 파일이 채우는 자리
    `problem.md` §3 **내놓는 것**이 약속한 화면이 이것이다.

        1위  A은행 청년적금      내가 받을 금리 4.2%   (기본 3.0 + 우대 1.2)
               채운 조건    급여이체 +0.5 · 카드실적 +0.7
               못 채운 조건  카드실적 (이 은행 카드를 써야 함)
               ⚠ 광고 최고금리 3.8% 중 0.3%p 는 근거가 공시에 없음

    지금 화면(`ask_loop` 최종)은 `2.54~5.92%  [비대면]  남은 1개  주의:미응답` 이다.
    **약속한 칸 14개 중 4개가 없었다** — 조건별 %p 두 개, 못 채운 이유(공시 문구
    원문), 배타 그룹이 왜 걸렸나. 2026-08-31 재고 조사에서 상위 10개 상품의 추출
    항목 27개 중 **공시 문구가 화면에 있는 것이 0개**였고 화면 1,590자에 `%p` 가
    0회였다.

    **원천에는 다 있었다** (추출 항목 242개 중 `rate` 238개 · `evidence` 242개).
    `evaluate()` 가 `met`/`unmet`/`unknown` 을 이름만 남기면서 버렸다. 그 자리에
    `why` 를 더했고(`calculate.condition_detail`), 이 파일이 그것을 읽는다.

무엇을 하나
    build()    상품 하나 → 리포트 객체 (숫자는 전부 계산된 값. 새로 계산하지 않는다)
    render()   리포트 객체 → 텍스트 (F4 가 오면 같은 객체를 HTML 로 렌더한다)

무엇을 **안** 하나
    - **LLM 을 쓰지 않는다.** 숫자 칸은 코드가 채운다 (`problem.md` §7). 서술 문단은
      F2(R4)의 일이고 그때도 **숫자 칸은 이미 채워진 상태**로 넘긴다
    - **금리를 다시 계산하지 않는다.** `evaluate()` 가 낸 값을 그대로 쓴다. 리포트가
      자기 산수를 하면 화면과 계산기가 서로 다른 숫자를 말할 수 있다
    - **합이 안 맞는 것을 맞춰 보이지 않는다.** 조건별 %p 의 단순 합은 실제 상승분과
      다를 수 있다(배타 그룹 · 상품 상한 `cap`). **그 차이를 적는다**

사용법
    python src/analysis/calculate.py 20260826 --term 12 --report 3
    python src/analysis/calculate.py 20260825 --group savingsbank --report 2 \
        --state 급여_연금이체 --prefs 영업점=많이
"""
from __future__ import annotations

import calculate as C

EPS = 0.005          # %p 비교 허용치. 소수 둘째 자리에서 갈린다


def _pp(v: float) -> str:
    return f"{v:+.2f}%p"


def _sum(items: list[dict]) -> float:
    """조건별 %p 의 **단순 합**. 실제 상승분과 다를 수 있다 — 그게 요점이다."""
    return round(sum(i["pp"] for i in items), 4)


def build(s: dict, rank: int, prefs: dict | None = None,
          amounts: dict | None = None) -> dict:
    """상품 하나의 리포트 객체.

    **숫자는 전부 `evaluate()` 가 낸 값이다.** 여기서 하는 산수는 두 가지뿐이고
    둘 다 이미 있는 값의 차다 — 조건이 올린 폭(`raw_lo - base`, `raw_hi - raw_lo`)과
    단순 합과의 차이. 그 외에는 옮겨 적기만 한다.

    `amounts` (E4 · `prereg-25`) 가 있으면 **예상 이자**(원)를 `이자` 칸에 담는다 — 그 산수는
    `calculate.interest()` 한 곳이고 CLI 텍스트와 웹이 같은 칸을 읽는다. 없으면 None 이다.
    """
    why = s.get("why") or {"met": [], "unmet": [], "unknown": []}
    base = s["base"]
    # 상한을 먹기 **전** 값으로 계단을 쓴다. `gross_*` 는 이미 상한이 적용돼 있어서
    # "조건이 얼마를 올렸나" 를 그것으로 쓰면 상한 때문에 줄어든 몫이 조건 탓이 된다
    raw_lo = s.get("raw_lo", s["gross_lo"])
    raw_hi = s.get("raw_hi", s["gross_hi"])
    met_up = round(raw_lo - base, 4)             # 확실히 받는 몫 (보수 · `0022`)
    unknown_up = round(raw_hi - raw_lo, 4)       # 불확실한 몫 (낙관 − 보수)
    steps = {
        "기본금리": base,
        "확실히 받는 우대": met_up,
        "불확실한 우대": unknown_up,
        "세전 범위": (raw_lo, raw_hi),
        "공시 최고금리": s["disclosed_max"],
        "상한에 걸렸나": bool(s.get("clamped")),
        "세전 최종": (s["gross_lo"], s["gross_hi"]),
        "세율": s["tax_rate"],
        "세후 범위": (s["net_lo"], s["net_hi"]),
    }
    # **합이 안 맞는 자리** — 배타 그룹(`0022`)이면 보수 쪽에서 한 그룹의 최댓값만
    # 세고, 상품 상한(`cap`)이면 합계가 잘린다. 숨기면 사용자가 산수를 못 따라온다.
    #
    # **두 칸의 이름을 "채운/안 답한" 으로 쓰면 안 된다.** 실측에서 걸렸다 —
    # `met` 에 배타 그룹 두 항목이 들어간 상품에서 `안 답한 조건` 칸이 조건별 합보다
    # 1.00%p 컸다. 그 몫은 **답한 조건인데 중복 적용 여부가 불명한 것**이고, 코드가
    # 그것을 낙관(`hi`) 쪽에만 넣기 때문에 여기 섞인다. 그래서 칸 이름을 계산이
    # 실제로 하는 일(확실 / 불확실)로 맞추고, 차이의 출처를 아래에 적는다.
    naive_met, naive_unknown = _sum(why["met"]), _sum(why["unknown"])
    dedupe = round(naive_met - met_up, 4)         # 보수 쪽에서 깎인 몫
    mismatch = []
    if abs(dedupe) > EPS:
        mismatch.append({"칸": "확실히 받는 우대", "단순합": naive_met, "실제": met_up,
                         "출처": None})
    if abs(naive_unknown - unknown_up) > EPS:
        # 차이가 위에서 깎인 몫과 같으면 **그것이 여기 들어온 것**이다 — 정확히 짚는다
        same = abs((unknown_up - naive_unknown) - dedupe) <= EPS
        mismatch.append({"칸": "불확실한 우대", "단순합": naive_unknown,
                         "실제": unknown_up,
                         "출처": ("위에서 깎인 중복 적용 불명분이 여기 들어온 것이다"
                                  if same else None)})
    order = {
        "rank": rank,
        "기준": "세후 가중합 순" if prefs else "세후 최대 금리 순",
        # **결정 번호를 사용자 화면에 쓰지 않는다** (F5 · 이슈 #45). `0017`·`0030` 은
        # 우리 기록의 좌표이고, 사용자에게는 *무엇을 기준으로 세웠나* 만 필요하다
        "근거": ("답한 선호를 금리 차이로 옮겨 더한 값 순" if prefs
                else "조건을 다 채웠을 때 받을 수 있는 금리 순"),
        "조정": s.get("_adj"),
        "조정 사유": s.get("_why") or [],
        "선호밖": bool(s.get("_blocked")),
    }
    return {
        "순위": rank,
        "%p 설명": C.PP_NOTE,          # 남기고 설명만 붙이는 낱말 (F5 · 이슈 #45)
        "상품": s["name"],
        "기관": C.org_label(s.get("company") or ""),      # 화면 표기 (F5)
        "채널": s.get("channel") or "",
        # **층은 라벨로 담는다** (F5 · 이슈 #45). 원본 코드는 상품 dict 의 `tier` 에
        # 그대로 있으므로 여기 또 담지 않는다 — 안 읽는 칸은 만들지 않는다(`0039`)
        "층": C.tier_label(s["tier"]),
        "층 설명": s.get("message") or "",
        "계단": steps,
        "합_불일치": mismatch,
        "배타그룹_밴드": bool(s.get("band")),
        "상품상한": s.get("cap"),
        "근거없는_%p": s.get("unexplained_pp") or 0.0,
        "조건": {"채운": why["met"], "못채운": why["unmet"], "안답한": why["unknown"]},
        # **이 금리가 어떤 약속 위에 서 있나** (이슈 #50 · `prereg-17`). 채운 조건 중
        # 시제가 행동·중립인 것 — 사용자가 "하겠다" 고 답한 것들이다. 은행권 확정 50개 중
        # 44개가 여기에 기댄다(T4). 가입 뒤에 하는지는 우리 일이 아니지만, 숫자의 전제를
        # 밝히는 것까지는 우리 일이다
        "전제": [c for c in why["met"] if C.is_commitment(c["type"])],
        "전제_문장": C.PREMISE_NOTE,
        # 예상 이자 — 가입 금액이 있을 때만 (E4 · A18). 세전·세후 둘 다 범위로 담고 3층 판정을 같이 낸다
        "이자": C.interest(s, amounts, C.load_tax()),
        "사유": [{"코드": c, "라벨": C.caveat_label(c), "문장": t}
               for c, t in zip(s.get("caveats") or [], s.get("caveat_text") or [])],
        "정렬": order,
    }


def _conditions(title: str, items: list[dict], tail: str = "") -> list[str]:
    """조건 블록. **공시 문구를 자르지 않는다** (`0027` · `prereg-10`).

    문구를 자르면 조건이 달라진다 — 질문 화면에서 이미 정한 규칙이고 리포트도 같다.
    """
    if not items:
        return [f"    {title}", "      (없음)"]
    out = [f"    {title}{tail}"]
    for it in items:
        head = f"      {it['이름']}  {_pp(it['pp'])}"
        marks = []
        if it["group"]:
            # `배타그룹 g1` 은 우리 말이었다 (F5). 그룹 기호는 남긴다 — 같은 묶음끼리
            # 짝이 보여야 사용자가 "이 둘 중 하나" 를 읽을 수 있다
            marks.append(f"함께 받을 수 없음 ({it['group']})")
        if it["threshold"]:
            marks.append("금액·횟수 조건")
        if marks:
            head += "  (" + " · ".join(marks) + ")"
        out.append(head)
        if it["evidence"]:
            out.append(f'        공시 문구  "{it["evidence"]}"')
    return out


def render(rep: dict) -> str:
    """리포트 객체 → 텍스트. **범위는 범위로 쓴다**(화면 계약 1번 · A1)."""
    st = rep["계단"]
    lo, hi = st["세후 범위"]
    rng = f"{lo:.2f}%" if abs(hi - lo) < 1e-9 else f"{lo:.2f} ~ {hi:.2f}%"
    ch = f"  [{rep['채널']}]" if rep["채널"] else ""
    out = [f"  {rep['순위']}위  {rep['상품']}  —  내가 받을 금리 {rng} (세후){ch}",
           f"        {rep['기관']} · 계산 상태 {rep['층']}"
           + (f" — {rep['층 설명']}" if rep["층 설명"] else "")]

    out.append("")
    out.append("    이 숫자가 어디서 왔나")
    out.append(f"      {rep['%p 설명']}")
    out.append(f"      기본금리                 {st['기본금리']:>7.2f}%")
    out.append(f"      + 확실히 받는 우대        {st['확실히 받는 우대']:>+7.2f}%p")
    out.append(f"      + 불확실한 우대           {st['불확실한 우대']:>+7.2f}%p"
               "   (아직 안 답한 조건 · 중복 적용이 불분명한 몫)")
    p_lo, p_hi = st["세전 범위"]
    p_rng = (f"{p_lo:.2f}%" if abs(p_hi - p_lo) < 1e-9
             else f"{p_lo:.2f} ~ {p_hi:.2f}%")
    out.append(f"      = 세전                   {p_rng}")
    if st["상한에 걸렸나"]:
        out.append(f"        공시 최고금리 {st['공시 최고금리']:.2f}% 로 상한 — "
                   f"세전 최대가 {st['세전 최종'][1]:.2f}% 가 된다")
    r = st["세율"]
    out.append(f"      세금 {r * 100:.1f}% 를 떼면" if r > 1e-9
               else "      비과세 대상이라 세금 0%")
    out.append(f"      = 세후                   {rng}")

    for m in rep["합_불일치"]:
        out.append(f"        ※ {m['칸']} — 조건별 단순 합은 {m['단순합']:+.2f}%p 인데 "
                   f"계산에 들어간 것은 {m['실제']:+.2f}%p 다")
        if m["출처"]:
            out.append(f"           {m['출처']}")
            continue
        why = []
        if rep["배타그룹_밴드"]:
            why.append("한 그룹에서 하나만 받는 조건이 섞여 있다(중복 우대 불가)")
        if rep["상품상한"] is not None:
            why.append(f"상품이 우대분을 {rep['상품상한']:.2f}%p 로 제한한다")
        for w in why or ["이유를 우리가 못 짚었다 — 근거 없음"]:
            out.append(f"           {w}")

    # **최대값이 어떤 가정 위에 서 있는지 말한다.** 계산기는 낙관(`hi`) 쪽에서 배타
    # 그룹을 **믿지 않고 다 더한다**(`0022` — 라벨을 절반쯤 못 믿으므로 밴드로 둔다).
    # 실측에서 이 자리가 크게 벌어졌다 — 웰뱅 라이킷 적금은 세 조건이 모두 같은 그룹인데
    # 낙관 합계가 +12.00%p 였다. 조건 줄에 `배타그룹 g1` 이 붙어 있어도, 최대값 자체가
    # 그 가정 위에 있다는 말이 없으면 사용자는 12%p 를 다 받는 것으로 읽는다.
    if rep["배타그룹_밴드"]:
        out.append("        ※ 위 최대값은 **중복 우대가 다 된다고 본 값**이다 — 같은 "
                   "그룹에서 하나만 받게 되면 최대가 그만큼 낮아진다")
        out.append("           공시가 중복 적용 여부를 분명히 적지 않아 우리가 "
                   "어느 쪽인지 못 정한다")

    if abs(rep["근거없는_%p"]) > 1e-9:
        v = rep["근거없는_%p"]
        if v > 0:
            out.append(f"      ⚠ 광고 최고금리 {st['공시 최고금리']:.2f}% 중 "
                       f"{v:.2f}%p 는 근거가 공시에 없다")
        else:
            out.append(f"      ⚠ 우리가 뽑은 우대가 공시 폭보다 {-v:.2f}%p 많다 — "
                       f"추출이 과다할 수 있다")

    # 예상 이자 (E4 · `prereg-25`) — 원 단위 숫자에는 세전·세후 라벨과 가정 한 줄이 붙는다 (A18)
    it = rep.get("이자")
    if it:
        out.append("")
        out.append(f"    예상 이자   {it['금액_뜻']} {C.won(it['금액'])} · {it['개월']}개월 · {it['방식']}")
        out.append(f"      세전   {_won_range(*it['세전'])}")
        out.append(f"      세후   {_won_range(*it['세후'])}")
        if it["종합과세_문장"]:
            out.append(f"      ⚠ {it['종합과세_문장']}")
        out.append(f"      {it['가정']}")

    # 전제 — 사용자가 "하겠다" 고 답한 조건. **"이미 받는다" 는 이 조건들에는 거짓이다**
    if rep["전제"]:
        out.append("")
        out.append(f"    ※ {rep['전제_문장']}")
        for c in rep["전제"]:
            out.append(f"      · {c['이름']}  ({c['pp']:+.2f}%p)")

    out.append("")
    out += _conditions("채운 조건 — 답한 대로면 받는다", rep["조건"]["채운"])
    out += _conditions("아직 안 답한 조건", rep["조건"]["안답한"],
                       "  — 답하면 범위가 좁아진다")
    out += _conditions("못 채운 조건 — 이 금리는 못 받는다", rep["조건"]["못채운"])

    if rep["사유"]:
        out.append("")
        out.append("    주의")
        for r in rep["사유"]:
            out.append(f'      {r["라벨"]:<20}"{r["문장"]}"')

    o = rep["정렬"]
    out.append("")
    out.append(f"    왜 이 순서인가   {o['기준']} ({o['근거']})")
    if o["선호밖"]:
        out.append("      선호 밖이라 맨 아래다 — " + " · ".join(o["조정 사유"]))
    elif o["조정"]:
        out.append(f"      선호 조정 {o['조정']:+.2f}%p — " + " · ".join(o["조정 사유"]))
        out.append("      조정은 **순서만** 바꾼다 — 위 금리 칸에는 안 들어간다 (A11)")
    return "\n".join(out)


def _won_range(lo: float, hi: float) -> str:
    """원 범위 — 같으면 하나 (A1 과 같은 태도)."""
    return C.won(lo) if lo == hi else f"{C.won(lo)} ~ {C.won(hi)}"


def render_all(scored: list[dict], top: int, prefs: dict | None = None,
               amounts: dict | None = None) -> str:
    """상위 `top` 개의 리포트. 맨 위에 세후 라벨·고지를 붙인다 (A12·A13 · `0035`)."""
    import ask_loop as L                  # 화면 문구는 한 곳에서만 온다
    main = L.ranked(scored, prefs)[:top]
    blocks = [render(build(s, i, prefs, amounts)) for i, s in enumerate(main, 1)]
    return "\n".join(L.screen_header(scored) + [""] + [("\n" + "-" * 96 + "\n").join(blocks)])
