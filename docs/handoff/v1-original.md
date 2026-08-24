# Finance Rule / Constraint Graph — Project Handoff

## 0. 목적

이 문서는 향후 새 금융 Knowledge-Augmented Generation / Rule Graph 프로젝트를 시작할 때
**Orca(Claude Code + Codex), Claude Cowork, GPT가 동일한 문제의식과 설계 방향을 공유하기 위한 공통 handoff 문서**다.

현재는 구현을 시작하지 않는다.

우선순위는 다음과 같다.

1. `finance_verifier` 프로젝트 마무리
2. 기존 `KAG_LlamaIndex` 저장소 구조와 한계 audit
3. 새 프로젝트의 공통 spec 설계
4. 신규 저장소에서 schema-first 금융 Rule / Constraint Graph MVP 시작
5. Verifier-only / Graph-only / Hybrid ablation으로 효과 측정

---

## 1. 참고할 기존 프로젝트

### 1.1 기존 Knowledge Graph 프로젝트

Reference repository:

https://github.com/hyos0415/KAG_LlamaIndex

이 저장소는 News-Arena 계열 프로젝트에서 뉴스 초안의 사실관계를 검증하기 위해 Knowledge Graph를 사용했던 기존 구현이다.

대략적인 흐름:

```text
뉴스 수집
→ 관련 문서 검색
→ Entity / Relation / Triplet 추출
→ Neo4j / LlamaIndex Property Graph
→ 초안과 검증 기사 관계 비교
→ 모순 및 관계 분석
```

이 저장소는 **기존 설계의 기록으로 보존**한다.

새 프로젝트를 이 저장소에서 바로 리팩토링하거나 Git history를 이어받는 것을 기본 방향으로 하지 않는다.
우선 audit 대상으로만 사용한다.

### 1.2 Finance Verifier

Reference repository:

https://github.com/hyos0415/finance_verifier

Finance Verifier는 금융상품 답변을 Atomic Claim으로 분해한 뒤,
Evidence와 Claim을 비교해 다음 세 가지로 판정하는 검증 전용 모듈이다.

```text
SUPPORTED
UNSUPPORTED
INSUFFICIENT
```

핵심 질문:

> 3~4B급 로컬 SLM이 금융상품 답변의 개별 Claim을 근거와 대조해,
> 잘못되거나 근거가 부족한 정보를 실용적인 수준으로 차단할 수 있는가?

Finance Verifier의 failure analysis가 새 Rule / Constraint Graph 프로젝트의 직접적인 출발점이다.

---

## 2. 기존 KAG / News-Arena 접근의 한계

기존 프로젝트의 문제를 단순히 "Knowledge Graph가 효과가 없었다"라고 해석하지 않는다.

핵심 한계는 **그래프를 만들기 전에 그래프 내부의 지식 단위와 관계 제약을 충분히 정의하지 않았다는 점**이다.

### 2.1 자유도가 높은 Entity / Triplet 추출

기존 구조에서는 LLM이 문서에서 Entity와 Relation을 비교적 자유롭게 추출했다.

그 결과 다음 계약이 약했다.

- 어떤 Entity를 독립 Node로 허용할 것인가
- 같은 개념의 표기 변형을 어떻게 정규화할 것인가
- 어떤 Relation만 허용할 것인가
- 같은 의미의 관계가 다른 Relation 이름으로 생성되면 어떻게 처리할 것인가
- 잘못 추출된 Triplet을 어떤 규칙으로 제거할 것인가
- Relation의 방향성과 cardinality를 어떻게 검증할 것인가

즉 Graph 내부에 들어오는 지식의 형식 자체가 충분히 제한되지 않았다.

### 2.2 Graph schema / ontology / constraint가 뒤늦게 붙음

기존에는 그래프가 먼저 만들어지고 다음 항목을 나중에 고민했다.

- Entity 기준
- Relation taxonomy
- Graph consistency
- 데이터 품질
- Error taxonomy
- Graph metric
- 평가 방법

새 프로젝트에서는 순서를 반대로 가져간다.

```text
Problem
→ Failure definition
→ Schema
→ Constraint
→ Extraction
→ Graph
→ Evaluation
```

### 2.3 Graph 기여도를 독립적으로 측정하지 못함

기존 News-Arena에서는 Graph가 전체 파이프라인 안에 포함됐지만,

> Graph가 없을 때보다 최종 검증 품질을 실제로 얼마나 개선했는가?

를 명확하게 측정하지 못했다.

새 프로젝트에서는 Graph의 incremental value를 반드시 ablation으로 측정한다.

---

## 3. Finance Verifier에서 새롭게 확인한 문제

### 3.1 핵심 failure: `condition_omission`

예시:

```text
Evidence:
최고 우대금리를 받으려면
A. 급여이체
B. 마케팅 동의
C. 모바일 가입
조건을 모두 충족해야 한다.

Claim:
급여이체와 모바일 가입을 하면 최고 우대금리를 받을 수 있다.
```

Claim에 명시된 A와 C 자체는 Evidence에 존재하지만,
B가 빠졌으므로 전체 Claim은 사실이 아니다.

정답:

```text
UNSUPPORTED
```

문제는 LLM Verifier가 종종 다음처럼 판단한다는 점이다.

```text
A → Evidence에 존재
C → Evidence에 존재
→ SUPPORTED
```

즉 **Claim에 적힌 내용의 일치 여부에는 집중하지만,
Claim에 적히지 않은 필수조건을 Evidence 전체에서 능동적으로 찾아내는 데 취약하다.**

### 3.2 이 문제는 소형 모델 체급 문제로만 보기 어려움

동일한 condition_omission 유형이 여러 모델에서도 반복됐다.

대표 관찰:

- Qwen3.5-4B: 두 사례 모두 실패
- Claude Haiku: 일부 실패
- Nemotron Ultra 550B: 두 사례 모두 실패

따라서 현재 가설은 다음과 같다.

> **복합 AND 조건에서 Claim이 언급하지 않은 필수 구성요소를 찾는 문제 자체가
> 일반적인 자연어 entailment 방식으로는 구조적으로 까다롭다.**

### 3.3 두 번째 failure: `INSUFFICIENT ↔ UNSUPPORTED`

예시:

```text
Claim:
만기 후 이율에 관한 주장

Evidence:
우대조건(spcl_cnd) 정보만 제공
```

정답은 `INSUFFICIENT`지만 모델이 `UNSUPPORTED`로 과대판정하는 패턴이 있었다.

다만 이 문제는 Graph가 반드시 필요한 문제는 아니다.
canonical schema의 `source_field` 또는 evidence coverage layer로 deterministic하게 보완할 가능성이 있다.

따라서 **Graph 프로젝트의 핵심 존재 이유는 `condition_omission`으로 둔다.**

---

## 4. 후속 프로젝트의 핵심 가설

> LLM Verifier가 자연어 의미 비교에는 강하지만
> 복합 금융상품 조건의 누락 여부를 판단하는 데 취약하다면,
> 금융상품의 조건 구조를 명시적인 Rule / Constraint Graph로 표현해서
> 두 시스템의 failure mode를 상호 보완할 수 있는가?

Graph는 Verifier를 대체하지 않는다.

```text
                    Atomic Claim
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
        SLM Verifier          Rule/Constraint Graph
             │                       │
      자연어 의미 비교             조건 완전성 검사
      숫자/문구/예외 비교           필수조건 누락 검사
             │                       │
             └───────────┬───────────┘
                         ▼
                    Final Verdict
```

---

## 5. 핵심 설계 원칙: Schema-first

기존 프로젝트의 가장 큰 개선 방향은 **Graph를 만들기 전에 허용 가능한 구조를 먼저 고정하는 것**이다.

### 5.1 데이터 도메인은 금융상품으로 제한

초기 MVP는 Finance Verifier와 동일한 데이터 축을 활용한다.

- 은행권 정기예금
- 금융상품 한눈에 Open API
- Finance Verifier의 snapshot / canonical data

처음부터 대출, 카드, 보험, 펀드 등 전체 금융상품으로 확대하지 않는다.

### 5.2 공식 API의 정형 구조를 schema 기반으로 사용

초기 후보:

```text
Product
Institution
Term
BaseRate
MaxRate
Eligibility
Channel
Benefit
Condition
Exception
MaturityInterest
```

LLM이 새로운 Entity type을 자유롭게 생성하지 않도록 한다.

### 5.3 자연어 필드는 제한된 schema로 매핑

자연어 성격이 강한 필드:

```text
spcl_cnd
mtrt_int
etc_note
```

LLM은 사용할 수 있지만 역할을 다음처럼 제한한다.

> 자유로운 Graph 생성 → 금지  
> 사전에 정의된 schema의 slot 채우기 → 허용

---

## 6. 초기 Graph schema 후보

### Node / Entity

```text
Product
Institution
Benefit
ConditionGroup
Condition
Channel
Eligibility
Term
Rate
Exception
```

### Relation

```text
Product ─HAS_BENEFIT→ Benefit
Benefit ─REQUIRES→ ConditionGroup
ConditionGroup ─HAS_CONDITION→ Condition
Product ─AVAILABLE_VIA→ Channel
Product ─ELIGIBLE_FOR→ Eligibility
Product ─HAS_TERM→ Term
Term ─HAS_RATE→ Rate
Benefit ─HAS_EXCEPTION→ Exception
```

Relation도 허용 목록을 둔다.

---

## 7. ConditionGroup을 first-class structure로 둔다

단순히:

```text
Product → requires → A
Product → requires → B
Product → requires → C
```

만 저장하면 `AND`인지 `OR`인지 사라질 수 있다.

따라서:

```text
Benefit
   │
REQUIRES
   ▼
ConditionGroup
operator = ALL_OF
   ├─ A
   ├─ B
   └─ C
```

처럼 조건 그룹 자체에 논리를 부여한다.

초기 operator 후보:

```text
ALL_OF
ANY_OF
NOT
MUTUALLY_EXCLUSIVE
THRESHOLD
TEMPORAL
EXCEPTION
```

---

## 8. `condition_omission` 탐지 방식

Evidence 기준:

```text
Required = {A, B, C}
```

Claim 기준:

```text
Claimed = {A, C}
```

그러면:

```text
Required - Claimed = {B}
```

결과:

```text
missing_required_condition = B
→ UNSUPPORTED 후보
```

핵심은 LLM에게 "빠진 조건이 있는지 다시 생각해봐"라고 요구하는 것이 아니다.

조건 구조를 명시적으로 만들고 deterministic set / constraint comparison으로 검증한다.

---

## 9. Graph 역할을 과도하게 넓히지 않는다

초기 MVP 우선순위:

1. `condition_omission`
2. AND / OR 구조
3. 필수조건 / 선택조건
4. 예외조건
5. 상호배타 조건
6. threshold / range
7. temporal constraint

초기 MVP에서 제외:

- 범용 금융상품 추천
- 고객 개인화
- 대규모 Graph traversal
- PageRank 등 Graph algorithm을 사용하기 위한 사용
- 자유형 multi-hop reasoning
- 전체 금융상품군 확대
- Graph 자체를 위한 Graph 구축

Graph algorithm은 **문제에서 필요성이 확인될 때만** 도입한다.

---

## 10. 핵심 평가 설계

최소 다음 세 시스템을 비교한다.

```text
A. Verifier Only
B. Rule / Constraint Graph Only
C. Verifier + Rule / Constraint Graph
```

목적:

> Graph를 붙였다는 사실이 아니라
> Graph가 기존 Verifier에서 실제로 관찰된 failure를 얼마나 줄였는지 측정한다.

### Primary evaluation slice

```text
condition_omission
```

확인할 질문:

- Verifier Only는 몇 건을 놓치는가?
- Graph Only는 condition omission을 얼마나 잡는가?
- Hybrid는 전체 False Accept를 줄이는가?
- Graph 때문에 정상 Claim을 과하게 차단하는 false reject가 생기지는 않는가?

### 지표 후보

```text
Condition Omission Recall
False Accept Rate
UNSUPPORTED Recall
Macro F1
False Reject
Additional Latency
Graph Rule Application Rate
Schema / Extraction Valid Rate
```

Graph extraction 오류와 Verifier 오류를 분리한다.

---

## 11. News-Arena와 새 프로젝트의 가장 중요한 차이

기존:

```text
Graph를 만들어본다
→ Graph에서 탐색한다
→ 나중에 효과를 평가한다
```

새 프로젝트:

```text
Verifier를 먼저 평가
→ 반복되는 failure를 발견
→ failure 원인을 구조적으로 정의
→ 그 failure를 겨냥한 Graph 설계
→ Graph의 incremental value 측정
```

---

## 12. 기존 KAG 저장소 audit 시 확인할 것

`KAG_LlamaIndex`를 바로 수정하지 않는다.

다음 네 분류로 정리한다.

### A. 재사용 가능한 것
- Neo4j 연결 코드
- LlamaIndex Property Graph 사용 패턴
- Graph serialization / query utilities
- 실험 코드 일부

### B. 재사용하면 안 되는 것
- 자유도가 높은 Entity / Relation 생성
- News domain-specific schema
- 평가 없이 사용된 Graph algorithm
- 명시적 contract가 없는 Triplet extraction

### C. 설계적으로 발전시킬 것
- Entity normalization
- Relation constraint
- Schema validation
- Graph data quality
- provenance
- extraction confidence
- failure taxonomy

### D. 새 프로젝트에서 새로 만들 것
- Finance domain schema
- ConditionGroup
- Rule representation
- deterministic constraint checker
- Verifier / Graph Hybrid layer
- ablation eval

---

## 13. 새 저장소 운영 방향

후속 프로젝트는 신규 저장소에서 시작한다.

원칙:

- 기존 `KAG_LlamaIndex` repo를 fork하지 않는다.
- 기존 Git history를 가져오지 않는다.
- 기존 News-Arena repo는 당시 설계의 기록으로 보존한다.
- Finance Verifier도 독립 프로젝트로 보존한다.
- 새 Graph 프로젝트는 세 번째 독립 실험으로 시작한다.

포트폴리오 흐름:

```text
News-Arena / KAG
Graph-first 접근
        ↓
한계 발견
        ↓
Finance Verifier
Eval-first / failure-first 접근
        ↓
condition_omission 발견
        ↓
Finance Rule / Constraint Graph
Schema-first 구조적 보완
        ↓
Hybrid Ablation
```

---

## 14. 도구별 역할 분담

### Claude Cowork
- 공통 project spec 설계
- 문서 구조 관리
- architecture decision 정리
- schema / scope / non-goal 정리
- 코드와 문서 consistency 관리

### Orca (Claude Code + Codex)
- 실제 코드 구현
- schema / graph builder 구현
- constraint checker 구현
- Eval Harness
- ablation 실행
- Claude Code / Codex 상호 리뷰
- edge case와 반대 가설 검증

### GPT
- 문제 정의 비판
- KAG / Graph / 금융 AI 사례 조사
- schema 및 실험 설계 검토
- failure interpretation
- 결과 분석
- 발표 / 포트폴리오 서사 정리
- "왜 이 기술이 필요한가?" 지속 검토

---

## 15. 공통 Source of Truth

새 프로젝트에는 tool-neutral한 공통 spec을 둔다.

후보:

```text
AGENTS.md
docs/project_spec.md
docs/schema.md
docs/evaluation.md
docs/decisions/
```

Claude 전용 지시는 `CLAUDE.md`에 따로 둘 수 있지만,
핵심 문제 정의와 결정은 특정 Agent에 종속된 문서에만 두지 않는다.

공통 spec 최소 항목:

```text
Problem
Hypothesis
Scope
Non-goals
Data
Schema
Constraint
Evaluation contract
Metrics
Current decisions
Rejected alternatives
Known limitations
```

---

## 16. 여러 Agent 사용 시 주의점

여러 Agent가 같은 문서를 읽었다고 해서 독립적으로 같은 결론을 냈다고 해석하지 않는다.

예:

```text
Claude가 A라는 가설을 docs에 기록
→ Codex가 A를 읽음
→ GPT가 A를 읽음
→ 모두 A라고 말함
```

이건 독립 검증이 아니다.

중요한 decision에는 가능하면 다음을 같이 남긴다.

```text
Decision
Evidence
Alternative
Why rejected
```

독립 검증이 필요하면 해당 결론을 보지 않은 reviewer에게 별도로 검토시킨다.

---

## 17. 현재 하지 않을 것

이 문서를 받은 직후 구현을 시작하지 않는다.

현재 우선순위는 `finance_verifier`를 완결하는 것이다.

새 프로젝트 시작 전 순서:

1. Finance Verifier final result 확인
2. 기존 KAG repo audit
3. `condition_omission` 사례 확정
4. 공통 spec 작성
5. 신규 repository 생성
6. MVP 구현 시작

---

## 18. 첫 세션에서 원하는 작업

이 문서를 받은 Agent는 바로 구현하지 말고 먼저:

1. `KAG_LlamaIndex` repository 구조를 분석한다.
2. 기존 Graph pipeline의 실제 schema / extraction / retrieval / reasoning 흐름을 정리한다.
3. 이 문서에서 주장한 기존 한계가 실제 코드와 일치하는지 검증한다.
4. 재사용 가능한 코드와 폐기할 코드를 구분한다.
5. Finance Rule / Constraint Graph의 최소 schema 후보를 비판적으로 검토한다.
6. `condition_omission`을 정말 Graph가 해결하기 적합한지 반대 가설도 제시한다.
7. 새 프로젝트 공통 spec 초안을 만든다.

구현은 이 분석 이후 시작한다.

---

## 19. 프로젝트의 핵심 질문

> **자연어 의미 비교에 강한 LLM Verifier와,
> 복합 금융상품 조건의 완전성을 deterministic하게 검사하는 Rule / Constraint Graph를 결합하면,
> 각각을 단독으로 사용할 때보다 금융 답변의 False Accept를 실제로 줄일 수 있는가?**

첫 번째 검증 목표:

> **Finance Verifier에서 반복적으로 확인된 `condition_omission` failure를
> 구조화된 조건 표현으로 얼마나 안정적으로 제거할 수 있는가?**

---

## 한 줄 요약

> 기존 Graph 프로젝트를 추상적으로 리팩토링하는 프로젝트가 아니라,
> Finance Verifier의 실제 Eval에서 발견된 `condition_omission` failure를 출발점으로
> schema-first Rule / Constraint Graph를 설계하고,
> Verifier와의 상호 보완 효과를 ablation으로 측정하는 후속 프로젝트다.
