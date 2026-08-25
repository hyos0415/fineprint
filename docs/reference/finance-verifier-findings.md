# 선행 프로젝트 실측 — finance_verifier가 실제로 확립한 것과 확립하지 못한 것

> Seed artifact. 작성 2026-08-24, `finance_verifier` 최종 결과(#15) 확정 직후.
> 원본: https://github.com/hyos0415/finance_verifier —
> `results/final/report.md`, `results/eval/test_eval_review.md`, `results/eval/smoke_eval_review.md`

이 문서의 목적은 **FINeprint의 전제가 어디까지 데이터로 뒷받침되는지 정직하게 구분하는 것**이다.
handoff v1 §3은 finance_verifier의 발견을 요약했지만, "확립된 것"과 "아직 확립되지 않은 것"을
구분하지 않았다. 그 구분이 v2의 반증 게이트 설계를 결정한다.

---

## 0. 상위 정정 (2026-08-25) ★ 먼저 읽는다

**선행 프로젝트가 종료 후 자체 감사에서 결론 두 개를 뒤집었다.** 원본은
`finance_verifier/results/eval/precondition_audit.md`(커밋 `e73df67` · `1f0db8c`)이며,
아래 §1~§5의 서술 중 그와 어긋나는 부분은 **이 절이 우선한다.** 원래 기록은 무엇이
어떻게 바뀌었는지 추적할 수 있도록 지우지 않고 남긴다.

| # | 이 문서의 기존 서술 | 감사 후 |
|---|---|---|
| 1 | §1.2 · §1.4 — INSUFFICIENT 혼동은 **체급 무관한 태스크 구조적 한계** | **틀렸다.** 같은 프롬프트로 **Kanana-2-3B(로컬 3B)·Haiku 4.5·Sonnet 5가 전부 4/4**. 실패는 Qwen·Nemotron·Gemma에 한정된 **모델별 특성**이다 |
| 2 | §1.4 · §1.5 · §2.2 — `condition_omission`은 프롬프트로 **해결되지 않는다** | **부분적으로 틀렸다.** 절차형 규칙(v8)을 넣으면 Qwen Test에서 **2/2 잡힌다.** 다만 대가가 있다 — 정상 claim 인식률 0.913 → **0.674 붕괴** |

### 0.1 INSUFFICIENT 정답률 — 전체 모델

기존 서술은 실패한 두 모델(Nemotron·Gemma)만 인용한 일반화였다.

| 모델 | Pilot (4건) | Test (2건) |
|---|---|---|
| **Kanana-2-3B** (로컬 3B, 탈락한 후보) | **4/4** | – |
| Claude Haiku 4.5 | **4/4** | **2/2** |
| Claude Sonnet 5 | **4/4** | – |
| Nemotron Ultra 550B | 0/4 | 1/2 |
| Gemma-4-31B | 1/4 | – |
| **Qwen3.5-4B** (채택) | **0/4** (채택 설정) | **0/2** |

**3B 로컬 모델이 만점을 받는 태스크를 "구조적 한계"라고 부를 수 없다.** 그리고 채택 설정의
Qwen은 **6개 실행 전부에서 INSUFFICIENT를 한 번도 출력하지 않았다** — 사실상 2분류기다.

### 0.2 절차형 프롬프트의 효과는 모델 능력에 종속된다

| 모델 | v2 → v8 정확도 | 판정 |
|---|---|---|
| Sonnet 5 | 0.9062 → **0.9344** | 개선 (단 Schema Valid 1.0 → 0.953) |
| Nemotron 550B | 0.9245 → **0.9623** (Test) | 개선 |
| Haiku 4.5 | 0.9057 → 0.8491 (Test) | 악화 |
| **Qwen3.5-4B** | 0.8438 → **0.6875** (Pilot) | **붕괴** |

### 0.3 정정된 결론이 FINeprint의 방향을 지지한다 ★

감사가 내린 진짜 결론은 이것이다.

> 약점은 "누락을 못 본다"가 아니라 **"evidence에 나열된 조건이 ALL_OF인지 ANY_OF인지,
> 어느 혜택에 속하는지 범위(scope)를 잡지 못한다"**이다. 절차형 규칙은 그 판별 능력을
> **요구할 뿐 제공하지 않는다.**
>
> 이건 후속 과제의 가설로 바로 연결된다 — **판별 능력을 요구하는 대신 구조를 입력으로
> 주면 어떻게 되는가.**

Qwen이 v8에서 새로 거부한 정상 claim 3건의 원인이 그 증거다.

```
p004_c01   다른 우대조항을 안 썼다고 거부   →  별개 혜택에 속한 조건 (대조 대상이 아님)
p020_c01   조건을 일부만 언급했다고 거부    →  claim은 두 조건을 모두 언급했다 (오독)
p034_c01   조건을 다 안 썼다고 거부        →  ANY_OF(택일)를 ALL_OF로 간주
```

**혜택 스코핑과 ALL_OF/ANY_OF 판별** — v2 §7.1이 "MVP 최소 요건"으로 정한 바로 그 지점이다.

### 0.4 평가 지표 설계 결함 — 우리 판정 기준에 직접 영향 ★

감사가 새로 찾은 것이고, FINeprint의 통과 기준(이슈 #3 · `prereg-02` §5)에 반영해야 한다.

**`"UNSUPPORTED"`만 반환하는 상수 스텁이 1·2·3순위 지표를 전부 이긴다.**

| | FAR (1순위) | UNSUP. Recall (2순위) | Schema (3순위) | Accuracy |
|---|---|---|---|---|
| Qwen 실제 (Test) | 0.1071 | 0.8846 | 1.0 | 0.9057 |
| `"UNSUPPORTED"` 상수 스텁 | **0.0000** | **1.0000** | 1.0 | — |

가상의 반례가 아니다. 실제 v8 프롬프트도 같은 방향으로 움직였다 — 정확도를 15.6%p
떨어뜨리면서 FAR과 UNSUPPORTED Recall을 둘 다 개선했다.

**해법은 순위제가 아니라 제약식이다.**

> FAR을 목표치 이하로 낮추되, **정상 claim 거부율(FRR)을 기준선 대비 악화시키지 않는다.**

Macro F1도 대표 지표에서 빼야 한다 — 6%짜리 클래스(INSUFFICIENT 4건)가 macro 평균의
33%를 차지해 순위를 뒤집는다. **단 진단 지표로는 계속 쓴다**(클래스를 통째로 버린 분류기를
정확히 벌점으로 준다).

### 0.5 재현 계약이 더 좁아졌다

"같은 모델·같은 프롬프트"로는 같은 실험이 아니다. 감사가 실측으로 확정한 재현 단위:
모델 ID·양자화 방식 · **vLLM 버전과 이미지 SHA** · **CUDA graph 활성 여부** · 서빙 파라미터 ·
생성 파라미터 · chat template · 프롬프트 라벨. 헤드라인 Macro F1 0.8434는 **eager 경로
값이었고 채택 경로 기준 0.6151로 정정**됐다 — 실행 경로가 다르면 다른 실험이다.

부수적으로 **재현성 자체는 확인됐다** — 동일 설정 2회 실행이 verdict·reason 텍스트까지 동일.

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

> **정정 (2026-08-25)**: 이 절의 결론은 §0.1로 대체됐다. 실패는 체급이 아니라 **모델별
> 특성**이다 — 3B 로컬 모델(Kanana)이 INSUFFICIENT 4/4를 받는다. 아래 서술은 당시 기록이다.

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

> **정정 (2026-08-25)**: §0.1·§0.2 참고. v3·v4가 실패한 것은 맞지만, 그건 **Qwen에서**의
> 결과다. 같은 태스크를 Kanana·Haiku·Sonnet은 프롬프트 변경 없이 맞힌다.

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

> **정정 (2026-08-25)**: 소진되지 않았다. 감사에서 **v7·v8이 새로 시도**됐고, 절차형
> 규칙(v8)은 목표 실패를 Qwen Test 2/2로 교정했다. 대가는 정상 claim 과잉거부다(§0.2).

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

> **정정 (2026-08-25)**: 이제 시도됐다(v7·v8, §0.2). 이 항목은 **해소**됐고, 남은 질문은
> "프롬프트로 잡히는가"가 아니라 **"과잉거부 없이 잡히는가"**다.

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
