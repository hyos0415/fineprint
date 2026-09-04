# -*- coding: utf-8 -*-
"""이번 달 수집이 다 들어왔나 — 판정 (H2 · 이슈 #65 · `prereg-23` §3).

왜 필요하나
    저축은행 공시는 기관마다 며칠에 걸쳐 들어온다(8월: 20일~24일 · 21일 이후 첫 등장 기관 10곳).
    언제 받아야 다 들어온 것인지 모르면 **반쯤 들어온 달을 "이번 달" 로 쓴다** — 그 위의 지표는
    다음 달과 비교할 수 없고 화면에는 아직 안 올라온 기관의 상품이 조용히 없다.

규칙 (`prereg-23` §3 — 9월 공시 전에 적었고 9월에 검증한다. 결과를 보고 고치지 않는다)
    판단 불가   직전 달 스냅샷이 없다 — 재료만 낸다
    완료       기관 수 ≥ 직전 달  그리고  상품 수 ≥ 직전 달의 95%  그리고  정착 ≥ 2일
    아직       그 밖에 — 걸린 조건과 직전 달에 있었는데 없는 기관을 이름으로 낸다

    정착(settle) = 수집일 − 가장 늦은 dcls_strt_day. 하루 건너 들어온 8월(20·21·22·24)을 보고 2일로 놨다.
    회사 목록(companySearch)과의 차이는 판정에 넣지 않고 이름으로만 보인다 — 상호저축은행중앙회처럼
    상품이 없는 것이 정상인 기관이 있어 수로 비교하면 늘 틀린다.

무엇을 안 하나
    - 다시 받지 않는다. 월 1회짜리라 사람이 부른다 (`collection-pipeline.md` §4)
    - 스케줄러를 붙이지 않는다 (H1 의 일)

사용법:
    python src/ingest/check_collection.py --group savingsbank
    python src/ingest/check_collection.py --group bank --date 20260824     (특정 수집일의 스냅샷으로)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_finlife import GROUPS, OUT_DIR, REPO_ROOT  # noqa: E402

KINDS = ("deposit", "saving")
SETTLE_DAYS = 2          # `prereg-23` §3 — 결과를 보고 고치지 않는다
PRODUCT_FLOOR = 0.95     # 같은 곳


def _suffix(group: str) -> str:
    return "" if group == "bank" else f"_{group}"


def snapshot_dates(group: str) -> list[str]:
    """예금·적금이 **둘 다** 있는 수집일. 은행권 파일은 권역 접미사가 없어 저축은행 것을 걸러낸다."""
    pat = re.compile(rf"^(deposit|saving){re.escape(_suffix(group))}_(\d{{8}})\.json$")
    found: dict[str, set[str]] = {}
    for f in OUT_DIR.glob("*.json"):
        m = pat.match(f.name)
        if m:
            found.setdefault(m.group(2), set()).add(m.group(1))
    return sorted(d for d, kinds in found.items() if kinds == set(KINDS))


def load_snapshot(group: str, stamp: str) -> dict:
    """한 수집일의 예금+적금 — `{month, institutions{code: name}, products, starts{day: n}, fetch}`."""
    inst: dict[str, str] = {}
    starts: dict[str, int] = {}
    months: dict[str, int] = {}
    n = 0
    for kind in KINDS:
        d = json.loads((OUT_DIR / f"{kind}{_suffix(group)}_{stamp}.json").read_text(encoding="utf-8"))
        for b in d.get("baseList", []):
            n += 1
            inst[b["fin_co_no"]] = b["kor_co_nm"]
            starts[b.get("dcls_strt_day") or "-"] = starts.get(b.get("dcls_strt_day") or "-", 0) + 1
            months[b.get("dcls_month") or "-"] = months.get(b.get("dcls_month") or "-", 0) + 1
    month = max(months, key=months.get) if months else "-"
    return {"stamp": stamp, "month": month, "months": months, "institutions": inst,
            "products": n, "starts": dict(sorted(starts.items()))}


def directory(group: str) -> dict[str, str]:
    files = sorted(OUT_DIR.glob(f"company_{group}_*.json"))
    if not files:
        return {}
    return {r["fin_co_no"]: r["kor_co_nm"]
            for r in json.loads(files[-1].read_text(encoding="utf-8")).get("baseList", [])}


def _days(a: str, b: str) -> int:
    da, db = date(int(a[:4]), int(a[4:6]), int(a[6:8])), date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    return (da - db).days


def prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[4:6])
    return f"{y - 1}12" if m == 1 else f"{y}{m - 1:02d}"


def judge(group: str, stamp: str | None = None) -> dict:
    dates = snapshot_dates(group)
    if not dates:
        raise SystemExit(f"{group} 스냅샷이 없다 (예금·적금 둘 다 있어야 한다)")
    stamp = stamp or dates[-1]
    if stamp not in dates:
        raise SystemExit(f"{group} {stamp} 스냅샷이 없다 — 있는 날짜: {dates}")
    now = load_snapshot(group, stamp)
    # 직전 달 — 그 달의 **가장 늦은** 수집일 (가장 다 들어온 것)
    prev_stamps = [d for d in dates if d < stamp and load_snapshot(group, d)["month"] == prev_month(now["month"])]
    prev = load_snapshot(group, prev_stamps[-1]) if prev_stamps else None
    last_start = max((d for d in now["starts"] if d != "-"), default=None)
    settle = _days(stamp, last_start) if last_start else None
    dir_ = directory(group)
    only_dir = sorted(dir_[c] for c in dir_ if c not in now["institutions"])
    only_now = sorted(now["institutions"][c] for c in now["institutions"] if c not in dir_)

    res = {"권역": group, "수집일": stamp, "공시월": now["month"], "기관": len(now["institutions"]),
           "상품": now["products"], "시작일": now["starts"], "마지막 시작일": last_start, "정착_일": settle,
           "회사 목록에만": only_dir, "스냅샷에만": only_now,
           "직전 달": None, "판정": "판단 불가", "걸린 조건": [], "빠진 기관": []}
    if prev is None:
        res["사유"] = f"직전 달({prev_month(now['month'])}) 스냅샷이 없다 — 재료만 낸다"
        return res
    res["직전 달"] = {"수집일": prev["stamp"], "기관": len(prev["institutions"]), "상품": prev["products"]}
    hit = []
    if len(now["institutions"]) < len(prev["institutions"]):
        hit.append(f"기관 {len(now['institutions'])} < 직전 달 {len(prev['institutions'])}")
    if now["products"] < PRODUCT_FLOOR * prev["products"]:
        hit.append(f"상품 {now['products']} < 직전 달 {prev['products']} 의 {PRODUCT_FLOOR:.0%}")
    if settle is None or settle < SETTLE_DAYS:
        hit.append(f"정착 {settle}일 < {SETTLE_DAYS}일")
    res["걸린 조건"] = hit
    res["빠진 기관"] = sorted(prev["institutions"][c] for c in prev["institutions"] if c not in now["institutions"])
    res["판정"] = "완료" if not hit else "아직"
    return res


def show(res: dict) -> None:
    print(f"\n■ {res['권역']} · 수집일 {res['수집일']} · 공시월 {res['공시월']} → **{res['판정']}**")
    if res.get("사유"):
        print(f"    {res['사유']}")
    print(f"    기관 {res['기관']}곳 · 상품 {res['상품']}개 · 시작일 {res['시작일']} · "
          f"마지막 시작일 {res['마지막 시작일']} · 정착 {res['정착_일']}일")
    if res["직전 달"]:
        p = res["직전 달"]
        print(f"    직전 달 {p['수집일']} — 기관 {p['기관']}곳 · 상품 {p['상품']}개")
    for c in res["걸린 조건"]:
        print(f"    걸림  {c}")
    if res["빠진 기관"]:
        print(f"    직전 달에 있었는데 없는 기관 {len(res['빠진 기관'])}곳: {res['빠진 기관']}")
    if res["회사 목록에만"]:
        print(f"    회사 목록에만 있는 기관 {len(res['회사 목록에만'])}곳: {res['회사 목록에만']}  (판정에 안 넣는다)")
    if res["스냅샷에만"]:
        print(f"    스냅샷에만 있는 기관: {res['스냅샷에만']}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    groups, stamp = list(GROUPS), None
    for flag in ("--group", "--date"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            if flag == "--group":
                if argv[i + 1] not in GROUPS:
                    raise SystemExit(f"--group 은 {list(GROUPS)} 중 하나다")
                groups = [argv[i + 1]]
            else:
                stamp = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    if argv:
        raise SystemExit("사용법: python src/ingest/check_collection.py [--group bank|savingsbank] [--date YYYYMMDD]")
    out = [judge(g, stamp) for g in groups]
    for r in out:
        show(r)
    path = OUT_DIR / f"collection_check_{out[-1]['수집일']}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {path.relative_to(REPO_ROOT)} (git 제외)")


if __name__ == "__main__":
    main()
