# -*- coding: utf-8 -*-
"""금융감독원 '금융상품한눈에' API에서 은행권 상품 스냅샷을 수집한다.

finance_verifier `src/ingest/fetch_finlife.py`를 재사용하고 세 가지만 바꿨다.
  1) 상품군을 인자로 받는다 (deposit | saving)
  2) 전체 페이지를 순회한다 (선행 스크립트는 1페이지만 받았다)
  3) 금융회사 권역을 인자로 받는다 (bank | savingsbank) — 홀드아웃 수집용

표준 라이브러리만 쓴다. 원본 스냅샷은 `data/raw/`에 저장하며 git에 커밋하지 않는다
(`.gitignore` 참고 — API로 제공되는 데이터를 GitHub에 재배포하지 않는다).

권역을 인자로 둔 이유는 **홀드아웃**이다(`docs/spec/prereg-03-extraction.md` §2).
규칙 파서는 은행권 253행을 여덟 라운드 보면서 만들어졌으므로 같은 집합에서 비교하면
과적합된 baseline과 겨루는 것이다. 저축은행(`030300`)은 같은 공시 체계·같은 상품 유형인데
기관이 전혀 다르다 — 표기 습관이 다를 것이 기대되고, 그게 홀드아웃의 요건이다.

파일명은 권역에 따라 다르다. 은행권은 기존 스냅샷(`deposit_20260824.json`)을 그대로
읽을 수 있도록 권역 이름을 붙이지 않고, 나머지 권역은 붙인다.

    은행권      data/raw/deposit_20260824.json
    저축은행    data/raw/deposit_savingsbank_20260825.json

사용법:
    python src/ingest/fetch_finlife.py deposit
    python src/ingest/fetch_finlife.py saving --group savingsbank
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = {
    "deposit": "depositProductsSearch",   # 정기예금
    "saving": "savingProductsSearch",     # 적금
}
BASE_URL = "https://finlife.fss.or.kr/finlifeapi/{endpoint}.json"
# 금융회사 권역 코드. 이름 없이 코드만 두면 나중에 읽을 수 없다.
GROUPS = {
    "bank": "020000",          # 은행 (개발 집합 — 규칙 파서가 이미 본 데이터)
    "savingsbank": "030300",   # 저축은행 (홀드아웃)
}
DEFAULT_GROUP = "bank"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "raw"
ENV_CANDIDATES = [
    REPO_ROOT / ".env",
    REPO_ROOT.parent / "finance_verifier" / ".env",
]


def load_api_key() -> str:
    """FINLIFE_API_KEY를 읽는다. 키 값은 어디에도 출력하지 않는다."""
    for env_path in ENV_CANDIDATES:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*FINLIFE_API_KEY\s*=\s*(.+)\s*$", line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("FINLIFE_API_KEY를 찾지 못했다 (.env 확인)")


def fetch_page(endpoint: str, api_key: str, group_no: str, page_no: int) -> dict:
    url = BASE_URL.format(endpoint=endpoint) + "?" + urllib.parse.urlencode(
        {"auth": api_key, "topFinGrpNo": group_no, "pageNo": page_no}
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
    result = payload.get("result", {})
    if result.get("err_cd") != "000":
        raise SystemExit(f"API 오류: err_cd={result.get('err_cd')} {result.get('err_msg')}")
    return result


USAGE = (f"사용법: python fetch_finlife.py {{{'|'.join(ENDPOINTS)}}} "
         f"[--group {{{'|'.join(GROUPS)}}}]")


def parse_args(argv: list[str]) -> tuple[str, str]:
    group = DEFAULT_GROUP
    if "--group" in argv:
        i = argv.index("--group")
        if i + 1 >= len(argv) or argv[i + 1] not in GROUPS:
            raise SystemExit(USAGE)
        group = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1 or argv[0] not in ENDPOINTS:
        raise SystemExit(USAGE)
    return argv[0], group


def main() -> None:
    kind, group = parse_args(sys.argv[1:])
    endpoint = ENDPOINTS[kind]
    group_no = GROUPS[group]
    api_key = load_api_key()

    print(f"[fetch] GET {BASE_URL.format(endpoint=endpoint)} "
          f"(topFinGrpNo={group_no} [{group}], auth=***)")

    first = fetch_page(endpoint, api_key, group_no, 1)
    max_page = int(first.get("max_page_no", 1))
    total = int(first.get("total_count", 0))
    base_list, option_list = list(first.get("baseList", [])), list(first.get("optionList", []))
    print(f"[fetch] total_count={total} max_page_no={max_page} (page 1: {len(base_list)}건)")

    for page in range(2, max_page + 1):
        time.sleep(0.3)
        result = fetch_page(endpoint, api_key, group_no, page)
        base_list.extend(result.get("baseList", []))
        option_list.extend(result.get("optionList", []))
        print(f"[fetch] page {page}: 누적 {len(base_list)}건")

    if len(base_list) != total:
        print(f"[warn] 수집 {len(base_list)}건 != total_count {total} — 스냅샷에 그대로 기록한다")

    fetched_at = datetime.now(timezone.utc).astimezone()
    snapshot = {
        "endpoint": endpoint,
        "product_kind": kind,
        "group": group,
        "topFinGrpNo": group_no,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "total_count": total,
        "max_page_no": max_page,
        "collected_count": len(base_list),
        "baseList": base_list,
        "optionList": option_list,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if group == DEFAULT_GROUP else f"_{group}"
    out_path = OUT_DIR / f"{kind}{suffix}_{fetched_at:%Y%m%d}.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] saved -> {out_path.relative_to(REPO_ROOT)} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
