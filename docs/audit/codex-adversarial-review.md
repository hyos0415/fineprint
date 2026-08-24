# Codex 적대적 리뷰: Finance Rule / Constraint Graph handoff

## 검토 범위

작업 루트는 `/Users/janghyoseong/orca/kag-audit-codex`이며, 구현·테스트·ETL·LLM 호출은 수행하지 않았다. 정적 파일 읽기와 `rg`/`jq` 수준의 JSON 조회만 사용했다.

읽은 파일:

- `docs/handoff/finance_rule_graph_project_handoff.md`
- `docs/CONTEXT.md`
- `docs/00-baseline-survey.md`
- `docs/design-review.md`
- `app/graph/jit_builder.py`
- `app/graph/knowledge_graph.py`
- `app/etl/enricher.py`
- `app/etl/extractor.py`
- `app/etl/storage.py`
- `app/rag/graph_flow.py`
- `app/rag/hybrid_retriever.py`
- `app/rag/solver.py`
- `app/rag/decomposer.py`
- `app/rag/evaluator.py`
- `scripts/build_index.py`
- `scripts/normalize.py`
- `scripts/verify_metrics.py`
- `experiments/v0prime/graph_public.json`
- `experiments/v1/graph_public.json`
- `tests/fixtures/baseline_v0prime.json`
- `tests/fixtures/baseline_v1.json`
- `tests/fixtures/baseline_v2a-manual-loose.json`
- `tests/fixtures/entity_hapax.json`
- `tests/fixtures/entity_length_reappearance.json`
- `tests/fixtures/normalize_v1_lo_dryrun.json`
- `tests/fixtures/normalize_v1_hi_dryrun.json`

읽지 않은 것:

- `/Users/janghyoseong/orca/kag-audit-claude`, `/Users/janghyoseong/orca/KAG_LlamaIndex`는 지시대로 접근하지 않았다.
- `docs/archive/`는 `docs/CONTEXT.md`의 금지 안내에 따라 읽지 않았다.
- `finance_verifier` 원 저장소와 실제 금융상품 스냅샷/canonical data는 이 worktree에 없어 확인 못 함. 따라서 `condition_omission`이 실제 몇 건·어떤 분포로 발생했는지는 handoff 문서만으로는 검증하지 못했다.

## 총평

handoff §2의 기존 KAG 설계 비판은 큰 방향에서 코드와 실측 데이터에 의해 지지된다. 자유 스키마 추출, 관계 타입 폭발, 엔티티/서술구/날짜 노드 오염, Neo4j 미사용, 평가 재현성 실패는 모두 실제 근거가 있다.

그러나 handoff는 새 Graph 프로젝트의 전제에는 훨씬 관대하다. 특히 `condition_omission`을 Graph 문제로 둔 결정, LLM 기반 조건 추출의 순환성, `Required - Claimed` 집합 차분, Graph-only 평가, 신규 저장소 정책은 아직 반증 실험과 실패 기준이 부족하다. 기존 프로젝트에서 확인된 실패 양상이 새 프로젝트 앞단으로 이동할 위험이 있다.

## A. 기존 KAG 설계 주장 검토

### 1. 자유 스키마 추출 문제는 지지된다

- 근거 등급: [코드확인], [데이터확인]
- 심각도: 치명
- 반대 주장: handoff §2.1의 "자유도가 높은 Entity / Triplet 추출" 비판은 과장이 아니다. `knowledge_graph.py`는 `SimpleLLMPathExtractor(llm=self.llm, num_workers=2)`를 schema나 relation allowlist 없이 사용한다(`app/graph/knowledge_graph.py:27-35`). `jit_builder.py`도 동일하게 `SimpleLLMPathExtractor`로 JIT 그래프를 만든다(`app/graph/jit_builder.py:21-32`). v1 실측은 관계 773건에 고유 관계 타입 460종, rel_type_ratio 0.5951이며, 1회만 등장한 relation type이 326/460이다(`tests/fixtures/baseline_v1.json`, `experiments/v1/graph_public.json` jq 집계). 상위 20종 커버리지는 21.3%에 불과하다.
- 반증 조건: schema/allowlist를 적용한 동일 코퍼스 재추출에서 relation type 수가 사전 정의 범위로 제한되고, 미분류/거부율과 최종 검증 성능이 함께 보고되면 이 지적은 약해진다.
- handoff 수정 제안: §2.1을 유지하되 "relation 이름 변형" 수준이 아니라 "LLM 술어 자유 생성으로 인한 장기 꼬리 분포"라고 명시하고, 새 프로젝트의 relation/operator allowlist 위반 시 처리 규칙을 §6에 추가하라.

### 2. handoff가 덜 강조한 문제: 노드 타입 오염이 핵심 실패다

- 근거 등급: [코드확인], [데이터확인]
- 심각도: 치명
- 반대 주장: handoff §2는 "Entity/Relation 자유도"를 말하지만, 실제 좌초 위험은 더 구체적이다. 기존 그래프는 엔티티 노드 공간에 사건, 속성, 긴 서술구, 날짜, 수치가 들어간다. `experiments/v1/graph_public.json`에는 `코스피 5000 특별위원회`, `최대 400만원 쿠폰 혜택`, `비대면 또는 은행연계 계좌 보유 개인고객`, `2026년 3월 7일∼7월 5일` 같은 노드가 있다. `docs/CONTEXT.md`도 발견 14에서 `정성국 의원직 사퇴`, `한동훈 제명 재고`, `노점 영업중단`을 엔티티가 아닌 사건·속성으로 판정하고(`docs/CONTEXT.md:158-160`), 발견 19에서 날짜·수치는 노드가 아니라 관계 리터럴 속성이어야 한다고 결론낸다(`docs/CONTEXT.md:177-180`).
- 반증 조건: 새 금융 Graph에서 `Condition`, `Rate`, `Term`, 날짜, 금액, 기간이 노드가 되어도 무의미한 연결·오병합·false reject가 증가하지 않는다는 ablation이 나오면 이 지적은 틀린다.
- handoff 수정 제안: §6의 노드 후보에서 `Rate`, `Term`, 숫자/날짜성 `Condition`을 first-class node로 둘 때의 기준을 추가하라. "노드로 둘 것 / 리터럴 속성으로 둘 것 / 논리식 내부 값으로 둘 것"의 구분표가 필요하다.

### 3. Neo4j 연결 코드는 "재사용 가능"으로 보기 어렵다

- 근거 등급: [코드확인], [데이터확인]
- 심각도: 중대
- 반대 주장: handoff §12 A는 "Neo4j 연결 코드"를 재사용 가능으로 분류하지만, 실제 코드는 호환성 monkeypatch와 stub이 많다. `StorageManager.get_neo4j_graph_store()`는 `supports_vector_queries`, `supports_structured_queries`를 동적으로 붙이고(`app/etl/storage.py:65-70`), `MockNode`를 만들어 `store.get`을 monkeypatch한다(`app/etl/storage.py:71-85`). `upsert_llama_nodes`, `upsert_nodes`는 no-op이고(`app/etl/storage.py:105-118`), `upsert_relations`는 relation property 없이 `store.upsert_triplet(s, r, o)`만 호출한다(`app/etl/storage.py:119-130`). 실측 Neo4j는 27노드/18관계의 수집 기사와 무관한 데모 데이터이며 관계 property가 `{}`라고 조사되어 있다(`docs/00-baseline-survey.md:128-150`). `docs/CONTEXT.md` 발견 2도 Neo4j가 실제 경로에 없었다고 한다(`docs/CONTEXT.md:104-105`).
- 반증 조건: 같은 코드가 금융 도메인의 provenance, schema validation, relation properties, migration/cleanup을 보존하며 Neo4j에 round-trip 저장·조회되는 통합 테스트가 있으면 "재사용 가능" 분류를 회복할 수 있다.
- handoff 수정 제안: §12 A의 "Neo4j 연결 코드"를 C 또는 B로 내리고, 재사용 가능 범위를 "환경 변수명과 LlamaIndex GraphStore 연결 시도 기록" 정도로 축소하라.

### 4. Graph serialization / query utilities 재사용 가능성은 제한적이다

- 근거 등급: [코드확인], [데이터확인]
- 심각도: 중대
- 반대 주장: 로컬 JSON 저장소는 provenance가 잘 붙은 장점이 있지만, utility라기보다 진단 과정에서 사후 안정화된 산출물이다. `verify_metrics.py`는 baseline 수치가 커밋되지 않은 대화형 코드로 산출되었고, 사후 구현은 `cross_doc_path_ratio`에서 0.45% 오차를 허용한다고 명시한다(`scripts/verify_metrics.py:1-35`, `scripts/verify_metrics.py:230-236`). `docs/CONTEXT.md` 발견 20도 같은 재현성 실패를 지적한다(`docs/CONTEXT.md:184-192`).
- 반증 조건: graph serialization 생성 코드, strip/public 변환, metric 계산, fixture 검증이 하나의 재현 가능한 명령으로 고정되고 모든 지표가 baseline과 완전 일치하면 재사용 가능하다고 볼 수 있다.
- handoff 수정 제안: §12 A의 "Graph serialization / query utilities"를 "진단 패턴과 일부 fixture 구조는 재사용, 기존 utility 코드는 검증 후 이식"으로 수정하라.

### 5. handoff가 지목하지 않은 기존 문제: LLM 산출물이 다시 추출 입력에 들어간다

- 근거 등급: [코드확인], [추론]
- 심각도: 중대
- 반대 주장: `enricher.py`는 LLM으로 `category`, `sentiment`, `keywords`, `summary`를 만들고(`app/etl/enricher.py:45-59`), 이를 `Document.metadata`에 넣는다(`app/etl/enricher.py:95-107`). `scripts/build_index.py` Stage 2의 캐싱 추출기는 `node.get_content(metadata_mode=MetadataMode.LLM)`을 LLM 추출 입력으로 사용한다(`scripts/build_index.py:181-188`). 따라서 원문과 LLM 생성 summary/keywords가 섞여 triplet extraction에 영향을 줄 수 있다. `docs/CONTEXT.md` 발견 10도 이 가능성을 후속 개선 대상으로 남긴다(`docs/CONTEXT.md:116-117`). 실제 오염률은 확인 못 함.
- 반증 조건: metadata 포함/제외 재추출 비교에서 추출 triplet, relation type 분포, graph metric, downstream 평가가 유의미하게 변하지 않으면 이 지적은 약해진다.
- handoff 수정 제안: §2 또는 §12 B에 "LLM-generated metadata를 extraction evidence로 재투입하는 경로"를 명시하고, 새 프로젝트에서는 원문 필드와 파생 필드를 강제로 분리하라.

### 6. 평가 없이 사용된 Graph algorithm보다 더 큰 문제는 Graph가 추론에 거의 개입하지 못한 점이다

- 근거 등급: [코드확인]
- 심각도: 중대
- 반대 주장: handoff §12 B는 "평가 없이 사용된 Graph algorithm"을 폐기 대상으로 쓰지만, 실제 코드상 최종 리포트는 RAG 분석과 graph reasoning 문자열을 단순 결합한다. `graph_flow.py`는 `need_graph=True`를 고정하고(`app/rag/graph_flow.py:52-53`), 최종 합성은 `f"### [RAG 분석]...### [심층 관계 분석]..."` 문자열 조립이다(`app/rag/graph_flow.py:74-78`). `knowledge_graph.py`의 metric도 factuality/originality/insight를 다시 LLM에게 0~100점으로 묻는다(`app/graph/knowledge_graph.py:65-84`, `app/graph/knowledge_graph.py:95-102`). 이는 graph algorithm 남용이라기보다 검증 의사결정 contract 부재다.
- 반증 조건: graph reasoning 결과가 최종 verdict의 특정 필드를 변경하고, graph 없는 조건과 비교 가능한 로그가 있으면 이 지적은 약해진다.
- handoff 수정 제안: §2.3을 "Graph incremental value를 못 측정"에서 한 단계 구체화해 "Graph output이 최종 verdict에 어떤 contract로 개입하는지 정의되지 않았다"로 수정하라.

## B. handoff 가정에 대한 적대적 리뷰

### 7. `condition_omission`이 Graph 문제라는 전제는 아직 미검증이다

- 근거 등급: [추론]
- 심각도: 치명
- 반대 주장: handoff §3.1은 `condition_omission`을 Graph 프로젝트의 존재 이유로 둔다(`docs/handoff/finance_rule_graph_project_handoff.md:129-164`, `docs/handoff/finance_rule_graph_project_handoff.md:197-198`). 그러나 finance_verifier 원자료가 이 worktree에 없어 실제 실패 분포와 재현성을 확인 못 했다. 반대 가설은 최소 네 가지다.
- 반대 가설 1: 프롬프트/디코딩 문제. 모델이 조건 누락을 보지 못한 것이 아니라 판정 지시가 "claim에 적힌 내용" 중심으로 편향됐을 수 있다. 반증 실험: 동일 evidence/claim에 대해 "필수조건 목록을 먼저 모두 열거하라"는 2단계 프롬프트, 낮은 temperature, JSON checklist 출력을 적용해 실패율이 유지되는지 본다.
- 반대 가설 2: claim 분해 단위 문제. "A와 C를 하면 최고금리"라는 claim이 사실상 "A와 C도 필요조건이다"와 "A와 C만으로 충분조건이다"를 혼합한다면 atomic claim 설계가 문제일 수 있다. 반증 실험: sufficient/necessary claim을 분리한 annotation으로 재평가했을 때 같은 false accept가 남는지 본다.
- 반대 가설 3: evidence 검색 리콜 문제. verifier가 B 조건을 포함한 evidence chunk를 받지 못했을 수 있다. 반증 실험: oracle evidence를 넣은 조건과 retriever evidence 조건을 분리해 recall ceiling을 측정한다.
- 반대 가설 4: deterministic checklist 문제. Graph가 아니라 field별 checklist 파서와 문자열/정규식 비교만으로 충분할 수 있다. 반증 실험: `spcl_cnd`에서 사람이 만든 required-condition checklist를 사용한 non-graph baseline과 Graph baseline을 비교한다.
- 반증 조건: 위 네 baseline이 모두 `condition_omission` recall을 충분히 개선하지 못하고, Graph/logic representation만 유의미한 incremental gain을 보이면 이 지적은 틀린다.
- handoff 수정 제안: §3.1 뒤에 "Graph 필요성 반증 실험"을 선행 gate로 추가하라. MVP 구현 전 prompt-only, decomposition-only, oracle evidence, deterministic checklist baseline을 통과 조건으로 둬야 한다.

### 8. 순환성: LLM verifier 실패가 LLM extractor 앞단으로 이동할 수 있다

- 근거 등급: [코드확인], [데이터확인], [추론]
- 심각도: 치명
- 반대 주장: handoff는 "LLM에게 빠진 조건을 다시 생각하게 하지 않고 deterministic set comparison을 한다"고 하지만(`docs/handoff/finance_rule_graph_project_handoff.md:381-384`), `Required`와 `Claimed`를 만드는 과정은 여전히 LLM일 가능성이 높다. 기존 저장소는 LLM 자유 추출이 관계 타입 폭발을 만든 실례다(`app/graph/knowledge_graph.py:27-35`; v1 relation type 460종/773관계). 발견 6은 모델 세대를 올려도 자유 스키마 추출기 문제가 유지됐고(`docs/CONTEXT.md:108-112`), 발견 15는 엔티티 925개 중 883개(95.46%)가 단일 문서에만 등장한다고 한다(`tests/fixtures/entity_hapax.json`). 발견 17/18/19는 긴 서술구와 날짜·수치 노드가 가짜 연결을 만든다고 경고한다(`docs/CONTEXT.md:172-180`). 같은 계열의 LLM이 `spcl_cnd` 자연어에서 ConditionGroup을 완전하게 뽑는다는 보장은 아직 없다.
- 반증 조건: 사람이 만든 gold ConditionGroup과 LLM extractor 산출물을 비교해 condition-level recall/precision, operator accuracy, exception/threshold accuracy가 충분히 높고, extractor 오류와 verifier 오류가 독립적으로 계측되면 이 지적은 약해진다.
- handoff 수정 제안: §7 또는 §10에 "Graph extraction 자체의 gold evaluation"을 독립 산출물로 추가하라. Hybrid 성능 전에 extractor recall ceiling을 먼저 보고해야 한다.

### 9. `Required - Claimed` 집합 차분은 금융 조건 표현을 과소모델링한다

- 근거 등급: [추론]
- 심각도: 치명
- 반대 주장: §8의 집합 차분은 `ALL_OF` 단순 예제에서는 설득력 있지만(`docs/handoff/finance_rule_graph_project_handoff.md:354-379`), 실제 금융 조건은 다음에서 깨질 수 있다.
- 패러프레이즈: `급여이체`와 `월급 자동입금`을 같은 condition으로 볼 것인가.
- 함의 조건: `모바일 가입`이 `비대면 채널`을 함의할 때 claim이 어떤 집합을 가진 것으로 볼 것인가.
- k-of-n/ANY_OF: "3개 중 2개 충족"은 단순 `Required - Claimed`가 아니다.
- threshold/range: "월 50만원 이상" vs "매월 급여 입금"은 값, 단위, 기간을 비교해야 한다.
- 예외조건: "단, 이벤트 금리는 제외"는 missing condition인지 scope 제한인지 다르다.
- 조건의 조건: "마케팅 동의 시, 단 만 14세 이상" 같은 nested prerequisite가 있다.
- claim의 부정: "마케팅 동의 없이도 가능"은 누락이 아니라 explicit contradiction이다.
- `Claimed` 집합 생성 주체가 LLM이면 verifier의 omission 문제가 claim parser로 이동한다.
- 반증 조건: 실제 `spcl_cnd`/`mtrt_int`/`etc_note` 샘플에서 위 유형을 annotation하고, set-difference checker가 각 유형의 gold verdict를 안정적으로 맞히면 이 지적은 틀린다.
- handoff 수정 제안: §8을 "집합 차분은 ALL_OF MVP의 한 연산"으로 격하하고, ANY_OF/k-of-n/range/exception/negation은 별도 semantics와 truth table을 요구한다고 명시하라.

### 10. §6/§7 스키마는 과소이면서 과대다

- 근거 등급: [데이터확인], [추론]
- 심각도: 중대
- 반대 주장: handoff §6의 노드 10종과 관계 8종은 단순해 보이지만(`docs/handoff/finance_rule_graph_project_handoff.md:278-306`), 실제 자연어 금융 필드에 충분한지 검증되지 않았다. 이 worktree에는 금융 API 샘플이 없어 직접 확인 못 했다. 다만 기존 뉴스 데이터에서 "숫자/날짜/긴 서술구를 노드로 두면 망가진다"는 경고는 강하다. v1 그래프에는 숫자·기간성 노드가 다수 존재하고(`experiments/v1/graph_public.json` jq: `7.09%`, `3월 31일까지`, `2026년 3월 7일∼7월 5일` 등), v2a-hi는 `5년` 클러스터가 ETF·쿠폰·날짜·펀드시장을 한데 묶는 오병합 샘플을 낸다(`tests/fixtures/normalize_v1_hi_dryrun.json`). 금융 스키마의 `Rate`, `Term`, `Condition`도 같은 위험을 가진다.
- 반증 조건: 실제 금융상품 샘플에서 노드/리터럴/논리식 선택 기준을 적용했을 때 노드 폭발, 중복 condition, 날짜·금액 허브, false reject가 발생하지 않는다는 측정이 있으면 이 지적은 약해진다.
- handoff 수정 제안: §6에 금융 API field별 mapping table을 추가하라. 예: `intr_rate`, `intr_rate2`는 `Rate` node가 아니라 product-option literal, `save_trm`은 term literal, `spcl_cnd`는 logic expression, `etc_note`는 coverage/scope note 등으로 사전 결정하라.

### 11. operator 7종은 같은 층위가 아니다

- 근거 등급: [추론]
- 심각도: 중대
- 반대 주장: §7의 `ALL_OF`, `ANY_OF`, `NOT`, `MUTUALLY_EXCLUSIVE`, `THRESHOLD`, `TEMPORAL`, `EXCEPTION`은 모두 ConditionGroup operator 후보로 나열되어 있다(`docs/handoff/finance_rule_graph_project_handoff.md:340-350`). 그러나 `ALL_OF/ANY_OF/NOT`은 논리 결합자, `THRESHOLD/TEMPORAL`은 predicate의 비교 제약, `EXCEPTION`은 scope override, `MUTUALLY_EXCLUSIVE`는 조건 간 consistency relation이다. 같은 enum에 넣으면 checker가 "operator"의 의미를 과적재하게 된다.
- 반증 조건: 단일 operator enum으로 nested expression, threshold value, temporal interval, exception precedence를 모호성 없이 직렬화·검증할 수 있음을 grammar와 사례로 보이면 이 지적은 틀린다.
- handoff 수정 제안: §7을 expression grammar로 바꾸라. 예: `Expr = All|Any|Not|Predicate|Exception`, `Predicate`가 comparator/value/unit/period를 가진다. `MUTUALLY_EXCLUSIVE`는 expression operator가 아니라 validation constraint로 분리하라.

### 12. Graph-only 평가는 비교 대상으로 부적절할 수 있다

- 근거 등급: [추론]
- 심각도: 중대
- 반대 주장: §10은 Verifier Only, Graph Only, Hybrid를 비교한다고 한다(`docs/handoff/finance_rule_graph_project_handoff.md:413-421`). 하지만 handoff 자체가 Graph는 verifier를 대체하지 않는다고 한다(`docs/handoff/finance_rule_graph_project_handoff.md:208-223`). Graph가 할 수 있는 일이 "missing required condition → UNSUPPORTED 후보"뿐이면 SUPPORTED/INSUFFICIENT를 판정할 수 없다. 이 경우 3-way classifier로 Macro F1을 비교하는 Graph-only는 의미가 없다.
- 반증 조건: Graph-only가 SUPPORTED/UNSUPPORTED/INSUFFICIENT 세 라벨을 모두 산출하는 명확한 abstain/coverage policy를 갖고, coverage 밖 사례를 어떻게 채점할지 사전 정의하면 이 지적은 약해진다.
- handoff 수정 제안: §10에서 Graph-only를 "classifier"가 아니라 "rule trigger / abstaining detector"로 정의하라. 지표는 `trigger precision`, `condition_omission recall within coverage`, `coverage`, `false reject among supported claims`로 분리하라.

### 13. "Graph extraction 오류와 Verifier 오류 분리"는 측정 설계가 없다

- 근거 등급: [코드확인], [추론]
- 심각도: 치명
- 반대 주장: §10은 오류를 분리한다고 하지만(`docs/handoff/finance_rule_graph_project_handoff.md:454-455`), 실제로는 최소 세 산출물이 필요하다: gold evidence condition graph, extracted graph, verifier verdict. 기존 저장소의 평가 코드는 합성 질문을 LLM이 만들고(`app/rag/evaluator.py:26-55`), RAGAS도 LLM/embedding 기반으로 평가한다(`app/rag/evaluator.py:80-96`). 이런 방식은 extractor 오류와 verifier 오류를 분리하지 못한다.
- 반증 조건: 동일 claim set에 대해 (1) gold graph+verifier, (2) extracted graph+oracle checker, (3) extracted graph+verifier, (4) no graph+verifier를 분리 실행하고 각 confusion matrix를 보고하면 이 지적은 틀린다.
- handoff 수정 제안: §10에 factorial evaluation matrix를 추가하라. "Graph extraction valid rate"만으로는 부족하고, gold graph 조건의 upper bound와 extracted graph 조건의 realized performance를 분리해야 한다.

### 14. 평가 slice 선택 편향과 negative 사례 부재 위험

- 근거 등급: [추론]
- 심각도: 중대
- 반대 주장: Primary slice가 `condition_omission` 하나로 고정되어 있다(`docs/handoff/finance_rule_graph_project_handoff.md:428-439`). 이 slice를 Graph 설계자가 고르면 Graph가 잘 잡을 수 있는 문제만 고르는 선택 편향이 생긴다. 또한 false reject 측정에는 정상 supported claim과 benign omission 사례가 필요하지만, handoff는 negative 사례 출처와 크기를 말하지 않는다.
- 반증 조건: slice annotation을 설계자와 독립된 reviewer가 blind로 수행하고, supported/unsupported/insufficient 및 omission/non-omission negative가 균형 있게 포함되며, 데이터셋 크기와 신뢰구간/검정력 계획이 있으면 이 지적은 약해진다.
- handoff 수정 제안: §10에 dataset construction protocol을 추가하라. 최소한 blind annotation, inter-annotator agreement, held-out 상품, false reject negative source, sample size justification을 명시하라.

### 15. 신규 저장소에서 history를 잇지 않는 정책은 재현성 자산을 버릴 수 있다

- 근거 등급: [코드확인], [데이터확인], [추론]
- 심각도: 중대
- 반대 주장: §13은 기존 Git history를 가져오지 않는다고 한다(`docs/handoff/finance_rule_graph_project_handoff.md:517-528`). 기록 보존 의도는 이해하지만, 이 저장소에서 가장 값진 자산은 코드보다 실패를 드러낸 사전 등록·fixture·검증 패턴이다. `docs/design-review.md`는 판정 기준 커밋 순서를 기록한다(`docs/design-review.md:39-63`). `verify_metrics.py`는 지표 정의와 known gap을 문서화한다(`scripts/verify_metrics.py:1-35`). `docs/CONTEXT.md` 발견 11/20은 모델 수명과 대화형 계산이 재현성을 깨뜨린다고 한다(`docs/CONTEXT.md:116-117`, `docs/CONTEXT.md:184-192`). 새 저장소가 history와 fixture 패턴을 버리면 같은 실패를 반복할 수 있다.
- 반증 조건: 신규 저장소 초기 커밋에 사전 등록 템플릿, metric definition, raw model response logging, fixture verification, model ID 기록 정책이 포함되면 이 지적은 약해진다.
- handoff 수정 제안: §13에 "history는 잇지 않되, 진단 산출물은 seed artifact로 vendoring/import"라는 정책을 추가하라. 최소 `docs/design-review.md`의 사전 등록 표 구조, `verify_metrics.py`의 fixture 검증 방식, raw response logging 패턴은 새 spec에 복제해야 한다.

### 16. §14 역할 분담과 §16 독립검증 주의사항은 긴장 관계에 있다

- 근거 등급: [추론]
- 심각도: 경미
- 반대 주장: §14는 여러 도구가 공통 handoff를 읽고 역할을 나누도록 한다(`docs/handoff/finance_rule_graph_project_handoff.md:550-575`). §16은 같은 문서를 읽은 결론은 독립 검증이 아니라고 경고한다(`docs/handoff/finance_rule_graph_project_handoff.md:615-640`). 둘은 완전한 모순은 아니지만, 현재 프로세스는 "공통 프레임을 주입한 뒤 독립 리뷰처럼 해석"될 위험이 있다. 이 리뷰도 handoff가 지정한 쟁점 구조 안에서 작성되었으므로 완전 독립 검증이 아니다.
- 반증 조건: blind reviewer에게 handoff의 결론 섹션을 숨기고 원자료만 제공했을 때도 같은 핵심 결론이 나오면 이 지적은 약해진다.
- handoff 수정 제안: §16에 "adversarial/blind review 모드"를 추가하라. 예: A그룹은 handoff 전체, B그룹은 원자료+질문만, C그룹은 finance_verifier failure만 보고 독립 결론을 낸 뒤 비교한다.

## 동의하는 부분

- 근거 등급: [코드확인], [데이터확인]
- 자유 스키마 추출기를 새 프로젝트에 그대로 가져가면 안 된다는 점에는 동의한다. `SimpleLLMPathExtractor`의 무제약 사용(`app/graph/jit_builder.py:21-32`)과 v1 관계 타입 460종/773관계 수치는 충분한 경고다.
- Graph incremental value를 ablation으로 측정해야 한다는 점도 동의한다. 기존 최종 리포트는 graph reasoning 문자열을 결합할 뿐(`app/rag/graph_flow.py:74-78`) 독립 기여도를 설명하지 못한다.
- provenance를 발전시켜야 한다는 점도 동의한다. 로컬 property graph는 관계 property에 `news_id`, `pub_date`, `triplet_source_id`를 붙이는 방향을 보였지만(`docs/00-baseline-survey.md:145-151`), Neo4j 실체에는 relation property가 없었다.

## 가장 위험한 가정 5개

1. [치명] `condition_omission`은 Graph로 풀 문제라는 가정. prompt/decomposition/evidence/checklist baseline을 이기지 못하면 프로젝트 존재 이유가 약해진다.
2. [치명] LLM이 `spcl_cnd`에서 ConditionGroup을 충분히 완전하게 추출한다는 가정. verifier 실패가 extractor 실패로 이동할 수 있다.
3. [치명] `Required - Claimed` 집합 차분으로 금융 조건 누락을 일반화할 수 있다는 가정. ANY_OF, threshold, exception, negation, nested condition에서 깨질 가능성이 크다.
4. [중대] Graph-only를 3-way verifier처럼 평가할 수 있다는 가정. Graph가 abstaining detector라면 지표 설계가 달라져야 한다.
5. [중대] 새 저장소가 기존 history 없이도 재현성 자산을 보존할 수 있다는 가정. 이 저장소의 가장 중요한 교훈은 코드가 아니라 사전 등록·fixture·raw logging·metric verification 패턴이다.
