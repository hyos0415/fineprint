# -*- coding: utf-8 -*-
"""제한 스키마 LLM 추출기 (추출기 B) — `docs/spec/prereg-03-extraction.md` §1.1 · §6.

무엇을 하나
    자유서술 우대조건 문구에서 금리 항목을 뽑는다. 조건 유형을 **열거값 17개
    (16종 + 기타)에서만** 고르게 하고, 출력을 structured outputs로 강제한다.
    자유 서술을 금지하는 것이 이 추출기의 전부다.

**이건 기각된 별칭 정규화가 아니다.** 사후에 표기를 묶는 게 아니라 뽑을 때 고르게 하는
것이다 (`CLAUDE.md` 5번 · 이슈 #5).

게임 방지 (사전등록 §1)
    입력은 `spcl_cnd` 텍스트와 가입기간뿐이다. **기본금리·최고금리를 주지 않는다** —
    추출기가 목표값을 보면 거기에 맞춰 값을 만들어낸다.

호출 단위
    (조건문, 가입기간) 쌍마다 한 번. 같은 쌍이 여러 행에 걸쳐 있으면 결과를 재사용한다
    (저축은행 홀드아웃은 1,090행이 228쌍뿐이다 — §2.1). 사전등록의 "문항당 1회"는
    이 쌍 단위를 뜻한다.

의존성
    표준 라이브러리만 쓴다. `src/pilot/run_model.py`에서 검증된 raw HTTP 호출을
    재사용한다 (이 저장소는 무의존 관행이다 — `fetch_finlife.py` 주석 참고).

사용법:
    python src/analysis/extract_llm.py --group savingsbank 20260825
    python src/analysis/extract_llm.py 20260824 --limit 3      # 개발 집합 연기 테스트
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finlife_rules import is_no_condition_literal  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR = REPO_ROOT / "data" / "pilot"

# 사전등록 §6에 고정된 실행 조건. 실행 후 수정하지 않는다.
MODEL_ID = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
TEMPERATURE = 0
TIMEOUT = 180
API_URL = "https://api.anthropic.com/v1/messages"

# 조건 유형 열거값 — `docs/spec/prereg-03-extraction.md` §1.1 (decisions/0005)
#   층 1 (12종) 사용자 상태로 O/X 판정 가능
#   층 2 (4종)  공시 문구만으로 판정 불가
#   + 기타      17번째 탈출구. 비율을 부 지표로 보고한다
CONDITION_TYPES = [
    "타상품_보유동시가입", "자동이체", "첫거래_신규고객", "카드실적",
    "마케팅_정보동의", "비대면_채널가입", "목표달성_납입실적", "급여_연금이체",
    "주거래_장기거래_재예치", "잔액_평잔_가입금액", "고객군_자격", "오픈뱅킹_타행계좌등록",
    "실천_미션_인증", "쿠폰_코드_추천인", "무조건_특판_이벤트", "판정불가_불특정",
    "기타",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "cap": {
            "type": ["number", "null"],
            "description": "합산 상한(%p). '최고우대금리 0.5%' 같은 표기가 있으면 그 값, 없으면 null",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition_type": {"type": "string", "enum": CONDITION_TYPES},
                    "rate": {"type": "number", "description": "이 항목의 우대금리(%p)"},
                    "polarity": {"type": "string", "enum": ["required", "must_not_have"]},
                    "applies_to_term": {
                        "type": "boolean",
                        "description": "주어진 가입기간에 이 항목이 적용되는가",
                    },
                    "exclusive_group": {
                        "type": ["string", "null"],
                        "description": "중복 적용 불가로 묶인 항목끼리 같은 id. 아니면 null",
                    },
                    "evidence": {"type": "string", "description": "근거가 된 원문 조각"},
                },
                "required": ["condition_type", "rate", "polarity",
                             "applies_to_term", "exclusive_group", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cap", "items"],
    "additionalProperties": False,
}

# 규칙·열거값은 호출마다 같으므로 system 블록에, 변하는 것(가입기간·조건문)만 user
# 메시지에 둔다.
#
# prompt caching은 붙이지 않았다 — `cache_control: {"type": "ephemeral"}`을 이 system
# 블록에 걸고 재봤지만 `cache_creation_input_tokens`가 계속 0이었다(beta 헤더를 붙이고
# 접두를 2.8k 토큰까지 늘려도 동일). 이 키·모델 경로에서 캐시가 걸리지 않는다.
# 전체 228쌍 비용이 ~$1.2라 파고들 값이 없어 그대로 둔다. 비용 지표(§4)는 캐시 없는
# 값으로 보고한다.
SYSTEM_PROMPT = """한국 예금·적금 공시의 우대조건 문구에서 **우대금리 항목**을 뽑는다.

## 뽑는 규칙

1. **금리가 명시된 조건만** items에 넣는다. 금리를 알 수 없는 조건은 넣지 않는다.
2. **상한 줄은 항목이 아니다.** "최고우대금리 0.5%" · "우대이율(최대 0.90%p)" ·
   "최고 연 1.5%p" 같은 표기는 `cap`에 넣고 items에는 넣지 않는다.
3. **한 줄에 금리가 여럿이면 하나만 고른다.** 금액·기간 구간별로 값이 나뉘어 있으면
   (예: "300만원이상 0.1%, 500만원이상 0.2%") 그 줄의 **최댓값**을 쓴다.
4. **"각 연0.10%p" 형태**는 앞에 나온 금리 없는 조건들 각각에 그 금리를 준다.
   조건이 세 개면 항목 세 개가 된다.
5. **가입기간 차등**이 붙은 항목은 위에 주어진 가입기간에 해당하는지 판단해
   `applies_to_term`에 담는다. 기간 표기가 없으면 true다.
   ("6개월제 0.5%, 12개월제 0.9%"에서 가입기간이 12개월이면 앞은 false, 뒤는 true)
6. **"중복 적용 불가"**로 묶인 항목들에는 같은 `exclusive_group` id를 준다("g1", "g2"...).
   묶이지 않은 항목은 null이다.
7. `polarity`는 조건을 **갖춰야** 하면 "required", **없어야** 하면 "must_not_have"다.
   "카드 사용실적이 있으면 제외" 같은 부정 조건에만 must_not_have를 쓴다.
   "최근 1년간 예적금 미보유"는 유형 자체가 이력 없음을 뜻하므로 required다.
8. 조건문에 **없는 값을 만들지 않는다.** 금리는 적힌 숫자만 쓴다.

## 유형을 고르는 원리 — 먼저 이걸 대 본다

아래 목록에 딱 맞는 말이 없어도 **원리로 판정한다.** 목록은 예시이지 전부가 아니다.

- 조건이 **사용자가 누구인가**로 갈리면 → `고객군_자격`
  (나이·가족 구성·직업·자격·신분 등 **가입 시점에 이미 정해져 있어 바꾸기 어려운 속성**.
   아래 목록의 "연령·다자녀·중소기업 근로자·VIP·단체가입"을 일반화한 것이다)
- 조건이 **사용자가 무엇을 했는가**로 갈리면 → `실천_미션_인증`
  (참여·기부·서약·인증·홍보·미션 수행 등 **행동**. 단 아래 특정 유형에 해당하면 그쪽이 먼저다)
- 조건에 **제3자나 코드가 끼어 있으면** → `쿠폰_코드_추천인`
  (추천인·소개·쿠폰·우대코드·전자명함처럼 **누군가를 거쳐 가입**하는 경로)
- 조건이 **돈이 들어오는 것**이면 → `급여_연금이체`
  (급여·연금·소득·사업 대금 등 **입금의 성격**이 핵심이면 명칭이 달라도 여기다)

`기타`는 **위 16종의 원리를 전부 대 봤는데도 안 맞을 때만** 쓴다.
목록에 그 단어가 없다는 이유로 `기타`를 고르지 않는다.

## condition_type — 아래 17개 중 하나만 고른다

층 1 (사용자 상태로 O/X 판정 가능)

- `타상품_보유동시가입` 주택청약·입출금통장·펀드·수익증권 보유, 짝 상품 동시가입, 교차거래
- `자동이체` 이 상품으로의 자동이체 납입, 공과금·지로·아파트관리비·통신비 자동이체
- `첫거래_신규고객` 최초거래, 최근 N개월 예적금 미보유·신규해지 이력 없음, 첫예금거래
- `카드실적` 신용·체크카드 결제·이용실적, 카드 신규 발급
- `마케팅_정보동의` 마케팅 동의, 개인(신용)정보 수집·이용 동의, 수신동의, 혜택알림 동의
- `비대면_채널가입` 이 상품을 인터넷·모바일·비대면·디지털 채널로 가입
- `목표달성_납입실적` 목표금액 달성, 입금 횟수·연속 성공, 저금 성공 일수, 별 모으기
- `급여_연금이체` 급여이체·소득이체·연금 입금·가맹점대금 입금
- `주거래_장기거래_재예치` 주거래 우대, 거래기간 N년 이상, 장기거래·재예치·자동재예치, 회전
- `잔액_평잔_가입금액` 총수신·요구불 평잔, 가입(재예치)금액 N원 이상, 월부금 N원 이상
- `고객군_자격` 연령(MZ·만65세 이상), 다자녀, 중소기업 근로자, VIP, 단체가입, 비과세종합저축
- `오픈뱅킹_타행계좌등록` 오픈뱅킹 서비스 가입, 타행 계좌 등록

층 2 (공시 문구만으로 판정 불가)

- `실천_미션_인증` ESG 서약, 대중교통 이용, 퀴즈·방문 인증, 봉사활동·상품홍보,
  인증 서비스 등록, 종이통장·통장미발급 미션
- `쿠폰_코드_추천인` 금리우대쿠폰 등록, 금리쿠폰·우대 코드 입력, 추천인
- `무조건_특판_이벤트` 특판·이벤트 우대이율, "가입고객 모두에게 적용" 특별금리,
  만기해지 요건만 있는 항목
- `판정불가_불특정` 랜덤 지급, 조건 서술 없이 "우대금리 적용"만, "상품설명서 참조"

- `기타` 위 16개에 넣기 어려운 조건

## 헷갈리는 자리

| 문구 | 유형 |
|---|---|
| "자동이체로 6회 이상 납입" | `자동이체` — 수단을 요구하면 자동이체다 |
| "누적 10회 입금 시" (수단 무관) | `목표달성_납입실적` |
| "적립식예금 잔액 10만원 이상 보유" | `타상품_보유동시가입` — 다른 상품을 갖는 게 핵심 |
| "이 상품 가입금액 2천만원 이상" | `잔액_평잔_가입금액` — 이 상품의 금액 수준이 핵심 |
| "급여/연금 이체" | `급여_연금이체` — 자동이체의 하위가 아니다 |
| "재예치고객 우대" | `주거래_장기거래_재예치` — 첫거래의 반대다 |
| "이벤트금리(비대면금리)" | `비대면_채널가입` — 채널 조건이 명시되면 채널이다 |
| "만기 해지 시 연 2.50% 제공" | `무조건_특판_이벤트` — 사용자 상태와 무관하다 |
| "스마트폰뱅킹의 상품알리기" | `실천_미션_인증` — 채널 가입이 아니라 홍보 행위다 |

절차 요건("만기시 제공" · "신규시 제공" · "만기일 전일까지 유지")은 **유형이 아니다.**
지급 시점일 뿐이므로 유형으로 두지 않는다. 단 항목 내용이 그것뿐이면
`무조건_특판_이벤트`로 보낸다."""

USER_TEMPLATE = """가입기간: {term}개월

조건문:
```
{text}
```"""


def api_key() -> str:
    """ANTHROPIC_API_KEY를 읽는다. 키 값은 어디에도 출력하지 않는다."""
    for env_path in (REPO_ROOT / ".env", REPO_ROOT.parent / "finance_verifier" / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*ANTHROPIC_API_KEY\s*=\s*(.+)\s*$", line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("ANTHROPIC_API_KEY를 찾지 못했다 (.env 확인)")


def load_pairs(stamp: str, group: str) -> tuple[list[dict], list[dict]]:
    """행 목록과 호출할 (조건문, 기간) 쌍 목록을 만든다.

    행은 채점 단위(닫힘률), 쌍은 호출 단위(McNemar·비용)다 — `prereg-03` §2.1.
    금리(base/max)는 행에만 담고 **쌍에는 담지 않는다.** 쌍이 추출기에 가는 것이다.
    """
    suffix = "" if group == "bank" else f"_{group}"
    rows, pairs, seen = [], [], {}
    for kind, label in (("deposit", "예금"), ("saving", "적금")):
        path = RAW_DIR / f"{kind}{suffix}_{stamp}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        base = {b["fin_prdt_cd"]: b for b in payload["baseList"]}
        for opt in payload["optionList"]:
            product = base.get(opt["fin_prdt_cd"])
            r1, r2 = opt.get("intr_rate"), opt.get("intr_rate2")
            if not product or r1 is None or r2 is None:
                continue
            text = product.get("spcl_cnd") or ""
            if is_no_condition_literal(text):
                continue                                  # 조건없음 행은 A와 같이 제외한다
            term = int(opt["save_trm"]) if str(opt["save_trm"]).isdigit() else 12
            key = (text, term)
            if key not in seen:
                seen[key] = len(pairs)
                pairs.append({"pair_id": len(pairs), "text": text, "term": term})
            rows.append({"pair_id": seen[key], "kind": label, "code": opt["fin_prdt_cd"],
                         "name": " ".join(product["fin_prdt_nm"].split()), "term": term,
                         "base": r1, "max": r2, "gap": round(r2 - r1, 3)})
    return rows, pairs


def call(text: str, term: int, key: str) -> dict:
    """한 쌍에 대해 한 번 호출한다. 재시도 없음 (사전등록 §6)."""
    payload = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user",
                      "content": USER_TEMPLATE.format(term=term, text=text)}],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={
        "Content-Type": "application/json", "x-api-key": key,
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    raw = "".join(b.get("text", "") for b in out.get("content", []))
    return {"raw": raw, "stop_reason": out.get("stop_reason"), "usage": out.get("usage", {})}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    group, limit, label = "bank", None, ""
    if "--label" in argv:
        i = argv.index("--label")
        if i + 1 >= len(argv):
            raise SystemExit("--label 값이 없다")
        label = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    for flag, cast in (("--group", str), ("--limit", int)):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit(f"{flag} 값이 없다")
            value = cast(argv[i + 1])
            group, limit = (value, limit) if flag == "--group" else (group, value)
            argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        raise SystemExit("사용법: python src/analysis/extract_llm.py YYYYMMDD "
                         "[--group bank|savingsbank] [--limit N] [--label v2]")
    stamp = argv[0]

    rows, pairs = load_pairs(stamp, group)
    todo = pairs[:limit] if limit else pairs
    key = api_key()
    print(f"[B] {MODEL_ID} · temperature {TEMPERATURE} · 재시도 없음")
    print(f"    스냅샷 {stamp} ({group}) · 조건 있는 행 {len(rows)} · 호출할 쌍 {len(todo)}"
          f"{f' (전체 {len(pairs)} 중 --limit)' if limit else ''}")

    results, t0, tok_in, tok_out = [], time.time(), 0, 0
    for n, pair in enumerate(todo, 1):
        started = time.time()
        try:
            res = call(pair["text"], pair["term"], key)
            res["error"] = None
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            detail = exc.read().decode("utf-8", "replace")[:300] if hasattr(exc, "read") else str(exc)
            res = {"raw": "", "stop_reason": None, "usage": {},
                   "error": f"{type(exc).__name__}: {detail}"}
        # 스키마 위반은 실패로 집계하되 항목 0개와 구분한다 (사전등록 §6)
        parsed, schema_ok = None, False
        if res["error"] is None:
            try:
                parsed = json.loads(res["raw"])
                schema_ok = isinstance(parsed.get("items"), list) and all(
                    it.get("condition_type") in CONDITION_TYPES
                    and isinstance(it.get("rate"), (int, float))
                    for it in parsed["items"])
            except (json.JSONDecodeError, AttributeError, TypeError):
                parsed = None
        tok_in += res["usage"].get("input_tokens", 0)
        tok_out += res["usage"].get("output_tokens", 0)
        results.append({**pair, "parsed": parsed, "schema_ok": schema_ok,
                        "stop_reason": res["stop_reason"], "usage": res["usage"],
                        "error": res["error"], "elapsed_s": round(time.time() - started, 2)})
        ok = sum(1 for r in results if r["schema_ok"])
        print(f"  {n:3d}/{len(todo)} 기간{pair['term']:>3}개월 "
              f"{results[-1]['elapsed_s']:5.1f}s  스키마 통과 {ok}/{len(results)}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if group == "bank" else f"_{group}"
    tag = f"_{label}" if label else ""     # 직전 결과를 덮어쓰지 않는다 (`prereg-07` §5)
    out = OUT_DIR / f"extract_llm{tag}{suffix}_{stamp}.json"
    out.write_text(json.dumps({
        "label": "llm-restricted-schema", "model_id": MODEL_ID, "snapshot": stamp,
        "group": group, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
        "n_rows": len(rows), "n_pairs": len(pairs), "n_called": len(todo),
        "usage_total": {"input_tokens": tok_in, "output_tokens": tok_out},
        "elapsed_s": round(time.time() - t0, 1),
        "rows": rows, "pairs": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    fails = [r for r in results if r["error"]]
    print(f"\n호출 {len(results)} · 실패 {len(fails)} · 스키마 위반 "
          f"{sum(1 for r in results if r['error'] is None and not r['schema_ok'])}")
    cost = tok_in / 1e6 * 1.0 + tok_out / 1e6 * 5.0   # Haiku 4.5 $1/$5 per MTok
    print(f"토큰 in {tok_in:,} / out {tok_out:,} · 비용 ${cost:.2f}")
    print(f"{time.time() - t0:.0f}초 → {out.relative_to(REPO_ROOT)} (git 제외)")
    for r in fails[:3]:
        print(f"  실패 {r['error'][:160]}")


if __name__ == "__main__":
    main()
