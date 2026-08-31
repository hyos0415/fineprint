# -*- coding: utf-8 -*-
"""근거 조문을 법제처에서 뽑아 스냅샷을 뜨고, 바뀌었는지 대조한다.

보는 것이 두 묶음이다 — **세율**(이슈 #28 · `0032`)과 **광고 규제**(이슈 #30 ·
`0034`). 바뀔 때 고쳐야 하는 것이 달라서 스냅샷 파일을 나눈다.

    config/tax-sources.json   조문 5개   바뀌면 → config/tax-2026.json 의 **값**
    config/ad-sources.json    조문 6개   바뀌면 → **화면 계약**(design.md) 과 `0017`

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

광고 규제는 무엇이 다른가
    **행정규칙(`target=admrul`)이 섞인다.** 금융소비자보호법·시행령은 `law` 지만
    감독규정은 금융위원회 고시이고 공정위 심사지침은 예규다. 응답 구조가 법령과
    다르다 — 자세한 것은 `admrul_current`·`admrul_article` 의 주석에 적었다.

    그리고 **바뀌었을 때 사람이 할 일이 다르다.** 세율은 숫자를 고치면 되지만,
    광고 조문이 바뀌면 화면이 무엇을 강제해야 하는지를 다시 봐야 한다(`0017`).

사용법:
    python src/ingest/fetch_law.py --check           바뀌었는지만 본다 (2단. 종료코드로 답한다)
    python src/ingest/fetch_law.py --snapshot [tax|ad]   스냅샷을 새로 쓴다 (사람이 확인한 뒤)
    python src/ingest/fetch_law.py --show 129        조문 원문을 찍어 본다 (사람이 읽으려고)
    python src/ingest/fetch_law.py --show 감독규정      규범 이름으로도 찾는다
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
SOURCES_AD = REPO_ROOT / "config" / "ad-sources.json"
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

# ── 감시 대상 좌표 · 광고 규제 (이슈 #30 · 로드맵 I3)
#
# `0017` 이 화면에 강제한 두 가지("최대값을 단독으로 쓰지 않는다" · "최대값 옆에 남은
# 조건 수를 붙인다")의 **법적 근거**다. `0026` 의 반증 조건이 *"최고금리 단독 표기
# 제한이 실재한다고 보지만 조문을 확인하지 않았다"* 로 열려 있었다.
#
# **여기는 세율과 성질이 다르다.** 세율은 `config/tax-2026.json` 의 **값**이 바뀌지만,
# 광고 조문이 바뀌면 바뀌는 것은 **화면 계약**(`design.md`)이다. 그래서 스냅샷
# 파일을 따로 둔다 — `config/ad-sources.json`.
#
# **`target` 이 섞여 있다.** 법률·대통령령은 `law` 지만 **감독규정은 행정규칙이라
# `admrul`** 이고 응답 구조가 다르다(아래 `admrul_article` 주석 참고).
WATCH_AD = [
    {"target": "law", "법령": "금융소비자 보호에 관한 법률", "법령ID": "013704",
     "조": "22", "가지": None,
     "무엇": "예금성 상품 광고 금지행위 — 이자율의 범위·산정방법을 명확히 표시하지 "
             "않아 오인하게 하는 행위 (제4항제3호가목)",
     "화면": "0017 강제 1 (범위로 쓴다) · 화면 계약 A2",
     "볼 문구": "이자율의 범위ㆍ산정방법"},
    {"target": "law", "법령": "금융소비자 보호에 관한 법률 시행령", "법령ID": "014044",
     "조": "18", "가지": None,
     "무엇": "광고에 포함할 '금융상품의 내용' — 명칭·이자율·수수료와 고시 위임 "
             "(제1항제1호라목). 감독규정 제17조의 위임 근거다",
     "화면": "0017 강제 1 의 상위 근거",
     "볼 문구": "금융위원회가 정하여 고시하는 사항"},
    {"target": "law", "법령": "금융소비자 보호에 관한 법률 시행령", "법령ID": "014044",
     "조": "20", "가지": None,
     "무엇": "광고 시 금지행위 — 중대한 영향을 미치는 사항을 분명하지 않게 표현하는 "
             "행위(제1항제5호)와 고시 위임(제1항제6호). 감독규정 제19조의 위임 근거다",
     "화면": "0017 강제 2 (남은 조건 수) 의 상위 근거",
     "볼 문구": "분명하지 않게 표현하는 행위"},
    {"target": "admrul", "법령": "금융소비자 보호에 관한 감독규정", "법령ID": "77048",
     "조": "17", "가지": None,
     "무엇": "광고의 내용 — **예금성 상품은 '이자율·수익률 각각의 범위 및 산출기준'** "
             "을 광고에 포함해야 한다 (제1항제3호가목)",
     "화면": "0017 강제 1 과 문구가 그대로 대응한다",
     "볼 문구": "이자율ㆍ수익률 각각의 범위 및 산출기준"},
    {"target": "admrul", "법령": "금융소비자 보호에 관한 감독규정", "법령ID": "77048",
     "조": "19", "가지": None,
     "무엇": "광고 시 금지행위 — **소비자에 따라 달라질 수 있는 거래조건을 누구에게나 "
             "적용될 수 있는 것처럼 오인하게 만드는 행위** (제1항제1호·제3항제1호)",
     "화면": "0017 강제 2 가 막으려는 것과 같은 자리",
     "볼 문구": "누구에게나 적용될 수 있는 것처럼 오인하게 만드는 행위"},
    # 조문 좌표가 없다 — 이 예규는 `조문내용` 이 **문자열 하나**로 온다(장·절 구분이
    # 로마숫자다). 그래서 `조: None` 으로 두고 전문을 해시한다.
    {"target": "admrul", "법령": "금융상품 등의 표시·광고에 관한 심사지침",
     "법령ID": "55352", "조": None, "가지": None,
     "무엇": "공정거래위원회 예규 — Ⅴ.1.마 **'세전'인지 '세후'인지를 누락하면 부당한 "
             "표시·광고**. 법 제22조제5항이 표시광고법을 함께 적용한다고 정한다",
     "화면": "세전·세후 라벨 (CLI 헤더 '세후 확정~최대' · '세전')",
     "볼 문구": "‘세전’인지 ‘세후’인지를 누락하여"},
]

# `--check` 가 도는 스냅샷 묶음. 세율과 광고 규제는 **바뀔 때 고쳐야 하는 것이 다르다**
SNAPSHOTS = [
    ("세율", SOURCES, WATCH, "config/tax-2026.json 의 값"),
    ("광고 규제", SOURCES_AD, WATCH_AD, "화면 계약(design.md) 과 `0017`"),
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


def admrul_current(rule_name: str, rule_id: str) -> dict:
    """**1단 · 행정규칙** — 목록 조회. `target=admrul` 은 필드 이름이 법령과 다르다.

    ```
    법령                        행정규칙
    법령ID        ← 핀 →        행정규칙ID
    법령일련번호   ← 매번 새로 → 행정규칙일련번호   (본문 조회의 `ID` 파라미터다)
    공포일자/번호  ← 대응 →      발령일자/발령번호
    현행연혁코드                 현행연혁구분
    ```

    **본문 조회가 `MST` 가 아니라 `ID` 로 간다** — 그리고 그 `ID` 는 `행정규칙ID`(77048)
    가 아니라 **`행정규칙일련번호`**(2100000276850) 다. 헷갈리면 조용히 옛 판을 읽는다.
    """
    got = _get("lawSearch.do", target="admrul", query=rule_name)
    items = got.get("AdmRulSearch", {}).get("admrul", [])
    if isinstance(items, dict):
        items = [items]
    for it in items:
        if it.get("행정규칙ID") == rule_id and it.get("현행연혁구분") == "현행":
            return {"법령명": it["행정규칙명"], "법령ID": it["행정규칙ID"],
                    "법령일련번호": it["행정규칙일련번호"], "시행일자": it["시행일자"],
                    "공포일자": it["발령일자"], "공포번호": it["발령번호"],
                    "제개정구분": it.get("제개정구분명", ""),
                    "종류": it.get("행정규칙종류", ""), "소관": it.get("소관부처명", "")}
    raise SystemExit(f"현행 행정규칙을 못 찾았다: {rule_name} (행정규칙ID {rule_id})")


def admrul_article(seq: str, jo: str | None, ga: str | None) -> dict:
    """**2단 · 행정규칙** — 본문에서 조문 하나를 뽑는다.

    **법령과 응답 구조가 다르다.** 법령은 `조문단위[]` 가 dict 리스트(조문번호·
    조문가지번호·조문여부·조문시행일자 필드가 따로 있다)인데, 행정규칙은
    `조문내용` 이 **문자열 리스트**다 — `"제17조(광고의 내용) ① …"` 처럼 조문번호가
    본문 앞머리에 붙어 있을 뿐이고 좌표 필드가 없다. 그래서 정규식으로 앞머리를 읽는다.

    **같은 `target` 안에서도 형태가 갈린다** — 예규(공정위 심사지침)는 `조문내용` 이
    **문자열 하나**로 온다(장·절이 로마숫자라 조문 단위가 아니다). 그때는 `jo=None`
    으로 불러 전문을 쓴다.

    법령 쪽 함정(`조문여부='전문'` 인 편·장 헤더가 같은 조문번호로 섞인다)에 대응하는
    것을 찾아봤는데 **감독규정에는 없었다** — 36개 원소가 전부 `제N조` 로 시작하고
    좌표 중복이 0이었다(2026-08-31 확인). 다만 `조문형식여부: N` 인 행정규칙도 있으니
    조문을 못 찾으면 죽는 쪽으로 둔다.
    """
    got = _get("lawService.do", target="admrul", ID=seq)
    body = got["AdmRulService"]["조문내용"]
    title = got["AdmRulService"]["행정규칙기본정보"]["행정규칙명"]
    if jo is None:                       # 조문 좌표가 없는 예규 — 전문을 쓴다
        whole = body if isinstance(body, str) else "\n".join(body)
        return {"조문제목": "전문", "조문시행일자": None,
                "본문": re.sub(r"\s+", " ", whole).strip()}
    if isinstance(body, str):
        raise SystemExit(f"조문 단위가 아닌 행정규칙이다 — jo=None 으로 부른다: {title}")
    label = f"제{jo}조" + (f"의{ga}" if ga else "")
    for text in body:
        m = re.match(r"\s*제(\d+)조(?:의(\d+))?", text)
        if not m:
            continue
        if m.group(1) != str(jo) or (m.group(2) or None) != (str(ga) if ga else None):
            continue
        head = re.match(r"\s*제\d+조(?:의\d+)?\(([^)]*)\)", text)
        return {"조문제목": head.group(1) if head else "",
                "조문시행일자": None,     # 행정규칙에는 조문 단위 시행일자가 없다
                "본문": re.sub(r"\s+", " ", text).strip()}
    raise SystemExit(f"조문을 못 찾았다: {title} {label} (행정규칙일련번호 {seq})")


def head_of(w: dict) -> dict:
    """`target` 에 맞는 1단 조회. 스냅샷 행의 모양을 하나로 맞춘다."""
    if w.get("target", "law") == "admrul":
        return admrul_current(w["법령"], w["법령ID"])
    return current(w["법령"], w["법령ID"])


def article_of(w: dict, seq: str) -> dict:
    """`target` 에 맞는 2단 조회.

    **두 모양의 dict 를 다 받는다** — WATCH 항목(`조`·`가지`)과 스냅샷 행
    (`조문번호`·`조문가지번호`)이다. 원래 코드는 `check()` 에서 스냅샷 행의 필드를
    직접 풀어 넘겼는데, 여기로 모으면서 이름이 안 맞아 한 번 깨졌다.
    """
    jo = w["조"] if "조" in w else w.get("조문번호")
    ga = w["가지"] if "가지" in w else w.get("조문가지번호")
    if w.get("target", "law") == "admrul":
        return admrul_article(seq, jo, ga)
    return article(seq, jo, ga)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def excerpt(text: str, needle: str, span: int = 120) -> str:
    """`볼 문구` 주변을 잘라 낸다. **사람이 읽을 인용**이라 원문 그대로 남긴다."""
    i = text.find(needle)
    if i < 0:
        return ""
    return text[max(0, i - span // 2): i + len(needle) + span]


def build(watch: list[dict], 무엇: str, 고칠_곳: str) -> dict:
    out = {
        "_설명": f"{무엇} 의 근거 조문 스냅샷. 사람이 확인한 시점의 원문·해시를 박아 둔다. "
                 f"기계는 '바뀌었다' 까지만 말하고 {고칠_곳} 은 사람이 고친다",
        "출처": f"{BASE}/lawSearch.do · {BASE}/lawService.do (법제처 국가법령정보 공동활용)",
        "조문": [],
    }
    laws: dict[str, dict] = {}
    for w in watch:
        head = laws.get(w["법령ID"]) or head_of(w)
        laws[w["법령ID"]] = head
        art = article_of(w, head["법령일련번호"])
        label = ("전문" if w["조"] is None
                 else f"제{w['조']}조" + (f"의{w['가지']}" if w["가지"] else ""))
        found = w["볼 문구"] in art["본문"]
        row = {
            "target": w.get("target", "law"),
            "법령": head["법령명"], "법령ID": head["법령ID"], "조문": label,
            "조문번호": w["조"], "조문가지번호": w["가지"],
            "조문제목": art["조문제목"],
            "무엇": w["무엇"],
            "시행일자": head["시행일자"], "공포일자": head["공포일자"],
            "공포번호": head["공포번호"], "조문시행일자": art["조문시행일자"],
            "본문해시": digest(art["본문"]), "본문길이": len(art["본문"]),
            "볼_문구": w["볼 문구"], "볼_문구_있나": found,
            "인용": excerpt(art["본문"], w["볼 문구"]),
        }
        if "config" in w:
            row["config"] = w["config"]        # 세율 — 고칠 곳이 config 값이다
        if "화면" in w:
            row["화면"] = w["화면"]            # 광고 규제 — 고칠 곳이 화면 계약이다
        out["조문"].append(row)
    return out


def check_one(무엇: str, path: Path, 고칠_곳: str) -> tuple[int, int, int]:
    """스냅샷 하나를 대조한다. **1단에서 끝나면 본문을 안 긁는다.**

    돌려주는 것 — (규범 수, 조문 수, 바뀐 조문 수). 스냅샷이 없으면 (-1, 0, 0).
    """
    if not path.exists():
        print(f"  스냅샷이 없다: {path.relative_to(REPO_ROOT)} — 먼저 --snapshot")
        return -1, 0, 0
    old = json.loads(path.read_text(encoding="utf-8"))
    by_law: dict[str, list[dict]] = {}
    for row in old["조문"]:
        by_law.setdefault(row["법령ID"], []).append(row)

    changed, checked = 0, 0
    for law_id, rows in by_law.items():
        head = head_of(rows[0])
        checked += 1
        same = (head["시행일자"] == rows[0]["시행일자"]
                and head["공포번호"] == rows[0]["공포번호"])
        mark = "그대로" if same else "**바뀌었다**"
        print(f"  {head['법령명'][:24]:<26}시행 {head['시행일자']} · 공포 "
              f"{head['공포일자']}/{head['공포번호']}   {mark}")
        if same:
            continue
        print(f"    2단 — 본문을 긁어 조문 {len(rows)}개를 대조한다")
        for row in rows:
            art = article_of(row, head["법령일련번호"])
            if digest(art["본문"]) == row["본문해시"]:
                print(f"      {row['조문']:<12}조문은 그대로")
                continue
            changed += 1
            print(f"      {row['조문']:<12}**조문이 바뀌었다** — {row['무엇'][:60]}")
            print(f"        {row.get('config') or row.get('화면')} 를 사람이 다시 봐야 한다")
    print(f"  {무엇} — 규범 {checked}개 · 조문 {len(old['조문'])}개 · "
          f"바뀐 조문 {changed}개")
    return checked, len(old["조문"]), changed


def check() -> int:
    """커밋된 스냅샷 둘을 대조한다 — 세율(이슈 #28) · 광고 규제(이슈 #30).

    **1단은 목록 조회뿐이다** — 규범 하나당 2.5KB. 바뀐 규범만 본문을 긁는다(1.3MB).
    """
    print("\n=== 근거 조문 대조 ===")
    print("1단 — 목록 조회로 일련번호·시행일자·공포(발령)번호를 본다 (본문은 안 긁는다)")
    total_changed, missing = 0, 0
    for 무엇, path, _watch, 고칠_곳 in SNAPSHOTS:
        print(f"\n[{무엇}]  바뀌면 고칠 곳 — {고칠_곳}")
        checked, _n, changed = check_one(무엇, path, 고칠_곳)
        if checked < 0:
            missing += 1
            continue
        total_changed += changed
    if missing:
        return 2
    if not total_changed:
        print("\n  **바뀐 조문 없음.** 세율표와 화면 계약을 그대로 쓴다")
        return 0
    print(f"\n  **바뀐 조문 {total_changed}개.** 반영은 사람이 한다 — 자동으로 안 고친다")
    print("  `python src/ingest/fetch_law.py --show <조문번호>` 로 원문을 읽는다")
    return 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if "--show" in argv:
        i = argv.index("--show")
        want = argv[i + 1] if i + 1 < len(argv) else ""
        for _무엇, _path, watch, _고칠_곳 in SNAPSHOTS:
            for w in watch:
                label = ("전문" if w["조"] is None
                         else f"제{w['조']}조" + (f"의{w['가지']}" if w["가지"] else ""))
                if want not in (w["조"], label, w["법령"]):
                    continue
                head = head_of(w)
                art = article_of(w, head["법령일련번호"])
                print(f"\n=== {head['법령명']} {label}({art['조문제목']}) ===")
                print(f"시행 {head['시행일자']} · 공포(발령) {head['공포일자']}/"
                      f"{head['공포번호']} · 조문시행 {art['조문시행일자']}\n")
                print(art["본문"])
                return
        raise SystemExit(f"감시 대상에 없는 조문이다: {want}\n"
                         f"조문번호 · 규범 이름 중 하나로 부른다")
    if "--snapshot" in argv:
        i = argv.index("--snapshot")
        which = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else ""
        if which and which not in ("tax", "ad"):
            raise SystemExit("--snapshot [tax|ad] — 비우면 둘 다 뜬다")
        pick = {"tax": ["세율"], "ad": ["광고 규제"]}.get(which, ["세율", "광고 규제"])
        for 무엇, path, watch, 고칠_곳 in SNAPSHOTS:
            if 무엇 not in pick:
                continue
            snap = build(watch, 무엇, 고칠_곳)
            path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            print(f"→ {path.relative_to(REPO_ROOT)}  ({무엇})")
            for row in snap["조문"]:
                flag = "" if row["볼_문구_있나"] else "   ** 볼 문구를 못 찾았다 **"
                print(f"  {row['법령'][:22]:<24}{row['조문']:<10}"
                      f"{row['조문시행일자'] or '-':<9} {row['본문해시']}  "
                      f"{row['무엇'][:44]}{flag}")
        return
    if "--check" in argv or not argv:
        raise SystemExit(check())
    raise SystemExit("사용법: python src/ingest/fetch_law.py "
                     "[--check | --snapshot [tax|ad] | --show <조문번호|규범이름>]")


if __name__ == "__main__":
    main()
