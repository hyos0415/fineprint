# FINeprint — Evaluation

> 상태: **골격.** 지표는 측정 전에 사전 등록한다. 게이트 설계는 `../handoff/v2.md` §3.

## 0. 왜 사전 등록인가

선행 저장소(KAG_LlamaIndex)의 발견 16: **사전 등록은 오류를 막지 않고 드러낸다.**
같은 저장소가 두 번 겪은 재현성 실패(발견 11·20)의 공통 원인은 기준을 나중에 정한 것이었다.
따라서 이 프로젝트는 **측정 전에 지표 정의·임계·표본 크기를 날짜와 함께 커밋한다.**

## 1. 반증 게이트 (Phase 0)

`../handoff/v2.md` §3 참고. 게이트가 요구하는 것:

- 그래프 없는 baseline 4종을 먼저 측정한다
- 그중 하나라도 `condition_omission`을 충분히 잡으면 **그래프로 가지 않는다**
- "충분히"의 임계는 측정 **전에** 정한다 (D4, 미정)

## 2. 본 실험 — factorial matrix (게이트 통과 시)

감사 권고 #5(Codex V6): "extraction 오류와 verifier 오류 분리"에 측정 설계가 필요하다.
Hybrid 성능을 보기 전에 **extractor recall ceiling을 먼저 보고한다.**

| | oracle checker | real checker |
|---|---|---|
| **gold graph** | 상한 (설계가 맞는지) | checker 품질 |
| **extracted graph** | extractor 품질 | 실제 성능 |

이 2×2를 채우지 않고 "Hybrid가 좋아졌다"고 보고하지 않는다.

## 3. 시스템 비교 (ablation)

```
A. Verifier Only        ← finance_verifier 코드 그대로 재사용
B. Structure Only
C. Verifier + Structure
```

**B는 3-way classifier가 아니다** (감사 Codex V5). 조건 누락이 감지될 때만 발화하는
abstaining detector이므로, B의 지표는 A/C와 같은 축으로 재지 않는다:

```
trigger precision · coverage · false reject
```

## 4. 지표 후보 (확정 전)

```
Condition Omission Recall     ← primary
False Accept Rate             ← finance_verifier와 동일 정의로 비교 가능하게
False Reject                  ← 구조 검사가 정상 claim을 과차단하는지
UNSUPPORTED Recall / Macro F1  ← 보조
Extraction Valid Rate         ← 버려진/파싱 실패 항목 비율 포함 (선행 저장소 미구현 지표)
Additional Latency
```

**`Extraction Valid Rate`에 "조용히 버려진 항목"을 반드시 포함한다** — 선행 저장소는
같은 요구를 문서에 적어두고 구현하지 않아 파싱 실패가 계측되지 않았다
(`../audit/00-comparison.md` M3).

## 5. 표본 / 검정력

**미정 (D1) · 최우선 블로킹.** 현재 `condition_omission` 사례는 전체 3건이고
크로스모델 체크는 n=2였다(`../reference/finance-verifier-findings.md` §2.1).
이 크기에서는 어떤 개선도 측정되지 않는다.

false reject 측정용 negative 사례의 출처·크기도 함께 정한다(감사 Codex V7).
