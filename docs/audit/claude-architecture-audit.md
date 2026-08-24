# KAG_LlamaIndex 아키텍처·스키마·흐름 감사

> 감사자: Claude Code · 브랜치 `audit/claude-architecture` · 2026-08-20
> 대상: `KAG_LlamaIndex` @ `264fd20` (main)
> 공통 맥락: `docs/handoff/finance_rule_graph_project_handoff.md`
> 역할 분담상 이 문서는 **기존 설계의 실측 기술(記述)** 만 담당한다. handoff 문서의 가정에 대한
> 적대적 검토는 별도 리뷰어(Codex)가 독립 수행하며, 이 문서는 그 결과를 참조하지 않고 작성됐다.

---

## 0. 감사 범위와 방법

### 0.1 근거 등급

| 표기 | 의미 |
|---|---|
| `[코드]` | 파일:줄 인용. 정적 읽기로 확인 |
| `[데이터]` | 커밋된 산출물(JSON) 재계산. 재현 스크립트 있음 |
| `[이력]` | git blame / git log 로 확인 |
| `[추론]` | 위 셋으로 확정되지 않은 해석. 근거 없음을 명시 |

### 0.2 읽은 것

- 전체 애플리케이션 코드 `app/**` (9개 모듈, 1,006줄), `scripts/**` (4개, 1,171줄), `dags/`, `main_*.py` 3개
- `docs/CONTEXT.md`(721줄, 진실 원본), `docs/00-baseline-survey.md`, `docs/design-review.md`, `README.md`, `DATA.md`
- 커밋된 실측 산출물: `experiments/v0prime/graph_public.json`, `experiments/v1/graph_public.json`,
  `experiments/v{0prime,v1}/raw_completions/*.json`, `tests/fixtures/baseline_v*.json`
- git 이력 (`git log -S`, `git blame`)

### 0.3 읽지 못한 것 (한계)

이 감사는 **fresh clone 기준**이며 `.gitignore` 로 제외된 로컬 산출물이 없다. 따라서 다음은 확인 불가:

- `tests/fixtures/chunks_40.json` (Stage 1 산출물, 기사 원문) — 추출기 **입력 프롬프트 전문**을 재구성할 수 없음
- `storage_claude/property_graph_store.json` (v0 원본), `chroma_db/`, `neo4j_data/`, `rag_eval_results.csv`
- 실행 검증 없음. `.venv` 부재이며 §7.6(ETL 임의 실행 금지)에 따라 아무것도 실행하지 않았다.
  아래 "실행 불가" 판정은 전부 **정적 분석**이며, 런타임 확인이 아니다.

### 0.4 재현

이 문서가 인용하는 수치는 `scripts/audit/extraction_stats.py` 로 재계산된다
(산출물: `docs/audit/extraction_stats.json`). LLM 호출 없는 읽기 전용 스크립트다.
`docs/CONTEXT.md` 발견 20("분석 코드는 산출물과 함께 커밋되어야 한다")을 따른 것이다.

---

## 1. 아키텍처 — 선언된 구조와 실제 실행 경로

### 1.1 저장소가 주장하는 구조

`README.md:1-11` 과 `docs/CONTEXT.md:14` 는 다음 스택을 선언한다.

```
Airflow ETL · PostgreSQL · Elasticsearch · ChromaDB · Neo4j · LlamaIndex PGI · LangGraph
```

### 1.2 실측 — 하나의 파이프라인이 아니라 서로 만나지 않는 세 경로

코드에는 **독립적인 세 개의 실행 경로**가 있고, 셋은 저장소·프레임워크·진입점을 공유하지 않는다.
`main_*.py` 3개가 각각 다른 경로의 데모라는 점이 이를 그대로 보여준다 `[코드]`.

```
경로 A — LlamaIndex JIT (main_user_validation_demo.py)
  NewsRAGSolver.retrieve_similar_nodes         solver.py:46   ES(dense hybrid)
    → LLMRerank(top_n = top_k//2)              solver.py:64   ★ 문서 수 절반으로 축소
    → KnowledgeGraphManager.validate_user_article  knowledge_graph.py:160
       → graph_store.query("MATCH (n) DETACH DELETE n")  knowledge_graph.py:169  ★ 전체 삭제
       → sync_to_neo4j(...)  → Neo4j
       → LLM 프롬프트에 트리플 문자열 삽입 → 판정          knowledge_graph.py:185-194

경로 B — LangGraph + LangChain (main_hybrid_demo.py)
  NewsAppGraph.node_analyze      graph_flow.py:48   QueryDecomposer (facets 도출)
    → node_retrieve_rag          graph_flow.py:55   NewsLangChainSolver.solve
                                                     → NewsHybridRetriever (ES BM25 + Chroma)
    → node_reason_graph          graph_flow.py:64   JITGraphAnalyzer.build_and_analyze
                                                     → 메모리 PGI, 즉시 폐기
    → node_synthesize            graph_flow.py:74   f-string 결합

경로 C — Neo4j Direct Cypher (main_neo4j_demo.py)
  KnowledgeGraphManager.analyze_with_cypher  knowledge_graph.py:109
    → LLM 이 Cypher 생성 → graph_store.query → LLM 이 결과 해석

경로 D — 진단 계측 (scripts/build_index.py) ★ 유일하게 재현 가능한 경로
  Stage 1 청킹+메타데이터 → chunks_40.json
  Stage 2 CachingLLMPathExtractor → PropertyGraphIndex → persist(experiments/vN/)
```

세 응용 경로(A·B·C)의 그래프는 서로 다른 저장소에 있고, 진단 경로(D)의 그래프는 또 다른 로컬 JSON이다.
`docs/CONTEXT.md` 발견 2·3(“Neo4j는 실제 경로에 없었고 실제 동작한 그래프는 로컬 JSON”)은
코드 구조상 **필연**이었음을 확인한다 — 경로 A·C만 Neo4j를 쓰고, 측정은 경로 D에서 했다 `[코드]`.

### 1.3 정적 분석으로 확인된 실행 불가 지점

| # | 위치 | 내용 | 등급 |
|---|---|---|---|
| A1 | `app/etl/enricher.py:117` | `self.storage_manager.get_storage_context(store_type=...)` 호출. `StorageManager` 에 해당 메서드가 **없다**(`storage.py:55` 는 `get_llama_storage_context`). `git log -S"def get_storage_context"` 결과 이 이름은 **저장소 이력 전체에 한 번도 정의된 적 없다**. 2026-02-04 `9bdca4e` 이후 상시 `AttributeError` | `[코드]``[이력]` |
| A2 | `app/**` 전부 (7개 모듈) | 기본 모델이 `claude-sonnet-4-0`. `docs/CONTEXT.md` 발견 11 에 따르면 이 모델은 API에서 **404(완전 폐기)**. 인자를 명시하지 않는 모든 호출 경로가 실패 | `[코드]` |
| A3 | `app/etl/storage.py:58-132` | `Neo4jGraphStore` 를 llama-index 0.14 에 맞추기 위한 **몽키패치 6개 + Mock 클래스 1개**. `upsert_llama_nodes`/`upsert_nodes` 는 `pass`/`lambda: None` 인 무동작 스텁이고 `get_llama_nodes` 는 항상 `[]` 반환 | `[코드]` |
| A4 | `app/etl/storage.py:139-156` vs `enricher.py:120-122` | LangChain dense 리트리버는 Chroma `news_collection` 을 **읽지만**, Chroma 적재 코드는 주석 처리돼 있다. 현재 코드에 Chroma 쓰기 경로가 **존재하지 않는다** | `[코드]` |
| A5 | `app/etl/extractor.py:77` | `output_dir` 파라미터를 받고도 `base_dir="/opt/airflow"` 로 덮어써 무시한다. 컨테이너 밖에서 실행 불가 | `[코드]` |
| A6 | `app/etl/extractor.py:95` | `target_articles = articles[:5]` — 수집량이 코드에 하드코딩 | `[코드]` |

**A1 의 함의는 `docs/CONTEXT.md` 발견 1의 원인 귀속과 충돌한다.** 발견 1은 "5건만 색인"을 
"'그래프가 방대해질 것'이라는 우려에 따른 의도적 표본 추출 결정이며 버그가 아니다"로 기록했다.
그러나 Airflow DAG 는 `extractor.py`(A6: 5건 캡) → `enricher.py`(A1: 색인 단계 `AttributeError`)
두 태스크뿐이다(`dags/mk_news_dag.py:26-41`). 즉 **DAG 를 통한 색인은 애초에 성공할 수 없었다** `[코드]`.
관측된 "5건 색인"이 의도적 표본이었는지, A6 캡의 부산물인지, DAG 밖 수동 실행의 결과인지는
로컬 산출물이 없어 이 감사로는 구별할 수 없다 `[추론]`. 다만 **"의도적 결정이었고 버그가 아니다"는
서술은 A1 을 반영하지 않은 것**이므로, 새 프로젝트로 넘어가기 전 정정 대상이다.

### 1.4 아키텍처 수준의 구조적 결론

**그래프가 매 쿼리마다 새로 만들어지고 즉시 폐기된다.** `app/**` 전체에서
`storage_context.persist` 호출이 **0건**이다(진단용 `scripts/build_index.py:371` 만 persist 한다) `[코드]`.
`jit_builder.py:28` 의 `PropertyGraphIndex.from_documents` 는 메모리 인덱스를 만들고
`graph_flow.py:64-72` 는 그 결과 문자열만 상태에 담는다.

이것은 README 가 내세운 존재 이유와 직접 충돌한다. `README.md` 는 "1월 기사 A→B 투자,
3월 기사 B→C 납품 → 그래프에서 A-C 간접 관계 도출"을 KG 도입 근거로 제시한다. 그러나

- 그래프에 들어가는 문서는 그 쿼리에서 검색된 **2~5개 청크뿐**이다
  (경로 A: `solver.py:64` `top_n = top_k//2` → 기본 `top_k=4` 에서 **2개**;
   경로 B: `storage.py:158` 하이브리드 `k=5` → **5개**) `[코드]`
- 축적이 없으므로 1월 기사와 3월 기사가 같은 그래프에 있을 보장이 없다 — 둘 다 상위 2~5위에
  검색됐을 때만 우연히 성립한다 `[코드]`

즉 교차 문서 추론은 **정규화나 코퍼스 규모의 문제이기 전에, 그래프를 저장하지 않는 설계의
문제**다. `docs/CONTEXT.md` 의 진단(§4 소거법)은 경로 D(persist 하는 계측 경로)에서
수행됐으므로 이 층을 다루지 않는다. 새 프로젝트에 옮겨야 할 교훈은
**"그래프의 수명이 쿼리 수명보다 길어야 한다"** 이며, handoff §12 에 이 항목이 없다.

---

## 2. 스키마 — 무엇이 계약이었나

### 2.1 실측 스키마 전체

`experiments/v1/graph_public.json` 기준 `[데이터]`:

| 항목 | 값 |
|---|---|
| 노드 라벨 종류 | **2종** — `entity` 925개, `text_chunk` 86개 |
| 관계 라벨 종류 | **460종** / 관계 773건 (type_ratio 0.595) |
| 노드 타입 체계 | 없음. 모든 개체가 `entity` 하나 |
| 관계 방향/cardinality 제약 | 없음 |
| 관계 프로퍼티 키 | 8개 — `title, url, pub_date, news_id, category, sentiment, keywords, triplet_source_id` |

즉 **스키마는 "노드 2종 / 관계 무제한"** 이다. handoff §2.1 이 지목한 "Graph 내부에 들어오는
지식의 형식이 제한되지 않았다"는 주장은 정확하다 — 다만 "약했다"가 아니라 **타입 계약이 아예
존재하지 않았다**가 실측이다. `SimpleLLMPathExtractor` 는 허용 목록을 받지 않는다 `[코드]`.

### 2.2 리터럴이 노드가 된 비율 — 발견 19의 정량화

`docs/CONTEXT.md` 발견 19는 "노드 공간에 날짜·수치가 섞여 있다"를 사례로 기록했다. 규모를 측정했다 `[데이터]`:

| 지표 | v0'(5건) | v1(40건) |
|---|---|---|
| 리터럴 형태 엔티티 노드 | 17 / 118 = **14.4%** | 152 / 925 = **16.4%** |
| — 금액·단위 | 2 | 47 |
| — 날짜·기간 | 9 | 44 |
| — 퍼센트 | 3 | 29 |
| — 순수 숫자 | 1 | 14 |
| — 수량+단위 | 2 | 18 |
| **목적어가 리터럴인 트리플** | 17 / 94 = **18.1%** | 183 / 773 = **23.7%** |
| 양쪽 다 개체인 트리플 | 81.9% | 76.1% |

추출기 원시 출력이 이 형태를 그대로 보여준다(`experiments/v1/raw_completions/call_0001.json`) `[데이터]`:

```
(영업점, 축소율, 21%)
(업무용 고정자산 비율, 기록, 8.83%)
(감소 기간, is, 5년)
(코스닥, 급등, 7.09%)
(코스닥, 마감, 1064.41)
```

**이 트리플들은 그래프 간선이 아니라 노드의 속성이어야 한다.** `(코스닥, 마감, 1064.41)` 에서
`1064.41` 은 다른 어떤 것과도 연결될 이유가 없는 리터럴이고, 관계 라벨 `마감`·`축소율`·`기록` 은
술어가 아니라 **속성명**이다. 트리플의 약 1/4이 속성을 간선으로 잘못 표현했다는 뜻이며,
이는 관계 타입 460종 폭발의 독립적 기여 요인이다 — 속성명은 개체명만큼 다양하므로
술어 어휘가 수렴할 수 없다 `[추론, 데이터 뒷받침]`.

### 2.3 리터럴 노드가 실제로 교차 문서 다리였다

v1 에서 2개 이상 문서에 등장하는 엔티티(=브릿지 후보)는 **42개**이고, 그중 **6개(14.3%)가
리터럴**이다 `[데이터]`:

```
2025년 12월 · 2026-02-03 · 2026년 · 2026년 2월 3일 · 5월 9일 · 6.84%
```

`docs/CONTEXT.md` 발견 19가 별칭 병합 실험(v2a-manual-loose)에서 "5일"을 매개로 무관한 두 기사가
연결된 사례를 기록했는데, 그 현상은 병합 이전에 이미 존재했다 — 날짜 리터럴은
**정규화 없이도** 여러 문서에 그대로 재등장하기 때문이다. 이 감사의 추가 사실은
**"가짜 다리는 병합의 부작용이 아니라 노드 타입 부재의 직접 결과"** 라는 점이다.

### 2.4 엔티티 이름의 형태 — 발견 17의 정량화

| 지표 | v0'(5건) | v1(40건) |
|---|---|---|
| 평균 이름 길이 | 5.89자 | 6.79자 |
| 최대 | 16자 | 32자 |
| 10자 이상 | 19.5% | **20.0%** |
| 공백 포함(복합구) | 52.5% | **52.2%** |

가장 긴 것들은 문장 조각이다: `5000억달러 이상 미국산 제품 구매`, `국내 펀드시장 순자산총액`,
`Kb로 국내주식 옮기고 거래하면 쿠폰이 와르르` `[데이터]`. 엔티티 이름의 절반이 복합구라는 것은
**엔티티 경계 정의가 추출기에 위임됐다**는 뜻이고, `docs/CONTEXT.md` 발견 18(substring 별칭
매칭이 실패한 원인)의 구조적 배경이다.

### 2.5 유일하게 온전한 계약 — provenance

| 지표 | v0' | v1 |
|---|---|---|
| `triplet_source_id` 보유 관계 | 94/94 = **100%** | 773/773 = **100%** |
| 출처 단위 | 청크 (`{news_id}-chunk{idx}`) | 동일 |

`scripts/build_index.py:204-213` 에서 청크 메타데이터를 subject/object/relation 프로퍼티에
그대로 복사하기 때문이다 `[코드]`. 모든 트리플이 어느 기사 어느 청크에서 왔는지 결정론적으로
역추적된다. **이것이 이 저장소에서 새 프로젝트로 그대로 가져갈 가치가 있는 유일한 스키마 자산**이다
(단, 문제도 있다 — 2.6).

### 2.6 provenance 구현의 결함

관계·노드 프로퍼티에 문서 메타데이터 8필드가 **전량 복제**된다 `[코드][데이터]`. 결과:

- `graph_public.json` 원본은 4.1MB인데 그 대부분이 773회 반복된 동일 메타데이터다
  (`_stripped.original_size_bytes: 4139132`)
- 복제된 필드에 `summary`·`keywords` 가 포함돼 **LLM 생성물이 그래프 프로퍼티에 섞인다**.
  `scripts/strip_graph.py` 가 공개본에서 `summary` 를 지우는 것은 그 오염을 사후에 걷어내는 조치다
- 출처 단위가 **청크**다. 문장/문단 단위가 아니므로 "이 트리플이 어느 문장에서 왔나"는 추적 불가

새 프로젝트에서는 provenance 를 **참조(source_id)** 로 두고 문서 메타데이터를 별도 테이블에
분리해야 한다. 값 복제는 규모에서 비용이고, LLM 생성 필드 혼입 경로다 `[추론]`.

---

## 3. Extraction flow

### 3.1 실제 경로 (진단 경로 D 기준 — 유일하게 재현 가능)

```
result/airflow/*.json                                 크롤 산출물
  │  build_index.py:54  load_unique_articles          news_id 중복 제거
  ▼
[Stage 1]  build_index.py:81
  extract_metadata (LLMTextCompletionProgram)         ← LLM 호출 #1 (기사당 1회)
    → NewsMetadata{category, sentiment, keywords[5], summary}
  Document(text=본문, metadata={8필드})
  SemanticSplitterNodeParser(buffer_size=1, pct=95)   ← OpenAI 임베딩 사용
    → chunks_40.json  (40건 → 86청크)
  ▼
[Stage 2]  build_index.py:321
  TextNode(id_=f"{news_id}-chunk{idx}")               ← 캐시 키가 되는 결정론적 ID
  CachingLLMPathExtractor._aextract  (build_index.py:171)
    캐시 히트 → 재사용 / 미스 → LLM 호출 #2
    text = node.get_content(metadata_mode=MetadataMode.LLM)   ★ 3.2
    llm.apredict(extract_prompt, max_knowledge_triplets=max_paths_per_chunk)
    parse_fn(응답)  → [(subj, rel, obj), ...]
    EntityNode(name=subj, properties=청크메타데이터 전체)      ★ 2.6
  → PropertyGraphIndex(nodes=..., kg_extractors=[...])
  → persist(experiments/vN/)
```

**계측이 잘 되어 있다.** `instrument_anthropic_client`(`build_index.py:222`)가
`llm._aclient.messages.create` 를 감싸 모든 호출의 `stop_reason`·토큰 수·응답 원문·**실제 응답
모델 ID** 를 `raw_completions/call_NNNN.json` 에 남긴다 `[코드]`. 발견 9(토큰 상한 가설)가
실측으로 폐기될 수 있었던 이유이고, 발견 11(모델 수명 종속)에 대한 방어책이다.

### 3.2 메타데이터 오염 — 발견 10을 "가능성"에서 "실증"으로

`docs/CONTEXT.md` 발견 10은 "LLM 생성 요약이 추출기 입력에 포함되며 요약에서 파생된 트리플이
섞였을 **가능성**이 있으나 조건 고정을 우선해 변경하지 않았다"로 기록돼 있다.

`build_index.py:181` 이 `metadata_mode=MetadataMode.LLM` 을 쓰고
`excluded_llm_metadata_keys` 가 저장소 전체에서 **한 번도 설정되지 않으므로**(grep 0건),
`title·url·pub_date·news_id·category·sentiment·keywords·summary` 8필드가 기사 본문과 함께
추출 프롬프트에 들어간다 `[코드]`.

**결과가 그래프에 남아 있다.** 메타데이터 필드에서만 파생될 수 있는 트리플 **15건**(773건의 1.94%),
9개 청크 / **7개 문서(40건 중 17.5%)** 에서 발생했다 `[데이터]`:

```
(기사, 감정, 긍정)            11951848-chunk0     ← sentiment 필드
(기사, 카테고리, 경제)         11951848-chunk0     ← category 필드
(기사, 발행일, 2026년 2월 3일)  11951848-chunk0     ← pub_date 필드
(Article, Has sentiment, 부정) 11951954-chunk0
(Article, Category, 정치)      11951954-chunk0
(기사, Written by, 원호섭 특파원) 11951770-chunk1
(Sentiment, Is, 긍정)          11951900-chunk0
(기사 카테고리, Is, 정치/경제)   11951850-chunk0     ★
...
```

`긍정`·`부정`·`기사` 가 엔티티 노드로 존재하고 그중 `긍정`·`부정`·`기사` 는 2개 이상 문서에
등장하는 **브릿지 42개에 포함**된다 `[데이터]`.

### 3.3 새 인과 연결 — 메타데이터 오염이 §4 "가짜 다리"의 출발점이었다

`docs/CONTEXT.md` §4(전이 경로 추적)는 v2a-hi 판정을 무효화한 대표 경로를 이렇게 기록한다.

```
경제(34) → 서울:  경제 → 정치/경제 → 정치 → 서울대 정치학과 → 서울
```

이 경로의 두 번째 노드 `정치/경제` 의 출처는 트리플
`(기사 카테고리, Is, 정치/경제)` @ `11951850-chunk0` 이다 `[데이터]`.
`정치/경제` 는 **기사 본문의 개체가 아니라 `enricher` 가 생성한 `category` 메타데이터 값**이다.

즉 발견 10(메타데이터 오염)과 발견 17(긴 서술구가 가짜 다리를 만듦)은 별개 발견으로 기록돼
있지만, **최대 클러스터의 다리 하나는 전자가 후자를 만든 사례**다. `docs/CONTEXT.md` 는 이 연결을
기록하지 않았다. 함의: 발견 10을 "후속 개선 대상"으로 미룬 결정이, 결과적으로 v2a-hi 무효화
사유의 일부를 만들었다 `[데이터 + 추론]`.

반증 조건: `11951850` 기사 본문에 "정치/경제"라는 문자열이 실제로 존재하면 이 귀속은 틀린다.
`chunks_40.json` 이 로컬에 없어 이 감사에서는 확인 불가 — **새 프로젝트 이전에 확인할 항목**.

### 3.4 추출 계약의 부재가 남긴 구체적 구멍

| 계약 항목 | 현재 상태 | 근거 |
|---|---|---|
| 허용 노드 타입 | 없음 (`entity` 단일) | `[데이터]` |
| 허용 관계 타입 | 없음 (460종 자유 생성, 70.9% 단발성) | `[데이터]` |
| 출력 언어 | 없음 — 한국어 기사에 **영문 라벨 83종** | `[데이터]` |
| 리터럴 vs 개체 구분 | 없음 (2.2) | `[데이터]` |
| 엔티티 경계 | 없음 (2.4, 절반이 복합구) | `[데이터]` |
| 파싱 실패 처리 | `except ValueError: triples = []` — 조용히 버림. **버려진 비율이 기록되지 않는다** | `[코드]` build_index.py:189 |
| 청크당 트리플 상한 | `max_paths_per_chunk` 기본값에 의존. 스크립트가 명시하지 않음 | `[코드]` |
| 스키마 검증 | 없음 | — |

마지막 줄이 중요하다. `docs/CONTEXT.md` §6 는 "버려진 트리플 비율을 로그로 남기세요. 20% 초과면
온톨로지가 너무 좁습니다"라고 요구하지만, `build_index.py:189` 의 `except ValueError` 는
카운터를 올리지 않는다 — **요구된 지표가 계측되지 않는다** `[코드]`.

---

## 4. Retrieval flow

### 4.1 세 개의 리트리버 구현, 서로 다른 저장소

| 구현 | 위치 | sparse | dense | 융합 |
|---|---|---|---|---|
| `NewsRAGSolver` | `solver.py:79` | ES 내장 hybrid (`alpha=0.5`) | ES dense | ES 위임 |
| `HybridRetriever` | `solver.py:16` | `BM25Retriever` | `VectorIndexRetriever` | 단순 합집합 (점수 폐기) |
| `NewsHybridRetriever` | `hybrid_retriever.py:6` | ES BM25 | **Chroma** | RRF (`c=60`) |

`HybridRetriever`(`solver.py:16-32`)는 두 결과를 dict 로 합치고 **랭킹 정보를 전부 버린다** —
`list(all_nodes_dict.values())` 의 순서는 삽입 순서이므로 벡터 결과가 항상 앞에 온다 `[코드]`.
정의된 클래스지만 같은 파일 어디에서도 사용되지 않는다(사용처 grep 0건) — 죽은 코드다.

`NewsHybridRetriever` 는 dense 쪽을 Chroma 에서 읽는다(`storage.py:147-156`). 그런데
**현재 코드에 Chroma 적재 경로가 없다** — `enricher.py:120-122` 에서 주석 처리됨 `[코드]`.
`docs/CONTEXT.md` 는 `chroma_db` 31M 이 로컬에 남아 있다고 기록하므로, 이 리트리버는
**현재 ETL 이 채우지 않는 과거 저장소를 읽고 있다**. 두 벡터 저장소의 내용이 다르면
sparse(ES, 최신) 와 dense(Chroma, 과거) 가 서로 다른 코퍼스를 검색한다 `[추론]`.

### 4.2 검색 결과가 그래프 크기를 결정한다 (구조적 상한)

```
경로 A: top_k=4 → LLMRerank(top_n = top_k//2 = 2) → 그래프 입력 2청크   solver.py:64,87
경로 B: 하이브리드 k=5              → 그래프 입력 5청크                storage.py:158
```

`docs/CONTEXT.md` 의 진단은 v0'(5건/10청크)에서 컴포넌트 33개, v1(40건/86청크)에서 224개를
관측했다. **응용 경로가 실제로 그래프에 넣는 청크는 2~5개**이므로, 운영 시 그래프는 진단이
측정한 것보다 한 자릿수 작다 `[코드]`. 브릿지가 생길 확률은 그만큼 더 낮다.

### 4.3 리랭커가 그래프 입력을 줄인다

`LLMRerank(choice_batch_size=5, top_n=top_k//2)` 는 LLM 판정으로 문서를 절반 버린다
(`solver.py:64`, `solver.py:87`) `[코드]`. 이는 **정밀도를 위해 리콜을 버리는 선택**인데,
교차 문서 그래프 추론은 리콜에 의존한다. 관련 문서 중 절반이 그래프에 들어가지 못하면
"여러 기사에 흩어진 사실을 잇는다"는 목적과 직접 상충한다 `[추론]`.

이 상충은 새 프로젝트에도 그대로 온다 — handoff §3.3 이 언급한
`INSUFFICIENT ↔ UNSUPPORTED` 과대판정은 **증거 리콜 문제**이고, 리랭커로 증거를 잘라내는
파이프라인은 그 실패를 증폭한다.

### 4.4 RRF 구현 세부

`hybrid_retriever.py:23-35` `[코드]`:

- 문서 키가 `doc.metadata.get("news_id", doc.page_content[:50])` — **news_id 가 문서 단위**이므로
  같은 기사의 서로 다른 청크가 **하나로 축약**된다. 청크 단위 검색이 문서 단위로 붕괴한다
- sparse 루프는 `doc_scores[doc_id] = {...}` 로 **덮어쓴다**. sparse 결과 내 중복(같은 기사 다른 청크)이
  있으면 마지막 것만 남고 앞의 순위 점수는 소실된다. dense 루프만 `+=` 누적을 한다
- RRF 상수 `c=60` 에 `rank` 0-기반 → `1/(rank+60)`. 표준형(`1/(k+rank+1)`)과 상수만 다르므로
  순위 왜곡은 아니다 — 이 항목은 결함이 아니다

---

## 5. Reasoning flow — 그래프가 추론에 개입하는가

### 5.1 최종 리포트는 문자열 결합이다

```python
# app/rag/graph_flow.py:77
report = f"### [RAG 분석]\n{state['rag_analysis']}\n\n### [심층 관계 분석]\n{state.get('graph_reasoning', 'N/A')}"
```

RAG 분석과 그래프 분석이 **각각 독립 LLM 호출로 생성된 뒤 붙는다** `[코드]`. 두 결과가 모순되면
조정하는 단계가 없고, 그래프 결과가 RAG 결과를 수정할 수 없다.
`docs/CONTEXT.md` §3 "리포트 생성: f-string 결합. 그래프가 추론에 개입 못 함"은 정확하다.

### 5.2 조건부 분기가 상수다

```python
# graph_flow.py:53
return {"facets": [...], "need_graph": True}   # 우선 True 고정
```

`should_use_graph`(`graph_flow.py:80`)는 `need_graph` 를 읽지만 그 값은 항상 `True` 다 `[코드]`.
LangGraph 조건부 엣지가 선언돼 있으나 분기는 일어나지 않는다 — **"그래프 없이 실행"하는
경로가 코드에 존재하지 않는다**.

이것이 handoff §2.3("Graph 기여도를 독립적으로 측정하지 못함")의 코드 차원 원인이다.
ablation 을 하려면 그래프를 끄는 스위치가 필요한데, `solver.py:69` 의 `use_graph` 플래그는
경로 A에만 있고 LangGraph 경로(B)에는 없다 `[코드]`. 평가 코드(`evaluator.py`)는
`NewsLangChainSolver.solve` 만 호출하므로 **그래프 경로를 한 번도 지나지 않는다**(`evaluator.py:66`) `[코드]`.
즉 `rag_eval_results.csv` 95행은 RAG 평가이고 그래프 평가가 아니다.

### 5.3 "육각형 지표"는 측정이 아니라 자기 보고다

두 개의 구현이 있고 둘 다 문제가 있다 `[코드]`:

**(a) LLM 이 자기 점수를 계산한다** — `jit_builder.py:40-63`. 프롬프트가
"사실성 = 매칭 엔티티 수 / 답변 내 전체 엔티티 수 × 100" 같은 공식을 **자연어로 지시하고
LLM 이 그 산수를 수행해 출력**한다. 그래프에서 계산된 값이 아니다.
검증도, 자리수 확인도 없다. (프롬프트 자체에 오타 `반드시 지커 답변하세요` 도 있다 — `jit_builder.py:50`)

**(b) 6개 지표 중 3개가 LLM 주관 점수다** — `knowledge_graph.py:39-107`.
`connectivity`·`depth`·`density` 는 Cypher/산술로 계산하지만
`factuality`·`originality`·`insight` 는 `llm.complete("0~100점으로 평가하세요")` 의 결과를
`int()` 로 파싱한다. 파싱 실패 시 `except Exception` 이 전부를 삼키고 0을 남긴다
(`knowledge_graph.py:104-106`).
게다가 `depth = min(100, paths*5)` 인데 쿼리에 `LIMIT 1` 이 있어(`knowledge_graph.py:74`)
`count(path)` 는 항상 전체 경로 수 1행을 반환한다 — 지표 의미가 불명확하다.

새 프로젝트의 handoff §10 지표 목록은 전부 결정론적 지표다. **이 저장소가 남긴 교훈은
"LLM 이 자기 성능 점수를 출력하게 하면 지표가 아니다"** 이고,
`docs/CONTEXT.md` §6("지표 — 전부 결정론적. LLM judge 불필요")는 이 실패에 대한 정정이다.

### 5.4 파괴적 연산

`knowledge_graph.py:169` — `validate_user_article` 는 시작할 때
`graph_store.query("MATCH (n) DETACH DELETE n")` 로 **Neo4j 전체를 삭제**한다 `[코드]`.
"깨끗한 대조를 위해"라는 주석이 있지만, 이는 그래프를 누적 지식 베이스로 쓰는 설계와 모순이며
`docs/CONTEXT.md` 발견 2(Neo4j 에 수집 기사와 무관한 데모 데이터 27노드만 남아 있었다)의
유력한 설명이다 `[추론]`.

### 5.5 Cypher 생성 경로의 취약점

`analyze_with_cypher`(`knowledge_graph.py:109-157`) `[코드]`:

- LLM 이 생성한 Cypher 를 **문자열 정리만 하고 그대로 실행**한다(```` ``` ```` 제거만).
  화이트리스트·read-only 검증이 없다. LLM 이 `DELETE` 를 생성하면 실행된다
- 프롬프트가 `"현재 데이터셋이 작으므로 count(*) > 1 같은 엄격한 필터링은 피하고,
  최대한 많은 관계를 보여줄 수 있도록 작성하세요"` 라고 지시한다(`:120`) —
  **데이터 부족을 결과 부풀리기로 보정하도록 프롬프트에 명시**돼 있다
- 실패 시 예외 문자열을 반환하는데(`:157`) 성공 시엔 dict 를 반환한다. 호출자가 타입을 구분하지 않으면
  조용히 오작동한다

---

## 6. handoff §2 주장과 실제 코드 대조

| handoff 주장 | 실측 판정 | 근거 |
|---|---|---|
| §2.1 "LLM이 Entity/Relation을 비교적 자유롭게 추출했다" | **성립 — 다만 과소 서술.** "비교적 자유"가 아니라 타입 계약이 부재. 노드 라벨 1종, 관계 460종, 리터럴 16.4% | 2.1~2.4 |
| §2.1 "어떤 Entity를 독립 Node로 허용할지 계약이 약했다" | **성립.** 엔티티 이름 52%가 복합구, 20%가 10자 이상 | 2.4 |
| §2.1 "표기 변형 정규화 규칙이 없었다" | **성립하나 handoff의 함의는 과대.** 이 저장소는 정규화를 실제로 시도해 **기각**했다 — 별칭 후보 40쌍 표본에서 유의미한 별칭 0건, 재등장 엔티티 자체가 4.5%(42/925) | `docs/CONTEXT.md` 발견 15·18 |
| §2.2 "schema/ontology/constraint가 뒤늦게 붙었다" | **성립.** 스키마 제약 추출기 도입이 v5 후속으로 이관됨 | `docs/CONTEXT.md` §9 |
| §2.3 "Graph 기여도를 독립 측정하지 못함" | **성립. 코드 차원 원인 특정됨** — `need_graph=True` 고정, LangGraph 경로에 ablation 스위치 없음, `evaluator.py` 가 그래프 경로를 호출하지 않음 | 5.2 |
| §1.1 흐름도 "뉴스 수집 → 검색 → 추출 → **Neo4j/PGI** → 비교 → 모순 분석" | **부분 오류.** Neo4j는 실제 측정 경로에 없었고(발견 2), "모순 분석"에 해당하는 결정론적 단계가 코드에 없다 — 모순 판정도 LLM 프롬프트 한 줄(`knowledge_graph.py:190`) | 1.2, 5.1 |

### handoff 가 지목하지 않은, 코드에 실재하는 문제

1. **그래프가 저장되지 않는다** (1.4) — handoff §2 전체가 "그래프 내용의 품질" 문제로 프레이밍돼
   있으나, 응용 경로는 그래프를 축적하지 않는다. 스키마를 완벽히 고정해도 이 층은 해결되지 않는다
2. **메타데이터 오염이 그래프에 실제로 들어갔다** (3.2, 3.3) — handoff 에 항목이 없다
3. **리터럴/속성이 간선으로 표현된다** (2.2) — handoff §2.1 목록에 "무엇이 노드이고 무엇이 속성인가"가 없다
4. **평가 코드가 그래프를 지나지 않는다** (5.2) — §2.3 의 원인이 측정 설계가 아니라 코드 배선임
5. **버려진 트리플이 계측되지 않는다** (3.4)
6. **LLM 생성 Cypher 무검증 실행 / 전체 삭제 연산** (5.4, 5.5)

---

## 7. handoff §12 A/B/C/D 분류의 실측 재판정

### A. "재사용 가능한 것" — 3항목 중 2항목 하향

| handoff 항목 | 재판정 | 근거 |
|---|---|---|
| Neo4j 연결 코드 | **A → B (재사용 금지)** | `storage.py:58-132` 는 llama-index 0.14 호환용 몽키패치 6개 + Mock 클래스이며 `upsert_nodes`/`upsert_llama_nodes` 가 무동작 스텁이다. 이식하면 "저장한 줄 알았는데 안 된" 상태를 물려받는다. 발견 2(관계 프로퍼티 전부 `{}`)의 유력한 원인 |
| LlamaIndex PGI 사용 패턴 | **A → C (발전시킬 것)** | `SimpleLLMPathExtractor` 는 허용 목록을 받지 못한다. handoff 가 요구하는 schema-first 는 추출기 **교체**를 뜻하며 패턴 재사용이 아니다(이 저장소 스스로 v5로 이관) |
| Graph serialization / query utilities | **A 유지 (승격)** | `scripts/strip_graph.py`, `scripts/verify_metrics.py` 는 실제 자산이다 (7.1) |
| 실험 코드 일부 | **A 유지 (승격)** | `scripts/build_index.py` 의 Stage 분리·캐시·계측 (7.1) |

### B. "재사용하면 안 되는 것" — 전부 성립, 3항목 추가

handoff 의 4항목(자유도 높은 추출, News 도메인 스키마, 평가 없는 Graph algorithm,
contract 없는 Triplet extraction)은 모두 성립한다. 추가:

- **육각형 리포트 전체** (5.3) — LLM 자기 보고 점수. 프롬프트 문자열째로 옮기면 안 된다
- **LLM 생성 Cypher 직접 실행** (5.5)
- **`app/**` 의 모델 기본값** (A2) — 폐기된 모델 ID가 7개 모듈에 하드코딩

### C. "설계적으로 발전시킬 것" — handoff 목록 유지, 2항목 추가

handoff 의 6항목(엔티티 정규화, 관계 제약, 스키마 검증, 데이터 품질, provenance,
추출 신뢰도, failure taxonomy)에 추가:

- **노드 vs 속성 구분** (2.2) — 리터럴은 관계의 속성으로. handoff §6 스키마 후보에서
  `Rate`·`Term` 이 노드인 점은 이 저장소가 `1064.41` 을 노드로 만든 것과 같은 층의 결정이다
- **provenance 의 저장 방식** (2.6) — 값 복제 → 참조로. 출처 단위를 문장으로

### D. "새로 만들 것" — handoff 목록 유지, 1항목 추가

- **그래프 수명 정책** (1.4) — JIT/폐기 vs 영속. handoff §5~§8 은 스키마만 말하고
  그래프가 언제 만들어지고 얼마나 사는지를 말하지 않는다. 이 저장소가 실패한 층이므로
  새 프로젝트의 명시적 결정 항목이어야 한다

---

## 8. 새 프로젝트로 이관할 자산 (실측 근거 있는 것만)

### 8.1 그대로 가져갈 것 — 4개

| 자산 | 위치 | 왜 |
|---|---|---|
| **2단계 분리 (Stage 1 / Stage 2)** | `build_index.py:81,321` | 청킹·메타데이터 LLM 을 측정 대상에서 제거해 변동 요인을 하나로 줄인다. 새 프로젝트의 ablation(§10)에 그대로 필요하다 |
| **provenance 완비 캐시** | `build_index.py:158-219` | `{model_id, extracted_at, provenance, triples}` 구조. `node_id` 결정론적 키. 재현성 실패(발견 11·20)에 대한 직접 방어 |
| **원시 응답 계측** | `build_index.py:222-301` | 모든 LLM 호출의 `stop_reason`·토큰·**실제 응답 모델 ID** 저장. 발견 9를 실측으로 폐기시킨 장치 |
| **지표 재계산 스크립트 패턴** | `verify_metrics.py`, `strip_graph.py` | 산출물과 계산 코드를 함께 커밋. 발견 20의 교훈을 코드로 구현한 것 |

### 8.2 방법론 자산 — 코드가 아니라 규율

이 저장소의 진단이 남긴 가장 이식 가치 높은 것은 코드가 아니다 `docs/CONTEXT.md` 발견 16:

- **사전 등록** — 판정 기준을 실행 전에 날짜와 함께 기록. 이 저장소에서 기준이 3번 정정됐고,
  기록이 있었기 때문에 "무엇이 언제 왜 틀렸는지" 지목 가능했다
- **예약된 반증 조건** — 발견 12(고립은 내용 속성)가 v2 이전에 기록돼 있었기에
  v2a-hi 의 `isolated_doc_ratio 0.25→0.00` 을 사후 합리화 없이 오병합으로 판정할 수 있었다
- **처치의 정의를 성과로 읽지 않기** — `entities_per_doc` 을 v1→v2 구간에서 무효 지표로
  사전 선언한 것. handoff §10 의 "Schema/Extraction Valid Rate" 는 같은 위험이 있다
  (추출 유효율이 곧 처치이면 성과 지표가 아니다)

**handoff §13("기존 Git history를 가져오지 않는다")은 코드 이관 정책으로는 타당하나, 위
방법론 자산은 코드가 아니라 문서에 있다.** `docs/CONTEXT.md`·`docs/design-review.md` 를
새 저장소의 `docs/decisions/` 선례로 명시 인용하지 않으면 발견 16·20 을 다시 배우게 된다 `[추론]`.

### 8.3 이관하면 안 되는 것

- `app/graph/knowledge_graph.py` 전체 (몽키패치·전체삭제·무검증 Cypher·LLM 자기채점)
- `app/graph/jit_builder.py` 의 육각형 프롬프트
- `app/etl/storage.py:58-132` 의 Neo4j 호환 레이어
- 세 개의 중복 리트리버 구현 — 어느 것도 완결되지 않았다 (4.1)

---

## 9. 이 감사가 확정하지 못한 것

1. **A1(`get_storage_context` 부재)의 실제 영향 범위** — 색인이 어떤 경로로 5건 들어갔는지는
   로컬 산출물 없이 확정 불가. `docs/CONTEXT.md` 발견 1의 "의도적 결정" 서술과의 충돌은
   지적했으나 해소하지 못했다
2. **3.3 의 `정치/경제` 귀속** — 기사 본문에 해당 문자열이 없다는 것을 `chunks_40.json` 으로
   확인해야 확정된다
3. **`SimpleLLMPathExtractor` 의 실제 프롬프트 전문과 `max_paths_per_chunk` 기본값** —
   `.venv` 부재로 라이브러리 소스를 읽지 못했다. `raw_completions` 의 입력 토큰 수(610)로
   간접 추정만 했다
4. **Chroma 와 ES 의 내용 차이** (4.1) — 두 저장소가 로컬에 없어 실제 불일치 규모 미확인
5. **런타임 검증 전무** — §7.6 준수. 모든 "실행 불가" 판정은 정적 분석이다

---

## 10. 요약 — 한 문장씩

1. 파이프라인은 하나가 아니라 서로 만나지 않는 네 경로이고, 측정은 그중 하나(진단용 스크립트)에서만 재현된다.
2. 스키마는 "약했다"가 아니라 **없었다** — 노드 라벨 1종, 관계 460종, 리터럴이 노드의 16.4%.
3. 트리플의 23.7%가 속성을 간선으로 표현했고, 이것이 관계 타입 폭발의 독립 기여 요인이다.
4. 교차 문서 다리 42개 중 6개가 날짜·수치 리터럴이었다 — 가짜 다리는 병합의 부작용이 아니라 노드 타입 부재의 결과다.
5. LLM 이 생성한 메타데이터가 추출 프롬프트에 섞여 그래프에 트리플 15건을 남겼고, 그중 하나(`정치/경제`)는 v2a-hi 판정을 무효화한 클러스터의 다리였다.
6. 응용 경로는 그래프를 저장하지 않는다 — README 가 내세운 "1월+3월 기사 연결"은 코드 구조상 불가능했다.
7. 그래프를 끄는 스위치가 없어 ablation 이 구조적으로 불가능했고, 평가 코드는 그래프 경로를 지나지 않는다.
8. 온전한 것은 provenance(100%)와 진단 계측이며, 새 프로젝트가 가져갈 것은 이 둘과 사전 등록 규율이다.
