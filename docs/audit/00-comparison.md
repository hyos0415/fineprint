# 두 독립 감사 결과 비교

> 작성: 2026-08-20 · 브랜치 `audit/comparison`
> 대상 산출물
> - `docs/audit/claude-architecture-audit.md` — Claude Code, 브랜치 `audit/claude-architecture`
> - `docs/audit/codex-adversarial-review.md` — Codex, 브랜치 `audit/codex-adversarial`

---

## 0. 독립성이 실제로 얼마나 확보됐나

먼저 이 비교의 신뢰도를 규정한다. handoff §16 이 경고한 함정("같은 문서를 읽고 같은 결론을
내는 것은 독립 검증이 아니다")에 이 절차 자체가 걸리기 때문이다.

**확보된 것**

- 두 감사는 별개 git worktree(`kag-audit-claude`, `kag-audit-codex`)에서 **동시에** 수행됐다.
  Codex 실행 로그 검증 결과 상대 worktree 경로를 참조한 쉘 명령은 0건이다
  (언급 6건은 전부 "접근하지 않았다"는 자기 서술과 지시문 인용)
- 두 감사 모두 상대의 결론을 읽지 않은 상태에서 작성이 끝났다
- 과제가 다르게 지정됐다 — Claude Code는 기술(記述), Codex는 반증

**확보되지 않은 것 (해석 시 감안할 것)**

- 두 감사 모두 **같은 handoff 문서와 같은 `docs/CONTEXT.md`를 읽었다.** 따라서
  CONTEXT.md 에 이미 기록된 항목(발견 1~20)에 대한 일치는 **독립 발견이 아니라 공통 입력의 결과**다
- Codex 스스로 이 한계를 지적했다(리뷰 B16, 심각도 경미) — "이 리뷰도 handoff 가 지정한
  쟁점 구조 안에서 작성되었으므로 완전 독립 검증이 아니다"

**따라서 아래 §1 을 두 등급으로 나눈다.**

- **1급 수렴** — 두 원본 문서(handoff, CONTEXT.md)에 **없던 판정**에 양쪽이 도달한 것. 증거 가치 높음
- **2급 수렴** — CONTEXT.md 에 이미 있던 내용의 재확인. 증거 가치 낮음 (다만 "여전히 유효하다"의 확인)

---

## 1. 일치 — 두 감사가 같은 결론에 도달한 것

### 1급 수렴 (원본 문서에 없던 판정)

| # | 일치 판정 | Claude Code | Codex | 왜 1급인가 |
|---|---|---|---|---|
| C1 | **handoff §12 A 의 "Neo4j 연결 코드 재사용 가능"은 성립하지 않는다** | §7 → `A → B(재사용 금지)` | A3 → `C 또는 B로 내려라` | handoff 의 명시적 분류를 양쪽이 독립적으로 뒤집었다. 근거도 동일 — 몽키패치 6개 + `upsert_nodes` 무동작 스텁 |
| C2 | **이 저장소의 최대 이관 자산은 코드가 아니라 방법론이다 — handoff §13("history 안 잇는다")이 그것을 버릴 위험** | §8.2 (사전 등록·예약된 반증 조건·처치를 성과로 읽지 않기) | B15 (사전 등록·fixture·raw logging·metric verification) | handoff 어디에도 없는 판정. Codex 는 "가장 위험한 가정 5개" 5위로, Claude Code 는 이관 자산 최상위로 각각 독립 배치 |
| C3 | **handoff §6 스키마의 `Rate`/`Term`/`Condition` 노드 선택이 이 저장소가 실패한 지점과 같은 층의 결정이다** | §7 C절 "노드 vs 속성 구분", §2.2 | A2 반증조건, B10 | CONTEXT.md §9 는 "날짜·수치를 노드에서 빼라"만 말한다. 그것을 **새 스키마의 구체 노드 후보에 적용**한 것은 양쪽 모두 독립 |
| C4 | **LLM 생성 메타데이터가 추출 입력으로 재투입되는 경로를 handoff 가 다루지 않는다 — 새 프로젝트에서 원문/파생 필드를 강제 분리해야 한다** | §3.2 | A5 | CONTEXT.md 발견 10은 "가능성, 후속 개선 대상"으로 유보. 양쪽이 독립적으로 **차단 사유로 승격**했다 |
| C5 | **문제는 "평가 없이 Graph algorithm을 썼다"(handoff §12 B)가 아니라 Graph 출력이 최종 판정에 개입하는 계약이 없었다는 것** | §5.1, §5.2 | A6 | handoff 의 프레이밍을 양쪽이 같은 방향으로 재정의했다 |

### 2급 수렴 (CONTEXT.md 기재 사항 재확인)

| # | 일치 판정 | 비고 |
|---|---|---|
| C6 | 자유 스키마 추출기가 근본 원인이며 그대로 이관하면 안 된다 | 양쪽 동일 수치 인용 (460종/773관계, 단발성 70.9%) |
| C7 | Neo4j 는 실제 경로에 없었고 실측 그래프는 로컬 JSON이었다 | CONTEXT 발견 2·3 |
| C8 | 최종 리포트가 f-string 결합이며 `need_graph=True` 고정 | 양쪽 동일 코드 인용 (`graph_flow.py:52-53,74-78`) |
| C9 | 육각형 지표 중 일부가 LLM 자기 채점이다 | 양쪽 동일 (`knowledge_graph.py:65-102`) |
| C10 | provenance 는 발전시킬 가치가 있는 자산이다 | 양쪽 동일 |

---

## 2. 불일치 — 같은 증거, 다른 판정

### D1. `verify_metrics.py` / serialization 유틸을 자산으로 볼 것인가 ★ 결정 필요

| | 판정 | 근거 |
|---|---|---|
| **Claude Code** (§8.1) | **이관 자산 4개 중 하나로 승격** | 산출물과 계산 코드를 함께 커밋하는 패턴 자체가 발견 20 교훈의 구현체 |
| **Codex** (A4) | **강등** — "utility 라기보다 진단 과정에서 사후 안정화된 산출물" | `cross_doc_path_ratio` 0.45% 오차를 허용한다고 스스로 명시. 8지표 중 7개만 완전 재현 |

**같은 사실을 보고 반대로 판정했다.** 조정안: 둘 다 부분적으로 옳다 —
**패턴은 자산, 특정 코드는 검증 후 이식**. Codex 의 반증 조건("생성·strip·metric·fixture 검증이
하나의 재현 가능한 명령으로 고정되고 모든 지표가 baseline과 완전 일치")을 새 프로젝트의
**초기 커밋 수용 기준**으로 삼으면 두 판정이 동시에 만족된다.

### D2. handoff §2.1 "정규화 부재" 비판의 함의 ★ 결정 필요

| | 판정 |
|---|---|
| **Claude Code** (§6 대조표) | **"성립하나 handoff 의 함의는 과대"** — 이 저장소는 정규화를 실제로 시도해 **기각**했다. 재등장 엔티티가 925개 중 42개(4.5%)뿐이라 완벽한 별칭 사전의 상한이 이미 낮다 |
| **Codex** (A1) | 자유 스키마 비판을 **전면 지지**. 정규화 상한 문제는 다루지 않음 |

**Codex 가 놓친 것이 아니라 과제 범위 밖이었다**(Codex 의 lane 은 handoff 가정 공격).
그러나 함의가 크다 — handoff §2.1 은 "정규화 규칙이 없었다"를 개선 가능한 결함으로 나열하지만,
이 저장소의 실측은 **정규화가 해결책이 아니었다**는 것이다. 새 프로젝트가 "이번엔 정규화를
제대로 하자"로 읽으면 이미 기각된 경로를 다시 걷는다. handoff §2.1 정정 대상.

### D3. `condition_omission` 자체에 대한 평가

| | 판정 |
|---|---|
| **Codex** (B7) | **치명 1순위** — Graph 로 풀 문제라는 전제가 미검증. 반대 가설 4개 + 각각의 반증 실험 제시 (프롬프트 편향 / claim 분해 단위 / evidence 리콜 / 결정론적 체크리스트) |
| **Claude Code** | **다루지 않음** — 과제 범위(기존 아키텍처 기술)에 없었다 |

불일치가 아니라 **역할 분담의 결과**. 다만 Claude Code 감사의 §4.3(리랭커가 그래프 입력을
절반으로 줄인다 → 리콜 희생)이 Codex 의 반대 가설 3(evidence 검색 리콜 문제)과
**독립적으로 같은 층을 가리킨다**. 아래 §3 M2 참고.

---

## 3. 상호 보강 — 한쪽만으로는 약했던 결론

### M1. 노드 타입 오염: 경고(Codex) + 규모(Claude Code)

Codex 는 `Rate`/`Term`/`Condition` 을 노드로 두는 위험을 지적하고 사례를 들었다(A2, B10).
Claude Code 는 그 위험의 **크기를 측정했다**(§2.2~2.3):

```
리터럴 형태 엔티티 노드      152 / 925 = 16.4%
목적어가 리터럴인 트리플      183 / 773 = 23.7%   ← 트리플 1/4이 속성을 간선으로 표현
교차문서 브릿지 중 리터럴      6 / 42  = 14.3%   ← 다리의 1/7이 날짜·퍼센트
```

**합쳐진 결론**: handoff §6 노드 후보 10종 중 `Rate`·`Term`·수치성 `Condition` 을
노드로 두면, 기존 프로젝트가 트리플의 23.7%에서 겪은 실패를 **스키마에 명시적으로 설계해
넣는 것**이 된다. 두 감사가 동일하게 요구한 산출물은 **"노드로 둘 것 / 리터럴 속성으로 둘 것 /
논리식 내부 값으로 둘 것" 구분표**이며, 이것이 MVP 착수 전 최우선 문서다.

### M2. 리콜 층: 반대 가설(Codex) + 코드 근거(Claude Code)

Codex 반대 가설 3은 "verifier 가 B 조건을 포함한 evidence chunk 를 받지 못했을 수 있다"이며
oracle evidence 실험을 제안한다. Claude Code §4.3 은 기존 코드가
`LLMRerank(top_n = top_k//2)` 로 **검색 문서의 절반을 버리고**(`solver.py:64,87`),
그래프에 들어가는 청크가 2~5개로 제한된다는 것을 보였다.

**합쳐진 결론**: "증거 리콜 부족"은 새 프로젝트의 가설이 아니라 **기존 프로젝트에서 이미
코드로 확인된 실패 양상**이다. Codex 의 oracle evidence baseline 은 선택 항목이 아니라
필수 통제군으로 격상해야 한다.

### M3. 순환성: 위험(Codex) + 기준선(Claude Code)

Codex B8 은 "verifier 실패가 extractor 앞단으로 이동한다"를 치명 2순위로 두고
gold ConditionGroup 대비 extractor 평가를 요구한다. Claude Code §3.4 는
**무제약 추출이 실제로 어떤 상태를 만드는지의 기준선**을 표로 제공한다 —
허용 타입 0, 출력 언어 미제약(영문 83종), 리터럴/개체 미구분, 엔티티 경계 미정의,
**파싱 실패가 조용히 버려지고 계측되지 않음**(`build_index.py:189`).

**합쳐진 결론**: 새 프로젝트의 extractor 계약은 위 7개 칸을 모두 채워야 하고,
그중 **"버려진 트리플 비율"은 CONTEXT.md §6 이 이미 요구했으나 구현되지 않은 지표**다.
handoff §10 의 "Schema / Extraction Valid Rate" 가 이것을 뜻한다면, 기존 프로젝트에서
같은 요구가 계측 누락으로 이어진 전례를 명시해야 한다.

---

## 4. 한쪽에만 있는 발견

### Claude Code 단독 (Codex 가 다루지 않음)

| # | 발견 | 심각도 | 새 프로젝트 영향 |
|---|---|---|---|
| U1 | **응용 경로가 그래프를 저장하지 않는다.** `app/**` 에 `persist` 호출 0건. README 가 KG 도입 근거로 내세운 "1월 기사 + 3월 기사 연결"은 **코드 구조상 불가능**했다 | 치명 | handoff §12 에 없는 **신규 D 항목: 그래프 수명 정책**. 스키마를 완벽히 고정해도 이 층은 해결되지 않는다 |
| U2 | **메타데이터 오염 → 가짜 다리의 인과 사슬 실증.** `(기사 카테고리, Is, 정치/경제)` 트리플이 CONTEXT §4 의 최대 클러스터 경로 `경제 → 정치/경제 → 정치 → …` 의 두 번째 노드를 만들었다. 즉 발견 10을 유보한 결정이 v2a-hi 판정 무효화 사유의 일부를 만들었다 | 중대 | 파생 필드 분리를 "개선"이 아니라 **차단 조건**으로 둘 근거 |
| U3 | **`enricher.py:117` 이 저장소 이력 전체에 정의된 적 없는 메서드를 호출한다.** `git log -S"def get_storage_context"` 0건. 2026-02-04 이후 상시 `AttributeError`. DAG 의 색인 태스크는 성공할 수 없었다 | 중대 | CONTEXT 발견 1의 **"버그가 아니라 의도적 표본 추출 결정"이라는 원인 귀속과 충돌**. 정정 필요 |
| U4 | 트리플의 23.7%가 속성을 간선으로 표현 — 관계 타입 460종 폭발의 **독립 기여 요인** | 중대 | 타입 폭발을 "술어 자유 생성"만으로 설명한 CONTEXT §4 보강 |
| U5 | Chroma 를 읽는 리트리버는 있으나 **쓰는 코드가 없다**(주석 처리). sparse(ES, 최신) / dense(Chroma, 과거)가 다른 코퍼스를 검색 | 중대 | — |
| U6 | LLM 생성 Cypher 무검증 실행, `MATCH (n) DETACH DELETE n` 전체 삭제 | 중대 | 이관 금지 목록 |
| U7 | 파싱 실패 트리플이 계측되지 않음 (CONTEXT §6 요구사항 미구현) | 경미 | M3 참고 |

### Codex 단독 (Claude Code 의 과제 범위 밖 — 설계상 의도된 분담)

| # | 발견 | 심각도 |
|---|---|---|
| V1 | `condition_omission` 이 Graph 문제라는 전제가 미검증. 반대 가설 4개 + 반증 실험 (B7) | 치명 |
| V2 | 순환성 — Graph 를 채우는 것도 LLM. verifier 실패가 extractor 로 이동 (B8) | 치명 |
| V3 | `Required - Claimed` 집합 차분이 깨지는 지점 7종 — 패러프레이즈 / 함의 조건 / k-of-n / threshold·range / 예외 / 중첩 / claim 의 부정 (B9) | 치명 |
| V4 | operator 7종이 같은 층위가 아니다 — 논리결합자·비교제약·scope override·consistency 제약이 한 enum에 섞였다. **expression grammar 로 재설계** 제안 (B11) | 중대 |
| V5 | Graph-only 는 3-way classifier 가 아니다 — abstaining detector 로 정의하고 지표를 `trigger precision`/`coverage`/`false reject` 로 분리 (B12) | 중대 |
| V6 | "extraction 오류와 verifier 오류 분리"에 측정 설계가 없다 — **2×2 factorial** (gold/extracted graph × oracle/real checker) 필요 (B13) | 치명 |
| V7 | 평가 slice 선택 편향 + false reject 측정용 negative 사례 출처·크기·검정력 미언급 (B14) | 중대 |
| V8 | §14 역할 분담과 §16 독립검증 주의사항의 긴장. blind review 모드 제안 (B16) | 경미 |

---

## 5. 합쳐진 handoff 수정 목록 (우선순위)

두 감사의 수정 제안을 중복 제거하고 **착수 순서**로 정렬했다.

### MVP 착수 전 반드시 (블로킹)

1. **§3.1 앞에 "Graph 필요성 반증 게이트" 추가** — prompt-only / claim 분해 / oracle evidence /
   결정론적 체크리스트 4개 baseline 을 통과 조건으로. (Codex V1 + Claude Code M2)
   → 이 중 oracle evidence 는 선택이 아니라 필수 통제군 (M2)
2. **§6 에 "노드 / 리터럴 속성 / 논리식 값" 구분표 신설** — 금융 API 필드별 매핑
   (`intr_rate`, `save_trm`, `spcl_cnd`, `mtrt_int`, `etc_note`)까지 사전 결정. (M1, 양쪽 1급 수렴)
3. **§7 을 operator enum 에서 expression grammar 로 재설계** — `MUTUALLY_EXCLUSIVE` 는
   operator 가 아니라 validation constraint 로 분리. (Codex V4)
4. **§8 을 "ALL_OF MVP 의 한 연산"으로 격하** — 나머지 6종은 별도 semantics·truth table 요구. (Codex V3)
5. **§10 에 factorial evaluation matrix + extractor gold 평가 추가** — Hybrid 성능 이전에
   extractor recall ceiling 을 먼저 보고. (Codex V2·V6 + Claude Code M3)

### 저장소 정책 (신규 repo 초기 커밋에 반영)

6. **§13 에 "history 는 잇지 않되 진단 산출물은 seed artifact 로 명시 이식"** 추가 —
   사전 등록 표 구조, fixture 검증 방식, raw response logging, 실제 응답 모델 ID 기록.
   (C2, 양쪽 1급 수렴 — Codex 위험도 5위 / Claude Code 이관 자산 최상위)
7. **원문 필드와 LLM 파생 필드의 강제 분리를 스키마 불변식으로 선언** (C4 + U2)
8. **§12 에 D 항목 "그래프 수명 정책" 추가** — JIT/폐기 vs 영속, 재구축 트리거 (U1)

### 분류 정정

9. **§12 A "Neo4j 연결 코드" → B 또는 C 강등** (C1, 양쪽 1급 수렴)
10. **§12 A "LlamaIndex PGI 사용 패턴" → C 강등** — `SimpleLLMPathExtractor` 는 allowlist 를
    받지 못하므로 schema-first 는 패턴 재사용이 아니라 추출기 교체다 (Claude Code §7)
11. **§12 A "Graph serialization / query utilities"** → **D1 결정 대기** (아래 §6)
12. **§12 B 에 3항목 추가** — 육각형 리포트 프롬프트 전체 / LLM 생성 Cypher 직접 실행 /
    `app/**` 의 폐기된 모델 ID 하드코딩 (Claude Code §7)
13. **§2.1 정정** — "정규화 규칙이 없었다"를 개선 가능한 결함으로 나열하지 말 것.
    이 저장소는 정규화를 시도해 기각했고 상한이 4.5%(재등장 엔티티 42/925)로 이미 낮다 (D2)
14. **§2.3 구체화** — "Graph incremental value 를 못 측정"이 아니라
    "Graph output 이 최종 verdict 에 개입하는 contract 가 없었다" (C5)
15. **§16 에 blind review 모드 추가** (Codex V8)

### 새 프로젝트 이전에 확인할 사실 2건

16. `11951850` 기사 본문에 "정치/경제" 문자열이 실제로 없는지 — `chunks_40.json` 필요.
    U2 의 인과 귀속이 여기 걸려 있다
17. CONTEXT 발견 1의 "의도적 표본 추출" 서술을 U3(상시 `AttributeError`)에 비추어 정정할지

---

## 6. 사람이 결정할 것

| # | 항목 | 선택지 |
|---|---|---|
| Q1 | **D1 — `verify_metrics.py`/serialization 을 이관 자산으로 볼 것인가** | (a) Codex 안: 검증 후 이식, 수용 기준은 "전 지표 baseline 완전 일치" · (b) Claude Code 안: 패턴을 자산으로 승격하고 코드는 새로 씀 · (c) 조정안: 패턴 승격 + Codex 수용 기준 적용 (본 문서 권고) |
| Q2 | **D2 — handoff §2.1 을 정정할 것인가** | 정정 시 "기존 프로젝트의 한계" 서사가 바뀐다. 포트폴리오 서사(§13)와 연동 |
| Q3 | **U3 — CONTEXT 발견 1 정정 여부** | 진단 문서의 원인 귀속 하나가 코드 사실과 충돌한다. `docs/CONTEXT.md` 는 이 저장소의 진실 원본이므로 임의 수정하지 않고 남겨둠 (§7.8) |
| Q4 | **감사 브랜치 처리** | 3개 브랜치를 커밋만 하고 둘지, main 에 병합할지, PR 로 남길지. 원본 clone 은 지시대로 무변경 유지 중 |

---

## 7. 한 문단 요약

두 감사는 **다른 lane 에서 같은 지점을 가리켰다.** Codex 는 handoff 의 논리(집합 차분,
operator 층위, Graph-only 평가, 순환성)를 공격했고, Claude Code 는 기존 코드에서
그 논리가 이미 실패한 흔적을 측정했다. 가장 강한 신호는 **양쪽이 원본 문서에 없던 판정
5건에 독립적으로 도달했다는 것**이다 — 그중 두 건(노드 타입 오염이 새 스키마의 최대
위험이라는 것, 이관해야 할 자산은 코드가 아니라 사전 등록 규율이라는 것)은
handoff 를 지금 고쳐야 하는 항목이다. 가장 중요한 단독 발견은 **기존 응용 경로가 그래프를
아예 저장하지 않았다는 것**이며, 이는 스키마를 완벽히 설계해도 해결되지 않는 별개 층이므로
handoff §12 에 새 항목으로 들어가야 한다.
