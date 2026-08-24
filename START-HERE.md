# START-HERE — FINeprint

> 새 세션은 이 문서부터 읽는다. 마지막 갱신 2026-08-24.

## 한 줄

금융 답변이 빠뜨린 **필수조건**을 자연어 판단이 아니라 **구조**로 잡아낸다 —
단, **그래프 없이 되는지부터 먼저 확인한다.**

## 현재 상태

```
뼈대 + handoff v2 확정.   구현 0줄.   실험 0건.
```

착수 전 사람이 정해야 할 것이 남아 있다 (아래 §다음 할 일).

## 읽는 순서

| 순 | 문서 | 무엇 |
|---|---|---|
| 1 | **`docs/handoff/v2.md`** | **현재 유효한 계획.** 특히 §3 반증 게이트 |
| 2 | `docs/reference/finance-verifier-findings.md` | 출발점이 된 실측. 무엇이 확립됐고 무엇이 안 됐는지 |
| 3 | `docs/decisions/README.md` | 이미 정한 것 · 열린 결정(D1~D5) |
| 4 | `docs/audit/00-comparison.md` | v1→v2 수정의 근거 (필요할 때만) |
| — | `docs/handoff/v1-original.md` | 보존용. **계획으로 읽지 않는다** |

## 다음에 할 일 (순서 고정)

### 0. 사람이 정할 것 — 이것부터

- **D1: 평가 slice 목표 크기.** 현재 `condition_omission` 사례는 **전체 3건**이고
  크로스모델 체크는 n=2였다. 이 크기에서는 어떤 개선도 측정되지 않는다.
  몇 건까지 늘릴 것인가?
- **D4: 게이트 통과 임계.** baseline이 얼마나 잡으면 "구조 불필요"로 판정할 것인가?
  (측정 **전에** 정해야 한다)
- (선택) `docs/handoff/v2.md` §2의 **Q2 정정**을 확인한다. 선행 프로젝트의 정규화 서사를
  "안 했다" → "시도해서 기각했다"로 고쳐뒀다. 되돌리려면 그 절만 수정하면 된다

### 1. G0 — 평가 slice 구축

`condition_omission` 사례를 D1 목표치까지. false reject 측정용 negative(조건을 전부
정확히 인용한 정상 claim)도 같이. finance_verifier의 데이터 파이프라인 재사용
(`docs/reference/finance-verifier-findings.md` §3).

이때 **3건이 모두 순수 `ALL_OF`인지** 확인한다 (v2 §7 — k-of-n·threshold·예외가
섞여 있으면 집합 차분이 성립하지 않는다).

### 2. G4 — 결정론적 체크리스트 baseline ← 가장 먼저 돌릴 실험

그래프 없이. 조건 텍스트를 평면 리스트로 파싱해서 `Required − Claimed` 집합 차분만.

**이게 잡으면 그래프는 불필요하고, 그게 이 프로젝트의 결론이 된다.** 가장 싸고 가장
위험하므로 가장 먼저 돌린다.

### 3. G1 → G2 → 게이트 판정

`docs/handoff/v2.md` §3 표 그대로. 결과는 `docs/decisions/`에 5항목 형식으로 기록.

## 하지 말 것

- ❌ **게이트(§3) 통과 전에 스키마·그래프 코드를 쓰지 않는다.** `docs/spec/schema.md`가
  비어 있는 건 실수가 아니라 결정이다
- ❌ **Verifier를 새로 만들지 않는다.** finance_verifier 코드를 그대로 재사용한다
  (A 통제군)
- ❌ **미정 항목(D1~D5)을 임의로 확정하지 않는다.** 후보와 trade-off를 정리해서 사람에게 묻는다
- ❌ **정규화(별칭 사전) 경로로 가지 않는다.** 선행 저장소가 시도해서 기각했다
  (재등장 엔티티 4.5%)
- ❌ 지표를 측정한 **뒤에** 정의하지 않는다. 사전 등록 후 커밋

## 계보

```
KAG_LlamaIndex (News-Arena)   Graph-first → 한계 발견
        ↓
finance_verifier              Eval-first → condition_omission 발견 (표본 3건)
        ↓
FINeprint                     게이트 먼저 → 필요한 만큼만 구조 → ablation
```

참고 저장소:
- https://github.com/hyos0415/finance_verifier (선행, 완료)
- https://github.com/hyos0415/KAG_LlamaIndex (선행, 보존 — 수정하지 않는다)

## 저장소

로컬 git만 초기화돼 있다. GitHub 원격은 **아직 없음** — 필요할 때 생성한다.
