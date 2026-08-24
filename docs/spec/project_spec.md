# FINeprint — Project Spec

> 상태: **골격.** 아래 항목은 반증 게이트 결과가 나온 뒤에 채운다.
> 지금 채우면 게이트 결과와 무관하게 이미 결론을 정해둔 셈이 된다.

tool-neutral 문서다. 특정 Agent 전용 지시는 `CLAUDE.md` 등에 따로 둔다.

## Problem

`docs/handoff/v2.md` §1 참고. (게이트 통과 후 이 문서로 확정 이전)

## Hypothesis

미정 — 게이트 결과에 따라 "구조가 필요하다"의 형태가 달라진다
(결정론적 체크리스트로 충분 / 조건 그룹 표현 필요 / 그래프 순회 필요).

## Scope

미정.

## Non-goals

handoff v2 §9 초안 유지. 확정은 게이트 후.

## Data

`docs/reference/finance-verifier-findings.md` §3의 재사용 자산 + 신규 평가 slice(D1 미정).

## Schema

`schema.md` — **게이트 통과 전에는 착수하지 않는다.**

## Constraint

미정.

## Evaluation contract

`evaluation.md` 참고.

## Metrics

미정 — 단, 지표는 **측정 전에 사전 등록**한다(선행 저장소 발견 16: 사전 등록은 오류를
막지 않고 드러낸다).

## Current decisions

`../decisions/README.md`

## Rejected alternatives

`../decisions/` 의 각 기록 "Why rejected" 절.

## Known limitations

`docs/reference/finance-verifier-findings.md` §2 (표본 3건, 미측정 baseline 4종,
조건 추출 난이도 미지수, 원문 모호성으로 인한 gold 상한).
