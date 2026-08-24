# CLAUDE.md — FINeprint 작업 규칙

> **이 문서는 설계 문서가 아니다.** 문제 정의·계획·스키마·평가 설계는
> `docs/`에 tool-neutral하게 둔다(`docs/handoff/v2.md` §13 — 여러 Agent가 같은 문서를
> 봐야 하므로 핵심 결정을 Claude 전용 문서에 종속시키지 않는다).
> 여기에는 **작업 규칙만** 둔다.

## 시작할 때

**`START-HERE.md` → `docs/handoff/v2.md` 순서로 읽는다.** 그 두 문서가 현재 상태와
다음에 할 일을 갖고 있다. `docs/handoff/v1-original.md`는 보존용이며 **계획으로 읽지 않는다.**

한 줄 요약: 금융 답변이 빠뜨린 필수조건(`condition_omission`)을 구조로 잡는다 —
단, **그래프 없이 되는지부터 먼저 확인한다**(v2 §3 반증 게이트).

## 절대 하지 말 것

1. **게이트(v2 §3) 통과 전에 스키마·그래프 코드를 쓰지 않는다.**
   `docs/spec/schema.md`가 비어 있는 건 실수가 아니라 결정이다. 선행 저장소가 실패한
   순서(구조 먼저, 계약 나중)를 방향만 바꿔 반복하는 걸 막는 방어선이다.
2. **미정 항목(`docs/decisions/README.md`의 D1~D5)을 임의로 확정하지 않는다.**
   후보와 trade-off를 정리해서 사람에게 묻는다.
3. **지표를 측정한 뒤에 정의하지 않는다.** 정의·임계·표본 크기를 측정 **전에** 커밋한다
   (v2 §8.3). 이 프로젝트가 선행 저장소에서 배운 규율의 핵심이다.
4. **Verifier를 새로 만들지 않는다.** `finance_verifier` 코드를 재사용한다(A 통제군).
5. **정규화(별칭 사전) 경로로 가지 않는다.** 선행 저장소가 시도해서 기각했다
   (재등장 엔티티 4.5%). 해법은 추출 시점에 형식을 제한하는 것이다.
6. **선행 저장소를 수정하지 않는다.** `finance_verifier`, `KAG_LlamaIndex` 둘 다
   독립 프로젝트로 보존한다. 읽기만 한다.
7. **`docs/audit/` 3종을 편집하지 않는다.** 이식된 seed artifact이며 당시 감사의 기록이다.

## 문서는 쉬운 말로 쓴다

**기본값은 "이 도메인을 모르는 사람도 한 번 읽고 이해되는 글"이다.** 정확성을 위해
밀도를 높여야 하는 곳은 `docs/` 안쪽(감사 인용, 지표 정의)이고, 바깥쪽
(`README.md`, `START-HERE.md`, 리포트, 발표 자료)은 쉬운 말이 우선이다.

구체적으로:

- **약어·용어를 처음 쓸 때 한 번 풀어준다.** `condition_omission`, ablation, factorial
  matrix, abstaining detector 같은 말은 옆에 한 줄 설명을 붙인다
- **결론을 먼저, 근거를 나중에.** 감사 번호(C1, V3, M2)로 시작하지 말고 "무엇이
  왜 문제인지"부터 쓴 뒤 근거로 번호를 단다
- **구체적인 예시 하나가 설명 세 문장보다 낫다.** 실제 상품·실제 조건 문구를 쓴다
- 표와 코드블록으로 도망가지 말고, 표 앞에 **"이 표가 말하는 것"을 한 문장** 붙인다

선행 프로젝트에서 이미 확인된 선호다 — finance_verifier의 발표 자료를 전문용어 없이
다시 쓴 뒤 훨씬 나았다. **묻지 않고 쉬운 쪽을 기본값으로 삼는다.**

## 결정을 남기는 방식

중요한 결정은 `docs/decisions/`에 5항목으로 남기고 **결정 직후 커밋한다.**

```
Decision · Evidence · Alternative · Why rejected · 반증 조건
```

`반증 조건`("무엇이 관측되면 이 결정이 틀린 것인가")을 **결정 시점에 미리** 적는다.
근거가 없으면 "근거 없음 — 판단"이라고 쓴다. 없는 근거를 만들지 않는다.

## Git / 이슈 관리

`finance_verifier`에서 잘 작동한 경량 워크플로우를 계승한다. 무겁게 가지 않는다
(required review, CI 게이트, project board 미사용).

- **브랜치**: `<이슈번호>-slug`
- **PR**: 이슈 하나당 PR 하나, 본문에 `Closes #N`. 리뷰어 없으므로 self-merge, **squash merge**
- **커밋 메시지**: `feat:` / `fix:` / `chore:` / `docs:` 최소 prefix
- **이슈 체크박스는 작업이 끝날 때 같이 갱신한다** — finance_verifier에서 5개 이슈가
  "작업은 다 했는데 체크박스만 안 눌린" 상태로 닫혔다. 같은 걸 반복하지 않는다
- **커밋/푸시 전에는 항상 사용자에게 확인을 받는다.** 세션 중 앞서 승인이 있었어도 매번 묻는다

원격은 아직 없다(로컬 git만). GitHub 리포지토리는 필요할 때 생성한다.

## 실행 환경 (finance_verifier에서 검증된 것 재사용)

```
Windows 11 + RTX 4070 Laptop 8GB → WSL2 → Docker Desktop → vLLM(공식 이미지)
→ OpenAI 호환 endpoint → client (host Python)
```

- 서빙 설정은 검증된 값을 그대로 쓴다: `--max-model-len 1024 --max-num-seqs 4`
  (eager 제거, CUDA graph 활성). 근거는 finance_verifier `results/latency/`
- Qwen3.5는 **반드시** `chat_template_kwargs: {enable_thinking: false}`로 호출한다
  (없으면 thinking이 누출돼 JSON 스키마가 깨진다)
- **Git Bash에서 `docker run -v`를 쓸 때는** `MSYS_NO_PATHCONV=1` + Windows 스타일
  호스트 경로를 쓴다 (MSYS 경로 변환 버그로 마운트가 조용히 실패한다)

## 보안

- 키는 `.env`에만 둔다. `.gitignore`에 포함됨
- API 키를 로그·커밋·Docker 이미지·프롬프트에 절대 출력/저장하지 않는다. 디버깅 시 `***` 마스킹
- `.env.example`에는 키 이름만 적는다

## 스크래치 작업

임시 스크립트·중간 산출물은 리포지토리에 커밋하지 않는다. `notes/`는 `.gitignore`에 있다
(개인 메모용).
