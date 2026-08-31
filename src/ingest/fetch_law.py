# -*- coding: utf-8 -*-
"""세율의 근거 조문을 법제처에서 뽑아 스냅샷을 뜨고, 바뀌었는지 대조한다.

이 파일이 채우는 자리
    `config/tax-2026.json` 이 `"확인_상태": "미확인"` 이었다. 화면의 **모든 세후
    숫자**가 그 위에 서 있다 — `net_lo`/`net_hi` · 확정률 · 폭 평균, 그리고 선호
    가중치의 %p 전부가 세후다(`0030`). 로드맵 E3 는 이것을 E5·E6 의 선행이라고
    적어 뒀는데 **E5·E6 을 먼저 만들었다**(#22 · #24). 그 빚을 갚는 자리다.

    `problem.md` §4 가 *"세율은 매년 바뀐다. 그래서 세율표를 코드에 박지 않고 별도
    파일에 두고 적용 시점을 적는다 — 공시 스냅샷을 날짜로 고정한 것과 같은 방식"*
    이라고 적어 뒀다. 그 "적용 시점" 에 **근거 좌표와 원문**을 같이 박는 것이다.

무엇을 하나 — 2단 확인
    1단  목록 조회(`lawSearch`)로 **법령일련번호·시행일자·공포번호**만 본다.
         개정되면 이 셋이 바뀌므로 이것만으로 "바뀌었나" 가 판정된다
    2단  바뀐 법령만 본문(`lawService`)을 긁어 조문을 뽑고 해시를 대조한다

    실측 크기 차이가 이 구조의 이유다.
        lawSearch    2,505 bytes
        lawService   1,288,895 bytes  (소득세법)      ~515배

무엇을 **안** 하나
    **조문에서 세율을 자동으로 읽지 않는다.** 기계는 "바뀌었다" 까지만 말하고,
    "무엇으로 바뀌었나" 는 사람이 읽어 `config/tax-2026.json` 에 반영한다.

    근거는 조특법 §89의3 이다 — 조합등예탁금 세율이 **가입 시기별로 5%/9% 로 갈리고**
    대상자 조건까지 붙는다. 실제로 이 파일을 만들면서 우리 config 의 `1.4%` 가 틀린
    것을 찾았는데(2025년까지 가입분 비과세 시절의 값이었다), 자동 파싱을 했다면
    **똑같은 종류의 틀린 값을 조용히 만들었을 것**이다. 이 저장소가 *"LLM 이 숫자를
    만들지 못하게 한다"* 로 막은 자리와 같다(`problem.md` §7).

언제 도나 — 매일 돌지 않는다
    **세율이 쓰이는 자리는 하나뿐이다** — 월 1회 공시 수집(`0010`) 뒤의 계산이다.
    그래서 이 검사는 **월간 파이프라인의 첫 태스크**이고, 별도 DAG 를 만들지 않는다
    (로드맵 H1). 세법은 12월 말 공포 → 1월 1일 시행이 기본형이라 1월 수집(1/20 전후)
    에서 잡히고, **최대 20일 지연을 받아들인다.**

사용법:
    python src/ingest/fetch_law.py --check       바뀌었는지만 본다 (2단. 종료코드로 답한다)
    python src/ingest/fetch_law.py --snapshot    스냅샷을 새로 쓴다 (사람이 확인한 뒤)
    python src/ingest/fetch_law.py --show 129    조문 원문을 찍어 본다 (사람이 읽으려고)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES = REPO_ROOT / "config" / "tax-sources.json"
BASE = "https://www.law.go.kr/DRF"
TIMEOUT = 60

# ── 감시 대상 좌표 (`prereg` 없음 — 사실 확인이라 예측할 것이 없다. 이슈 #28)
#
# **핀은 `법령ID` 에 박는다.** `MST`(법령일련번호)는 개정될 때마다 새로 생기므로
# 매번 검색으로 얻고, **그 변화 자체가 "바뀌었다" 신호다.**
#
# `가지` 는 `조문가지번호`다 — `제103조의13` 은 (조문번호 103, 가지 13) 이다.
WATCH = [
    {"법령": "소득세법", "법령ID": "001565", "조": "129", "가지": None,
     "무엇": "이자소득 원천징수세율 14%",
     "config": "일반과세.이자소득세",
     "볼 문구": "그 밖의 이자소득에 대해서는 100분의 14"},
    {"법령": "소득세법", "법령ID": "001565", "조": "14", "가지": None,
     "무엇": "금융소득종합과세 기준금액 2천만원",
     "config": "금융소득종합과세.기준금액_원",
     "볼 문구": "이자소득등의 종합과세기준금액"},
    {"법령": "지방세법", "법령ID": "001649", "조": "103", "가지": "13",
     # **1.4% 는 조문에 없다.** 조문은 "소득세의 100분의 10" 이고 1.4% 는 14×10% 로
     # 유도한 값이다. 그래서 감시하는 문구가 "1.4%" 가 아니라 "100분의 10" 이다.
     "무엇": "개인지방소득세 특별징수 = 원천징수 소득세의 10%",
     "config": "일반과세.지방소득세",
     "볼 문구": "100분의 10에 해당하는 금액"},
    {"법령": "조세특례제한법", "법령ID": "001584", "조": "88", "가지": "2",
     "무엇": "비과세종합저축 — 한도 5천만원 · 일몰 2028-12-31",
     "config": "비과세종합저축",
     "볼 문구": "2028년 12월 31일까지 가입"},
    {"법령": "조세특례제한법", "법령ID": "001584", "조": "89", "가지": "3",
     # 이 조문이 자동 파싱을 금지하는 근거다 — 가입 시기별로 세율이 갈린다.
     "무엇": "조합등예탁금 — 한도 3천만원 · 2026년 가입분 5% · 2027년 이후 9%",
     "config": "세금우대_조합예탁금",
     "볼 문구": "100분의 5"},
]


def oc_key() -> str:
    """법제처 OPEN API 인증키(`OC`). 없으면 `test` 로 떨어진다.

    `OC` 는 신청 시 등록한 이메일 아이디라 비밀값은 아니지만, 계정에 묶이므로
    다른 키와 같은 자리(`.env`)에 둔다. 로그에 찍지 않는다.
    """
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*LAW_OC\s*=\s*(.+)\s*$", line)
            if m and m.group(1).strip().strip('"').strip("'"):
                return m.group(1).strip().strip('"').strip("'")
    return "test"


def _get(path: str, **params) -> dict:
    params["OC"], params["type"] = oc_key(), "JSON"
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def current(law_name: str, law_id: str) -> dict:
    """**1단** — 목록 조회. 2.5KB 로 "바뀌었나" 가 판정된다.

    `법령ID` 로 확인해서 동명이법을 잘못 집는 것을 막는다.
    """
    got = _get("lawSearch.do", target="law", query=law_name)
    items = got.get("LawSearch", {}).get("law", [])
    if isinstance(items, dict):
        items = [items]
    for it in items:
        if it.get("법령ID") == law_id and it.get("현행연혁코드") == "현행":
            return {"법령명": it["법령명한글"], "법령ID": it["법령ID"],
                    "법령일련번호": it["법령일련번호"], "시행일자": it["시행일자"],
                    "공포일자": it["공포일자"], "공포번호": it["공포번호"],
                    "제개정구분": it.get("제개정구분명", "")}
    raise SystemExit(f"현행 법령을 못 찾았다: {law_name} (법령ID {law_id})")


def _texts(node, out: list[str] | None = None) -> list[str]:
    """`...내용` 으로 끝나는 필드를 전부 모은다 — 조문·항·호·목이 중첩돼 있다."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("내용") and isinstance(v, str):
                out.append(v)
            else:
                _texts(v, out)
    elif isinstance(node, list):
        for x in node:
            _texts(x, out)
    return out


def article(mst: str, jo: str, ga: str | None) -> dict:
    """**2단** — 본문에서 조문 하나를 뽑는다. 바뀐 법령에만 부른다.

    **`조문여부='전문'` 을 걸러야 한다** — 편·장 헤더가 같은 조문번호로 섞여 있다.
    안 걸렀다가 소득세법 제14조와 지방세법 제103조의13 을 못 찾았다.
    """
    got = _get("lawService.do", target="law", MST=mst)
    units = got["법령"]["조문"]["조문단위"]
    if isinstance(units, dict):
        units = [units]
    for u in units:
        if u.get("조문여부") != "조문":
            continue
        if str(u.get("조문번호")) != str(jo):
            continue
        if (u.get("조문가지번호") or None) != (str(ga) if ga else None):
            continue
        text = re.sub(r"\s+", " ", " ".join(_texts(u))).strip()
        return {"조문제목": u.get("조문제목") or "", "조문시행일자": u.get("조문시행일자"),
                "본문": text}
    label = f"제{jo}조" + (f"의{ga}" if ga else "")
    raise SystemExit(f"조문을 못 찾았다: MST {mst} {label}")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def excerpt(text: str, needle: str, span: int = 120) -> str:
    """`볼 문구` 주변을 잘라 낸다. **사람이 읽을 인용**이라 원문 그대로 남긴다."""
    i = text.find(needle)
    if i < 0:
        return ""
    return text[max(0, i - span // 2): i + len(needle) + span]


def build() -> dict:
    out = {
        "_설명": "세율의 근거 조문 스냅샷. 사람이 확인한 시점의 원문·해시를 박아 둔다. "
                 "기계는 '바뀌었다' 까지만 말하고 세율 반영은 사람이 한다 (이슈 #28)",
        "출처": f"{BASE}/lawSearch.do · {BASE}/lawService.do (법제처 국가법령정보 공동활용)",
        "조문": [],
    }
    laws: dict[str, dict] = {}
    for w in WATCH:
        head = laws.get(w["법령ID"]) or current(w["법령"], w["법령ID"])
        laws[w["법령ID"]] = head
        art = article(head["법령일련번호"], w["조"], w["가지"])
        label = f"제{w['조']}조" + (f"의{w['가지']}" if w["가지"] else "")
        found = w["볼 문구"] in art["본문"]
        out["조문"].append({
            "법령": head["법령명"], "법령ID": head["법령ID"], "조문": label,
            "조문번호": w["조"], "조문가지번호": w["가지"],
            "조문제목": art["조문제목"],
            "무엇": w["무엇"], "config": w["config"],
            "시행일자": head["시행일자"], "공포일자": head["공포일자"],
            "공포번호": head["공포번호"], "조문시행일자": art["조문시행일자"],
            "본문해시": digest(art["본문"]), "본문길이": len(art["본문"]),
            "볼_문구": w["볼 문구"], "볼_문구_있나": found,
            "인용": excerpt(art["본문"], w["볼 문구"]),
        })
    return out


def check() -> int:
    """커밋된 스냅샷과 대조한다. **1단에서 끝나면 본문을 안 긁는다.**"""
    if not SOURCES.exists():
        print(f"스냅샷이 없다: {SOURCES.relative_to(REPO_ROOT)} — 먼저 --snapshot")
        return 2
    old = json.loads(SOURCES.read_text(encoding="utf-8"))
    by_law: dict[str, list[dict]] = {}
    for row in old["조문"]:
        by_law.setdefault(row["법령ID"], []).append(row)

    print("\n=== 세율 근거 조문 대조 (이슈 #28) ===")
    print("1단 — 목록 조회로 법령일련번호·시행일자·공포번호를 본다 (본문은 안 긁는다)\n")
    changed, checked = [], 0
    for law_id, rows in by_law.items():
        head = current(rows[0]["법령"], law_id)
        checked += 1
        same = (head["시행일자"] == rows[0]["시행일자"]
                and head["공포번호"] == rows[0]["공포번호"])
        mark = "그대로" if same else "**바뀌었다**"
        print(f"  {head['법령명']:<12}시행 {head['시행일자']} · 공포 "
              f"{head['공포일자']}/{head['공포번호']}   {mark}")
        if same:
            continue
        print(f"    2단 — 본문을 긁어 조문 {len(rows)}개를 대조한다")
        for row in rows:
            art = article(head["법령일련번호"], row["조문번호"], row["조문가지번호"])
            if digest(art["본문"]) == row["본문해시"]:
                print(f"      {row['조문']:<12}조문은 그대로")
                continue
            changed.append((row, head, art))
            print(f"      {row['조문']:<12}**조문이 바뀌었다** — {row['무엇']}")
            print(f"        config 의 {row['config']} 를 사람이 다시 읽어야 한다")

    print(f"\n  법령 {checked}개 · 조문 {len(old['조문'])}개")
    if not changed:
        print("  **바뀐 조문 없음.** config/tax-2026.json 을 그대로 쓴다")
        return 0
    print(f"  **바뀐 조문 {len(changed)}개.** 세율 반영은 사람이 한다 — 자동으로 안 고친다")
    print("  `python src/ingest/fetch_law.py --show <조문번호>` 로 원문을 읽는다")
    return 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if "--show" in argv:
        i = argv.index("--show")
        want = argv[i + 1] if i + 1 < len(argv) else ""
        for w in WATCH:
            label = f"제{w['조']}조" + (f"의{w['가지']}" if w["가지"] else "")
            if want not in (w["조"], label):
                continue
            head = current(w["법령"], w["법령ID"])
            art = article(head["법령일련번호"], w["조"], w["가지"])
            print(f"\n=== {head['법령명']} {label}({art['조문제목']}) ===")
            print(f"시행 {head['시행일자']} · 공포 {head['공포일자']}/{head['공포번호']} "
                  f"· 조문시행 {art['조문시행일자']}\n")
            print(art["본문"])
            return
        raise SystemExit(f"감시 대상에 없는 조문이다: {want}")
    if "--snapshot" in argv:
        snap = build()
        SOURCES.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"→ {SOURCES.relative_to(REPO_ROOT)}")
        for row in snap["조문"]:
            flag = "" if row["볼_문구_있나"] else "   ** 볼 문구를 못 찾았다 **"
            print(f"  {row['법령']:<12}{row['조문']:<10}{row['조문시행일자']} "
                  f"{row['본문해시']}  {row['무엇']}{flag}")
        return
    if "--check" in argv or not argv:
        raise SystemExit(check())
    raise SystemExit("사용법: python src/ingest/fetch_law.py "
                     "[--check | --snapshot | --show <조문번호>]")


if __name__ == "__main__":
    main()
