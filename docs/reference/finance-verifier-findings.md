# 선행 프로젝트 실측 — finance_verifier가 실제로 확립한 것과 확립하지 못한 것

> Seed artifact. 작성 2026-08-24, `finance_verifier` 최종 결과(#15) 확정 직후.
> 원본: https://github.com/hyos0415/finance_verifier —
> `results/final/report.md`, `results/eval/test_eval_review.md`, `results/eval/smoke_eval_review.md`

이 문서의 목적은 **FINeprint의 전제가 어디까지 데이터로 뒷받침되는지 정직하게 구분하는 것**이다.
handoff v1 §3은 finance_verifier의 발견을 요약했지만, "확립된 것"과 "아직 확립되지 않은 것"을
구분하지 않았다. 그 구분이 v2의 반증 게이트 설계를 결정한다.

---

## 1. 확립된 것

### 1.1 `condition_omission` 실패는 실재하고, 재현된다

```
Evidence(공시 원문):  A · B 를 모두 충족해야 보너스금리
Claim:               A 만 언급하며 "보너스금리를 받을 수 있다"
Gold:                UNSUPPORTED
Verifier 판정:        SUPPORTED   ← false accept
```

Pilot에서 1건 관찰(`p002_c04_3`, 당시 Qwen·Kanana 두 모델 모두 실패) → Test(unseen)에서
새 상품 2건에 새로 주입한 결과 **2건 모두 실패**. 즉 Pilot의 관찰이 우연이 아니었다.

### 1.2 모델 체급으로 해소되지 않는다

동일 evidence·동일 claim·동일 프롬프트(v2)로 Test의 2건을 여러 모델에 돌린 결과:

| 모델 | 파라미터 | 잡아낸 수 |
|---|---|---|
| Qwen3.5-4B-int4 | 4B | **0 / 2** |
| Claude Haiku 4.5 | (비공개, 4B보다 큼) | 1 / 2 |
| Nemotron Ultra 550B | 550B | **0 / 2** |

파라미터 130배 차이가 나는 두 모델이 정확히 같은 지점에서 같은 실수를 했다.

### 1.3 evidence 검색 실패로는 설명되지 않는다 ★

**이것이 FINeprint에 가장 중요한 확립 사항이다.** handoff v1의 감사(Codex V1)는
`condition_omission`의 반대 가설 중 하나로 "verifier가 조건 B를 포함한 evidence chunk를
애초에 받지 못했을 수 있다(리콜 문제)"를 제시하고 oracle evidence baseline을 요구했다.

**finance_verifier에는 검색 단계가 없다.** evidence는 canonical product record에서
`source_field` 기준으로 직접 주입된다(`src/verifier/client.py`). 즉:

> finance_verifier의 실험은 **이미 oracle evidence 조건에서 수행됐다.**
> 조건 B는 verifier에게 전달된 evidence 텍스트 안에 있었고, 그래도 놓쳤다.

따라서 반대 가설 3(리콜)은 **이 실패의 설명이 될 수 없다.** 새 프로젝트에서
oracle evidence baseline을 다시 만들 필요는 없고, "이미 통과된 통제군"으로 기록한다.
(단, 나중에 실제 검색 단계를 붙이면 리콜은 별개 문제로 다시 등장한다.)

### 1.4 두 번째 실패(INSUFFICIENT ↔ UNSUPPORTED)는 프롬프트로 안 고쳐졌다

"정보 부재"와 "명시적 충돌"의 경계 혼동. 접근이 서로 반대인 두 프롬프트 시도가 모두 실패:

- **v3**(판정 절차 + worked example 추가): 목표한 INSUFFICIENT 4건은 고쳤지만 원래 맞던
  UNSUPPORTED 케이스가 새로 틀렸다 — "애매하면 INSUFFICIENT로 도피"하는 과잉교정.
- **v4**(짧은 부정 규칙만 추가): Qwen의 INSUFFICIENT 인식이 1/4 → **0/4로 악화**.

Nemotron Ultra 550B도 같은 4건을 0/4로 놓쳤고, Gemma-4-31B는 1/4였다. 역시 체급 문제가 아니다.

**단, handoff v1 §3.3의 판단은 유지된다** — 이 실패는 Graph가 필요한 문제가 아닐 가능성이
높다. canonical schema의 `source_field`를 쓰면 "claim이 묻는 항목이 evidence에 애초에
포함된 필드인가"를 결정론적으로 알 수 있다. **FINeprint의 존재 이유는 `condition_omission`에
두고, 이쪽은 저비용 결정론적 보완으로 따로 처리한다.**

### 1.5 프롬프트 반복은 이미 소진됐다

v1→v2 채택(reason 길이 제약 — 정확도·latency 동반 개선), v3·v4 기각. Test 단계는 v2로
고정해서 진행했다. 즉 **"프롬프트를 더 잘 쓰면 되지 않나"는 이미 4버전 소진한 경로다.**

---

## 2. 확립되지 않은 것 — v2의 반증 게이트가 겨냥해야 할 지점

### 2.1 표본이 3건뿐이다 ★★ (가장 심각한 제약)

`error_type == "condition_omission"`으로 라벨된 claim의 전수:

| split | 전체 claim | condition_omission | claim_id |
|---|---:|---:|---|
| Pilot (`data/smoke/`) | 64 | **1** | `p002_c04_3` |
| Test (`data/test/`) | 53 | **2** | `p020_c02`, `p034_c02` |
| **합계** | 117 | **3** | |

§1.2의 크로스모델 표는 **n=2**에 대한 6회 판정이다. Haiku의 1/2도 "Haiku는 이 유형을
안다"는 근거가 되기엔 표본이 너무 작다(원문도 그렇게 명시했다).

**함의**: "`condition_omission`이 구조적 실패다"라는 FINeprint의 전제는 **방향은 신뢰할 만하지만
효과 크기를 논할 근거는 없다.** Graph를 붙여서 "2건 중 2건을 잡았다"고 말하는 건 의미 없는
측정이다. 따라서 **v2의 첫 작업 항목은 Graph도 게이트도 아니라 평가 slice 구축이다.**
(감사의 Codex V7 — "평가 slice 선택 편향 + 검정력 미언급" — 이 지점을 정확히 찔렀다.)

### 2.2 `condition_omission`을 겨냥한 프롬프트는 시도된 적이 없다

v3·v4는 **INSUFFICIENT 경계**를 겨냥했다. "AND 복합조건에서 언급되지 않은 조건이 있는지
evidence 전체와 대조하라"는 지시를 명시적으로 넣어본 적은 없다.

**따라서 반대 가설 1(프롬프트 편향)은 반박되지 않았다.** §1.5의 "프롬프트 소진"은
다른 실패 유형에 대한 것이다 — 이 유형에 대해서는 프롬프트 baseline이 **미측정**이다.
게이트에서 반드시 먼저 확인해야 한다.

### 2.3 claim 분해 단위를 바꿔본 적이 없다

`condition_omission` claim은 설계상 조건을 일부만 인용한다. Decomposer가
"이 claim이 인용한 조건 집합"을 명시적으로 산출하도록 바꾸면 그 자체로 비교가 쉬워질 수
있다 — 미측정.

참고로 decomposer 변경이 결과를 크게 바꾼 전례가 있다: self-containment 결함(대명사·시점조건
누락)을 고쳤을 때 Qwen의 과잉거부 패턴이 사실상 사라졌다(#12 재오픈). **분해 단위는 이
프로젝트에서 이미 한 번 지렛대로 작동했다** — 반대 가설 2를 가볍게 볼 수 없는 이유다.

### 2.4 결정론적 체크리스트를 시도해본 적이 없다 ★

그래프 없이, 조건을 구조화한 뒤 코드가 비교하는 baseline(게이트 G4).
**이것이 통과하면 FINeprint의 전제(구조가 필요하다)는 참이지만 그래프는 불필요하다는 결론이 된다.**

가장 싸고 가장 위험한 baseline이므로 **게이트에서 가장 먼저 돌린다.**

### 2.4b 구조화된 evidence를 LLM에게 준 적이 없다 ★★ (게이트 G5)

`condition_omission` 실패의 원인이 두 층 중 어디인지 갈라지지 않았다.

- **Layer 1 · 구조화** — 자유서술 원문 → 명시적 조건 집합 + 논리 연산자
- **Layer 2 · 판정** — 그 집합과 claim을 비교

finance_verifier가 측정한 것은 **원문 evidence + LLM 판정**(실패)뿐이다.
**구조화된 evidence + LLM 판정**은 측정되지 않았다. 이게 통과하면 결정론적 checker도
그래프도 불필요하고, 기여는 전부 Layer 1(구조화)에 있다는 결론이 된다.

**단, 부분적인 반증은 이미 있다** — `p002_c04_3`의 evidence 원문은
"만기일에 아래의 조건을 **모두 충족하는 경우**"라고 명시하고 조건을 대시로 분리해뒀는데,
두 모델이 모두 놓쳤다(§3.1). 즉 **텍스트 수준의 명시성은 충분하지 않다.**
G5가 측정하는 것은 그보다 강한 조건(형식 자료구조 + 명시 지시)이다.

### 2.4c 실제 조건 구조는 평면 AND가 아니다 ★★

`condition_omission` 3건의 evidence 원문 전수 확인 결과:

| claim | 상품 | 구조 | 평면 집합차분으로 커버 |
|---|---|---|---|
| `p002_c04_3` | e-그린세이브예금 | 평면 ALL_OF (2개) | ✅ |
| `p020_c02` | The파트너예금 | 최상위 독립/OR + **갈래 내부 AND**(`5년이상 + 마케팅동의`) | ❌ |
| `p034_c02` | Sh해양플라스틱Zero!예금 | 항목 AND + **하위 OR 제약**(카드/펀드/체크카드) | ❌ |

**3건 중 2건이 중첩이다.** 그리고 `p020`에서 `Required`를 구하려면 "claim이 어느 혜택
(0.20%)을 말하는가"를 먼저 정해 그 혜택에 걸린 조건만 골라야 한다 — ①②③을 다 합치면
안 된다. **혜택 단위 스코핑 자체가 구조 작업**이고, 평면 리스트로는 표현되지 않는다.

### 2.5 조건 구조 추출의 난이도가 미측정이다

집합 차분이 성립하려면 evidence 원문에서 `Required = {A, B, C}`를 정확히 뽑아야 한다.
그 추출도 결국 LLM이 한다 — 감사의 Codex V2가 지적한 **순환성**(verifier 실패가 extractor
앞단으로 이동)이다. finance_verifier는 조건 추출을 해본 적이 없으므로 이 난이도는 완전히 미지수다.

**원본 공시 데이터 자체가 모호한 사례가 이미 확인돼 있다는 점이 특히 중요하다** —
iM함께예금의 "각 연0.10%p"가 대시 항목 단위인지 하위 OR 조건 단위인지 원문만으로 확정되지
않는다(`results/final/report.md` §7). **정답 조건 집합을 사람이 확정할 수 없는 사례가
존재한다면, gold ConditionGroup 자체에 상한이 있다.**

---

## 3. 재사용 가능한 자산 (구현 시 참고)

| 자산 | 위치 | 비고 |
|---|---|---|
| canonical product record | `data/normalized/deposit_products_canonical.json` | 38개 상품, `spcl_cnd`/`mtrt_int`/`etc_note` 원문 + 기간별 금리 옵션 |
| Finlife raw snapshot | `data/raw/` | 재수집 없이 재현 가능 |
| Claim dataset (Pilot 64 / Test 53) | `data/smoke/`, `data/test/` | `error_type`·`gold_label`·`evidence_text` 라벨 포함 |
| Verifier client + JSON schema 강제 | `src/verifier/` | Schema Valid Rate 100% 달성 구성 |
| Eval harness + failure analysis | `src/eval/` | FAR / UNSUPPORTED Recall / Macro F1, warm-up 제외, 체크포인팅 |
| vLLM 서빙 설정 (검증됨) | `scripts/run_vllm_container.sh` | RTX 4070 8GB, `--max-num-seqs 4 --max-model-len 1024`, CUDA graph on |
| Langfuse tracing + prompt 버전 관리 | `src/verifier/langfuse_client.py` | prompt_version 자동 추적 |

**Verifier 쪽은 다시 만들 필요가 없다.** FINeprint의 A(Verifier Only) 통제군은 이 코드를
그대로 재사용하면 되고, 새로 만들 것은 조건 구조 추출·검사와 hybrid 결합층이다.

---

## 4. 코퍼스 상한 (D1 결정에 직결)

`data/normalized/deposit_products_canonical.json` 전수 집계:

```
은행 정기예금 전수                        38개  (total_count=38, 페이지 추가 없음)
  우대조건(spcl_cnd) 있음                 32개
  조건 항목 2개 이상 (복합조건 후보)        22개
  조건 항목 3개 이상                      18개
  "모두 충족"·"및"·"함께" 명시적 AND        6개   ← 병목
negative(오류 없는 claim) 재사용 가능       71건  (Pilot 46 + Test 25)
```

**명시적 AND가 6개 상품뿐이다.** 나머지는 항목이 여러 개여도 AND인지 OR인지 원문에 안
적혀 있어 gold 확정에 사람 판정이 들어간다(§2.4c의 p020·p034가 그 예). 정기예금만으로
D1을 20건 이상 채우면 절반이 주관 판정이 된다 — **이것이 FINeprint가 은행 적금까지
범위를 넓히는 데이터 근거다**(v2 §5.1).

**negative는 병목이 아니다** — 오류 없는 claim 71건이 이미 있어 재사용 가능하다.

## 5. 한 문단 요약

`condition_omission`은 실재하고, 체급으로 안 풀리고, 검색 리콜 문제도 아니고,
원문에 "모두 충족"이 적혀 있어도 놓친다 — 여기까지는 데이터가 뒷받침한다.
그러나 **표본이 3건이고, 프롬프트·분해단위·결정론적 체크리스트·구조화된 evidence
baseline은 하나도 측정되지 않았으며, 조건 구조 추출의 난이도는 미지수다.** 게다가
**실제 3건 중 2건이 중첩 구조**라 평면 집합 차분으로는 1건만 커버된다.
따라서 FINeprint의 첫 작업은 그래프 설계가 아니라 **(1) 충분한 크기의 층화된 평가 slice
구축, (2) 그 위에서 그래프 없는 baseline(G4·G5·G1·G2)을 먼저 돌려보는 반증 게이트**다.
