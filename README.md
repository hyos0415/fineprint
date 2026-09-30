# FINeprint

> 내 상황을 말로 적고 우대조건을 하나씩 확인하면, **내가 실제로 받을 수 있는 금리**로
> 예금·적금을 비교해 준다. 광고에 적힌 최고금리가 아니라.

이름은 "read the fine print"(약관의 깨알글씨까지 읽어라)에서 왔다.
**FIN**ance · **fine**-grained condition · printed disclosure.

지금은 **내 컴퓨터에서만 도는 프로토타입**이다. 공개 배포는 하지 않았고, 가입을 받지 않으며,
수익도 내지 않는다 — 상품마다 은행 홈페이지 링크와 대표전화만 알려준다
([`0037`](./docs/decisions/0037-link-only-and-no-monetization.md)).

## 최고금리만 보여주는 비교와 무엇이 다른가 — 실제 상품 두 개로

금융감독원 공시(2026-08-26 스냅샷)에 올라온 12개월 정기예금 두 개다.

| 상품 | 광고 최고금리 | 기본금리 | 우대조건 |
|---|---|---|---|
| 제주은행 **J정기예금** | **3.80%** | **2.00%** | 비대면 가입 0.3%p · 매월 앱 로그인 0.2%p |
| 전북은행 **JB 다이렉트예금통장** | 3.76% | 3.76% | 없음 |

최고금리 순으로 줄을 세우면 J정기예금이 위에 온다. 그런데 이 시스템의 계산기에 넣으면
이렇게 나온다.

```
J정기예금            세전 2.00~2.50%   "근거가 일부 없음"
                    우대조건을 다 채워도 2.50%다. 나머지 1.30%p는 조건문에
                    "이벤트시 … 추가 적용할 수 있음"이라고만 적혀 있어 받는 방법을 알 수 없다
JB 다이렉트예금통장   세전 3.76%        "금리 확정" — 조건이 없으니 누구나 이 금리
```

우대조건을 하나도 못 채우는 사람이면 두 상품의 차이는 1.76%p, 1천만원을 1년 맡겼을 때
세전 이자로 17만 6천원이다. **"최고금리가 더 높은 쪽"이 그 사람에게는 더 불리한 선택이다.**

그래서 이 시스템은 세 가지를 다르게 한다.

- **금리를 한 숫자가 아니라 범위로 보여준다.** 아직 답하지 않은 조건이 있으면
  "확실히 받는 금리 ~ 다 채웠을 때 금리"로 적고, 답할수록 범위가 좁아진다
- **광고 금리 중 공시로 설명되지 않는 부분을 따로 표시한다.** 버리지 않고 "근거가 일부 없음"
  같은 라벨을 붙여 같이 보여준다
- **추측하지 않는다.** 우대조건을 채우는지는 사용자가 예/아니오/모름으로 직접 답한다.
  "모름"은 채운 것으로 치지 않고 범위로 남는다

규제도 같은 방향이다. 예금 광고는 이자율의 **범위와 산출기준**을 함께 적어야 한다
(금융소비자 보호에 관한 감독규정 제17조제1항제3호가목 ·
[`0034`](./docs/decisions/0034-ad-rules-exist-but-bind-the-seller.md)).
문제 정의 전체는 [`docs/spec/problem.md`](./docs/spec/problem.md)에 있다.

## 어떻게 작동하나 — 코드 기준

화면은 세 장이다. **시작 폼 → 질문 화면 → 결과와 리포트.**
서버(`src/web/app.py`)는 이미 있는 계산 함수를 부르기만 하고, 사용자의 답을 저장하지 않는다
([`0040`](./docs/decisions/0040-the-server-is-stateless-and-has-no-db.md)).

### 1. 입력 — 문장은 검색 조건만 채우고, 사용자가 고쳐서 낸다

시작 폼에서 권역(은행/저축은행) · 은행 · 예금/적금 · 기간 · 금액 · 선호를 고른다.

폼 위에 **"내 상황" 상자**가 있다(선택). 예를 들어 *"신한은행 예금 1년 정도 넣을 생각"*이라고
적고 "칸 채우기"를 누르면, 로컬 모델이 문장을 읽어 **네 칸(권역 · 은행 · 예금/적금 · 기간)을
폼에 미리 채운다.** 사용자는 채워진 칸을 보고 틀린 것을 고친 뒤 "목록 보기"를 누른다.
이 확인을 거치지 않고 계산에 들어가는 값은 없다.

- **금액은 채우지 않는다.** 사람이 써 본 세션에서 "오천만원"을 세 번 모두 500만원으로
  읽었다([`prereg-29`](./docs/spec/prereg-29-r2-scope-prefill.md) §7). 금액은 직접 적는다
- **우대조건 답("급여이체 한다" 같은 것)은 채우지 않는다.** 실험에서 오답이 너무 많아
  기각했다(아래 "실험 결과")
- **문장은 모델 호출에만 쓰고 버린다.** 응답 화면에도, 로그에도 남기지 않는다
  ([`0042`](./docs/decisions/0042-local-inference-goes-to-r2-only.md))
- 상자를 비우거나 모델 서버가 꺼져 있으면 폼은 그대로 동작한다

### 2. 추천 기준 — 계산이고, 순서는 사용자가 정한다

상품마다 이 순서로 계산한다(`src/analysis/calculate.py`).

```
기본금리 + 사용자가 채우는 우대조건의 합 (상품 상한 적용)
  → 공시 최고금리를 넘지 않게 자른다
  → 일반과세 15.4%를 뗀다
  = 세후 예상금리 (범위)
```

공시에는 상품별 비과세 여부가 없어서 화면은 일반과세 기준으로 계산하고,
비과세종합저축 대상이면 세금이 달라진다는 안내를 붙인다.

- **정렬 기본값은 "조건을 다 채웠을 때" 순**이고, 범위와 남은 조건 수를 늘 같이 보여준다.
  조건을 못 채울 것 같은 사람은 **"확정된 금리" 순**으로 바꿔 볼 수 있다
  ([`0017`](./docs/decisions/0017-start-from-the-best-and-narrow.md))
- **선호는 시스템이 짐작하지 않는다.** 설문 5문항(영업점 방문 · 처음 거래하는 기관 · 금리 확실성 등)의
  답을 고정 표에 따라 "금리 %p"로 바꾸고(예: 영업점에 되도록 안 가겠다고 답하면 영업점에서만
  가입되는 상품에 −0.50%p),
  그 값을 화면에 보여주며 고칠 수 있게 한다. 선호는 **순서만** 바꾸고 금리 숫자는 안 바꾼다.
  설문을 안 하면 가중치는 0개다([`0030`](./docs/decisions/0030-preferences-are-rate-equivalents.md))
- **은행을 좁히면 밖에 더 좋은 상품이 있을 때 그것도 알려준다** — 좁힌 탓에 좋은 상품이
  묻히지 않게 하려는 것이다([`0028`](./docs/decisions/0028-candidate-scope-is-first-class.md))
- 금액을 적으면 예상 이자(세전·세후 원)를 보여준다. **금액은 표시에만 쓰고 순서는 안 바꾼다**
  ([`0055`](./docs/decisions/0055-amount-changes-only-the-display.md))

### 3. 근거 확인 — 숫자가 어디서 왔는지 보여준다

상위 상품마다 리포트가 붙는다(`src/analysis/report.py` ·
[`0036`](./docs/decisions/0036-report-shows-where-the-number-came-from.md)).

- 기본금리 → 확실히 받는 우대 → 불확실한 우대 → 세전 → 세금 → 세후로 이어지는 계단
- 우대조건마다 몇 %p인지와 **공시 문구 원문**(자르지 않는다)
- 광고 최고금리 중 공시로 설명되지 않는 %p
- 세금을 어떻게 뗐는지 — 세율과 근거 조문(`config/tax-2026.json`에서 읽는다)
- 은행 홈페이지 링크와 대표전화

화면이 이 약속을 지키는지는 **화면 계약 검사**가 확인한다
(`src/analysis/check_screen_contract.py`). "최고금리를 혼자 쓰지 않는다", "세후 라벨이 있다",
"우리끼리 쓰는 내부 이름이 화면에 없다" 같은 규칙 19개(A1~A19)를 질문 중간 상태 전부에서 검사한다.
(검수 중인 [#85](https://github.com/hyos0415/fineprint/issues/85)가 스무 번째 규칙 A20을 더한다.)

### 4. 사용자 확인 단계 — 질문은 하나씩, 답은 셋 중 하나

결과를 좁히는 것은 모델이 아니라 **사용자의 답**이다(`src/analysis/ask_loop.py`).

- 처음에 **"거래해 본 기관을 골라 주세요"**를 한 번 묻는다. 거래한 적 없는 은행은
  "첫 거래 우대 가능 · 실적 조건 불가"로 자동으로 정리된다
  ([`0045`](./docs/decisions/0045-conditions-are-per-institution.md))
- 나머지는 공시 문구를 보여주며 **예 / 아니오 / 모름**으로 묻는다. 기준 금액이 있는 조건도
  숫자를 묻지 않고 문구로 묻는다
  ([`0027`](./docs/decisions/0027-ask-the-clause-not-the-number.md))
- 답할 때마다 목록과 금리 범위가 다시 계산된다. 어디서 멈춰도 그 시점의 범위를 보여준다
- 답은 서버에 남지 않는다. 이어서 하려면 화면이 주는 **이어하기 코드**를 사용자가 갖고 있는다
  ([`0054`](./docs/decisions/0054-the-user-holds-the-resume-code.md))

## AI는 어디에 쓰고 어디에 안 쓰나

**금리 계산 · 정렬 · 질문 만들기 · 판정은 전부 규칙대로 도는 코드다.** 모델은 두 자리에만 있다.

| 도구 | 실제로 맡는 일 | 받는 데이터 |
|---|---|---|
| **Claude API** (Claude Haiku 4.5) | 공시 우대조건 문구를 구조로 바꾼다 — "비대면 가입시 0.3%" → `{유형: 비대면_채널가입, 금리: 0.3}`. 유형은 정해진 17종에서만 고르게 스키마로 강제한다(`src/analysis/extract_llm.py`). **공시가 갱신될 때 한 번 돌리고**, 화면은 그 결과 파일을 읽는다 | 공개된 공시 문구뿐. 사용자 입력은 보내지 않는다 |
| **Qwen3.5-4B** (Q5_K_M 양자화) | "내 상황" 문장에서 네 칸(권역 · 은행 · 예금/적금 · 기간)을 뽑는다(`src/analysis/r2_parse.py`). 은행 이름은 공시 기관 이름 목록에서만 고르게 스키마로 막는다 | 사용자 문장. **외부로 나가지 않는다** |
| **llama.cpp** (`llama-server`) | Qwen3.5-4B를 내 컴퓨터 GPU(8GB)에서 띄우는 엔진. 웹 서버가 `127.0.0.1:8081`로 부른다 | — |

**왜 자리가 이렇게 나뉘었나.** 사용자 문장에는 주거래 은행·금액 같은 금융 정보가 섞인다.
그래서 그 자리는 외부 API로 보내지 않고 로컬 모델에 둔다. 공시 문구는 공개 정보라 품질을
재 가며 API를 쓴다([`0042`](./docs/decisions/0042-local-inference-goes-to-r2-only.md)).

**코드와 설계 문서가 다른 점 하나.** 추출 실험에서는 "규칙 파서를 먼저 돌리고 산수가 안 맞는
것만 LLM에 보내는" 폴백 구조를 채택했다([`0012`](./docs/decisions/0012-adopt-fallback.md)).
그러나 **지금 화면의 계산 경로는 규칙 파서를 거치지 않고 Claude 추출 결과 파일만 읽는다**
(`src/analysis/ask_budget.py`의 `load()` → `calculate.evaluate()`). 규칙 파서
(`src/analysis/finlife_rules.py`)는 추출 품질을 비교·측정하는 경로에 있다.

## 지금 구현된 것

| 부품 | 상태 | 파일 |
|---|---|---|
| 공시 수집 | 금융감독원 API · 월 1회 갱신 · 은행 18곳 97상품 · 저축은행 79곳 668상품 | `src/ingest/fetch_finlife.py` |
| 우대조건 추출 | Claude Haiku 4.5 · 유형 17종 강제 | `src/analysis/extract_llm.py` |
| 계산기 | 범위 · 층 라벨 · 세후 · 공시 상한 | `src/analysis/calculate.py` |
| 질문 루프 | 예/아니오/모름 · 거래 기관 목록 · 기관별 판정 | `src/analysis/ask_loop.py` |
| 선호 가중치 | 설문 5문항 → 금리 %p · 화면에서 확인·수정 | `src/analysis/prefs.py` |
| 비교 리포트 | 조건별 %p · 공시 원문 · 세금 계산 설명 · 예상 이자 | `src/analysis/report.py` |
| 웹 화면 | FastAPI · 서버 렌더 · 무상태 · 이어하기 코드 | `src/web/` |
| 자연어 칸 채우기 | 로컬 Qwen3.5-4B · 네 칸 · 사용자가 고쳐서 제출 | `src/analysis/r2_parse.py` · `POST /prefill` |
| 화면 계약 검사 | A1~A19 · 질문 중간 상태 전부 | `src/analysis/check_screen_contract.py` |
| 세율 근거 감시 | 법제처 API로 조문이 바뀌었는지 확인 | `src/ingest/fetch_law.py --check` |

같은 계산을 명령줄로도 돌릴 수 있다 — `python src/analysis/ask_loop.py 20260826 --group bank --term 12`.

## 실험 결과

이 저장소는 **재기 전에 예측과 판정 기준을 먼저 커밋한다**(`docs/spec/prereg-*.md` — 사전등록).
아래 숫자는 모두 그 기록에서 옮겼고, 표본이 작은 것은 작다고 같이 적는다.

**우대조건 추출**
- 규칙 파서를 먼저 쓰고 안 맞는 것만 LLM에 보내는 폴백 구조가 은행권 **83.9%** 상품에서
  우대조건 합계를 공시와 맞췄다(예측 83.8% 이상 · 저축은행 79.1%).
  규칙만 쓰면 75.8%, LLM만 쓰면 71.2%였다
  — [`0012`](./docs/decisions/0012-adopt-fallback.md) · [`prereg-04`](./docs/spec/prereg-04-fallback.md)
- 남은 실패의 **71%는 공시 쪽 문제**였다 — 조건문에 금리 숫자가 없거나, 공시 상한이 실제 폭보다
  작다. 어떤 추출기도 없는 숫자는 만들 수 없어서 추출 개선을 여기서 멈췄다
  — [`0013`](./docs/decisions/0013-stop-improving-extraction.md)

**계산의 정직성**
- 처음에는 "자동이체 한다"는 답 하나가 은행 10곳 상품을 한꺼번에 올렸다. 조건을 은행별로
  따지게 고치자 금리가 확정된 상품 비율은 58.2% → 76.1%로 올랐고 평균 확정 금리는
  2.975% → 2.727%로 내려갔다. **부풀려 말하던 금리가 사라진 것이다**
  — [`0045`](./docs/decisions/0045-conditions-are-per-institution.md)
- 세후 정렬은 세전 정렬과 순서가 같았다. 공시 API에 상품별 비과세 여부가 없어서
  한 번 계산할 때 모든 상품이 같은 세율을 받기 때문이다
  — [`0033`](./docs/decisions/0033-after-tax-sorting-cannot-reorder.md)

**자연어 입력 (R2)**
- **우대조건 답까지 문장으로 채우는 것은 기각했다.** 어려운 문장 30개(부정문 · 보고 싶은 은행과
  거래 은행이 다른 문장)에서 30개 중 8개 문장, 9건의 오답이 화면까지 갈 뻔했다
  — [`0058`](./docs/decisions/0058-r2-rejected-under-prereg-27.md) ·
  [`0060`](./docs/decisions/0060-r2-scope-only.md)
- 검색 조건 칸은 같은 어려운 표본에서 **89%** 맞았다(기준 88% 이상)
  — [`prereg-29`](./docs/spec/prereg-29-r2-scope-prefill.md) §6
- 사람이 직접 쓴 6번의 세션에서 네 칸은 틀린 것이 없었다. 금액은 한글 숫자를 3번 모두 잘못
  읽어 채우지 않기로 했다. 단 **6번 중 4번은 문장 뼈대를 Claude가 제안했다** — 순수한 자기
  문장 표본은 아직 작다 — [`prereg-29`](./docs/spec/prereg-29-r2-scope-prefill.md) §7

**구조가 더 필요한가**
- 카드·타상품 가입처럼 다른 상품을 끼고 도는 조건은 은행권 19%로 많지만 모양은 평평했다.
  그래프 구조가 필요하다는 기준에 못 미쳐 그래프를 만들지 않았다
  — [`prereg-32`](./docs/spec/prereg-32-cross-sell-shape.md)
- 조건문은 A4 몇 장 분량이라 검색(RAG)이 필요 없다. 검색은 상품설명서 코퍼스가 생길 때까지
  보류했다 — [`0056`](./docs/decisions/0056-no-corpus-yet-undefined-words-stay-bank-check.md)

## 앞으로 할 것

전체 과업 지도와 선행 조건은 [`docs/spec/roadmap.md`](./docs/spec/roadmap.md)에 있다.

- **월 갱신 때 사람 손이 몇 건 필요한가** — 9월 공시로 잰다. 이 값이 "추출에 AI가 필요한가"의
  근거가 된다(로드맵 B6 · 이슈 [#65](https://github.com/hyos0415/fineprint/issues/65))
- **화면 피로 줄이기** — 시작 화면과 질문 화면을 줄인 버전이 사람 검수 중이다
  (이슈 [#85](https://github.com/hyos0415/fineprint/issues/85) · PR [#86](https://github.com/hyos0415/fineprint/pull/86))
- **교육장 파일럿** — 여러 명이 동시에 써 보고 도움이 되는지 본다
  (이슈 [#83](https://github.com/hyos0415/fineprint/issues/83) · [`prereg-34`](./docs/spec/prereg-34-classroom-pilot.md))
- **아직 없는 것** — 조건 분해가 원문과 맞는지 판정하는 검증 단계(R3 · 정답 라벨 대기) ·
  중도해지 이율(상품설명서 수집이 먼저 · [`prereg-33`](./docs/spec/prereg-33-early-termination.md)) ·
  정책 상품과 지점 위치(데이터 경로가 없다)

알려진 한계 — 상품별 비과세 여부와 카드 실적 기준은 공적 데이터에 없다
([`0033`](./docs/decisions/0033-after-tax-sorting-cannot-reorder.md) ·
[`0062`](./docs/decisions/0062-no-card-data-yet.md)). 그래서 해당 조건은 사용자에게 묻고,
자세한 내용은 은행 링크에서 확인하게 한다.

## 이전 설계 — AI 답변 검증기 (2026-08-26에 바꿨다)

이 프로젝트는 처음에 **"AI가 예적금 금리를 과대하게 말하는 것을 잡아내는 검증기"**였다.
그건 선행 프로젝트 `finance_verifier`가 이미 한 일이라, 사용자가 실제로 겪는 문제
(내게 맞는 상품 고르기)로 방향을 바꿨다. 조건 유형 17종, 추출기, 사전등록 방법론은 그대로
살아남았다.

- 전환 사유와 살아남은 것 — [`docs/decisions/0009-pivot-to-recommender.md`](./docs/decisions/0009-pivot-to-recommender.md)
- 옛 문제 정의(보존용) — [`docs/spec/problem-v1-verifier.md`](./docs/spec/problem-v1-verifier.md)
- 그 시절 파일럿에서는 Qwen3.5-4B를 vLLM으로 띄워 Kanana-2-3B · Claude Haiku · Sonnet과 비교했다
  (`src/pilot/` · [`prereg-02`](./docs/spec/prereg-02-pilot.md)). 지금 화면 경로에는 vLLM이 없다

## 돌려 보기

```bash
python -m venv .venv
source .venv/Scripts/activate            # PowerShell 은 .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. 공시 수집 — .env 에 FINLIFE_API_KEY
python src/ingest/fetch_finlife.py deposit
python src/ingest/fetch_finlife.py saving

# 2. 우대조건 추출 — .env 에 ANTHROPIC_API_KEY (Claude Haiku 4.5)
python src/analysis/extract_llm.py 20260826          # 수집한 날짜

# 3. 화면 — http://127.0.0.1:8000
python -m uvicorn src.web.app:app --host 127.0.0.1 --port 8000

# (선택) "내 상황" 상자 — llama.cpp 로 Qwen3.5-4B GGUF 를 띄운다. 없어도 폼은 동작한다
llama-server -m <Qwen3.5-4B-Q5_K_M.gguf> -ngl 99 -np 8 -c 32768 --port 8081 --jinja --log-disable
```

**원본 데이터는 저장소에 올리지 않는다.** 금융감독원 API로 공개되는 데이터를 GitHub에
재배포하지 않기 위해서다. 수집·집계 스크립트와 문서에 적은 집계 결과만 커밋한다.

작업을 이어받는다면 **[`START-HERE.md`](./START-HERE.md)** 부터 읽는다. 부품별 설계는
[`docs/spec/design.md`](./docs/spec/design.md), 사람이 정할 결정은
[이슈](https://github.com/hyos0415/fineprint/issues)에 있다.

## 계보

```
KAG_LlamaIndex     그래프부터 만들고 쓸 곳은 나중에 → 한계 발견
        ↓
finance_verifier   평가부터 만들기 → 검증기가 조건을 놓치는 실패를 실제로 관측
        ↓
FINeprint          검증기에서 추천기로 → 계산은 코드, AI는 필요한 두 자리만 → 효과를 잰다
```

참고 저장소 (읽기만 하고 수정하지 않는다):

- https://github.com/hyos0415/finance_verifier — 검증기·클레임 분해 (선행, 완료)
- https://github.com/hyos0415/KAG_LlamaIndex — 그래프 시도 (선행, 보존)
- https://github.com/hyos0415/reranker_FT — 리랭커 PEFT (수치 철회 상태)

## 라이선스

[MIT](./LICENSE).

**단, 인용한 공시 문구는 여기에 포함되지 않는다.** 이 저장소는 분석을 위해 금융회사의
우대조건 원문과 상품설명서 일부를 인용한다. 그 문구의 권리는 각 금융회사에 있고,
MIT 라이선스는 **우리가 쓴 코드와 문서**에만 적용된다.
