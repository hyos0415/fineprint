# -*- coding: utf-8 -*-
"""금융감독원 '금융상품한눈에' API 의 **금융회사 조회**를 받아 기관 정보를 모은다 (A7 · 이슈 #58).

왜 따로 받나
    상품 공시(`baseList`)에는 홈페이지 URL(`homp_url`)·대표전화(`cal_tel`)가 **없다**
    (`decisions/0037` — `data/raw` 전체에서 `homp_url` 이 있는 파일 0개). 두 값은
    `companySearch.json` 에 있고, F3(홈페이지 링크·대표전화)의 재료가 된다.

무엇을 안 하나
    - 없는 기관을 웹 검색으로 채우지 않는다 (추측 금지 · `0016`)
    - URL 에 추적 파라미터를 붙이지 않는다 (`0037` — 링크만 주고 수익화하지 않는다)
    - 화면은 만들지 않는다 — 이 파일은 수집과 대조까지다

키 로딩·페이지 순회·User-Agent 는 `fetch_finlife.py` 를 그대로 쓴다. 원본은 `data/raw/` 에
저장하고 git 에 커밋하지 않는다. 문서에 적는 것은 `--check` 의 집계다.

사용법:
    python src/ingest/fetch_companies.py --group bank
    python src/ingest/fetch_companies.py --group savingsbank
    python src/ingest/fetch_companies.py --check            (두 권역 최신 파일을 상품 스냅샷과 대조)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_finlife import GROUPS, OUT_DIR, REPO_ROOT, fetch_page, load_api_key  # noqa: E402

ENDPOINT = "companySearch"
# 상품 스냅샷 파일명 규칙 (`fetch_finlife.py`) — 은행권은 권역 접미사가 없다
PRODUCT_KINDS = ("deposit", "saving")


def fetch(group: str) -> Path:
    group_no = GROUPS[group]
    api_key = load_api_key()
    print(f"[fetch] {ENDPOINT} (topFinGrpNo={group_no} [{group}], auth=***)")
    first = fetch_page(ENDPOINT, api_key, group_no, 1)
    max_page = int(first.get("max_page_no", 1))
    total = int(first.get("total_count", 0))
    base, opts = list(first.get("baseList", [])), list(first.get("optionList", []))
    for page in range(2, max_page + 1):
        time.sleep(0.3)
        r = fetch_page(ENDPOINT, api_key, group_no, page)
        base.extend(r.get("baseList", []))
        opts.extend(r.get("optionList", []))
    if len(base) != total:
        print(f"[warn] 수집 {len(base)}건 != total_count {total} — 그대로 기록한다")
    fetched_at = datetime.now(timezone.utc).astimezone()
    snapshot = {
        "endpoint": ENDPOINT, "group": group, "topFinGrpNo": group_no,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "total_count": total, "max_page_no": max_page, "collected_count": len(base),
        "baseList": base, "optionList": opts,      # optionList 는 영업 지역 (area_cd · area_nm · exis_yn)
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"company_{group}_{fetched_at:%Y%m%d}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] {len(base)}곳 → {out.relative_to(REPO_ROOT)} (git 제외)")
    return out


def latest(pattern: str, exclude: tuple[str, ...] = ()) -> Path | None:
    """이름 순 마지막 파일. `exclude` 중 하나가 이름에 들면 뺀다 — 은행권 상품 파일은 권역
    접미사가 없어서 `deposit_*` 가 `deposit_savingsbank_*` 까지 잡는다 (첫 실행에서 실제로 잡았다)."""
    files = sorted(f for f in OUT_DIR.glob(pattern) if not any(x in f.name for x in exclude))
    return files[-1] if files else None


def load_directory(group: str) -> dict[str, dict]:
    """최신 회사 목록 — `{fin_co_no: 행}`."""
    path = latest(f"company_{group}_*.json")
    if path is None:
        raise SystemExit(f"{group} 회사 목록이 없다 — 먼저 --group {group} 으로 받는다")
    rows = json.loads(path.read_text(encoding="utf-8"))["baseList"]
    return {r["fin_co_no"]: r for r in rows}


def product_companies(group: str) -> dict[str, str]:
    """최신 상품 스냅샷에 나오는 기관 — `{fin_co_no: kor_co_nm}`. 예금·적금을 합친다."""
    suffix = "" if group == "bank" else f"_{group}"
    out: dict[str, str] = {}
    for kind in PRODUCT_KINDS:
        others = tuple(g for g in GROUPS if g != group) if group == "bank" else ()
        path = latest(f"{kind}{suffix}_*.json", exclude=others)
        if path is None:
            continue
        for b in json.loads(path.read_text(encoding="utf-8"))["baseList"]:
            out[b["fin_co_no"]] = b["kor_co_nm"]
    return out


def check(group: str) -> dict:
    """`prereg-20` §3 의 P1~P5 를 센다. **집계만** 낸다 — 개별 값은 문서에 적지 않는다."""
    directory = load_directory(group)
    products = product_companies(group)
    matched = {co: directory[co] for co in products if co in directory}
    missing = sorted(products[co] for co in products if co not in directory)
    with_url = [r for r in matched.values() if (r.get("homp_url") or "").strip()]
    with_tel = [r for r in matched.values() if (r.get("cal_tel") or "").strip()]
    name_diff = sorted((products[co], matched[co].get("kor_co_nm", "")) for co in matched
                       if products[co] != matched[co].get("kor_co_nm", ""))
    # P5 는 두 갈래로 센다 — 첫 수집(2026-09-04)에서 둘이 다 나왔고 F3 에서 다르게 다뤄야 한다.
    # 스킴이 없으면 그대로는 링크가 안 되고, 파라미터는 API 가 준 값이라 우리가 떼지 않는다
    no_scheme = sorted(r["kor_co_nm"] for r in with_url
                       if not r["homp_url"].strip().lower().startswith(("http://", "https://")))
    has_query = sorted(r["kor_co_nm"] for r in with_url if "?" in r["homp_url"])
    bad_url = sorted(set(no_scheme) | set(has_query))
    n = len(products)
    pct = lambda k: round(k / len(matched) * 100, 1) if matched else 0.0   # noqa: E731
    res = {
        "권역": group, "상품 기관": n, "회사 목록": len(directory),
        "P1 짝": f"{len(matched)}/{n}", "P1 빠진 기관": missing,
        "P2 홈페이지": f"{len(with_url)}/{len(matched)} ({pct(len(with_url))}%)",
        "P3 전화": f"{len(with_tel)}/{len(matched)} ({pct(len(with_tel))}%)",
        "P4 이름 불일치": name_diff,
        "P5 형태 위반": bad_url, "P5 스킴 없음": no_scheme, "P5 파라미터 있음": has_query,
    }
    print(f"\n■ {group} — 상품 기관 {n}곳 · 회사 목록 {len(directory)}곳")
    print(f"    P1 짝           {res['P1 짝']}   빠진 기관 {len(missing)}개 {missing if missing else ''}")
    print(f"    P2 홈페이지      {res['P2 홈페이지']}")
    print(f"    P3 전화         {res['P3 전화']}")
    print(f"    P4 이름 불일치   {len(name_diff)}개 {name_diff if name_diff else ''}")
    print(f"    P5 형태 위반     {len(bad_url)}개 — 스킴 없음 {len(no_scheme)} "
          f"{no_scheme if no_scheme else ''} · 파라미터 있음 {len(has_query)} "
          f"{has_query if has_query else ''}")
    return res


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if argv == ["--check"]:
        for g in GROUPS:
            check(g)
        return
    if len(argv) == 2 and argv[0] == "--group" and argv[1] in GROUPS:
        fetch(argv[1])
        return
    raise SystemExit("사용법: python src/ingest/fetch_companies.py --group bank|savingsbank · --check")


if __name__ == "__main__":
    main()
