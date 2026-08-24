# FINeprint

> 금융 답변이 빠뜨린 **세부 조건**을, 자연어 판단이 아니라 **구조**로 잡아낸다.

이름은 "read the fine print"(약관의 깨알글씨까지 읽어라)에서 왔다. **FIN**ance ·
**fine**-grained condition · printed disclosure — 세 겹이 겹친다.

## 무엇을 푸는가

선행 프로젝트 [finance_verifier](https://github.com/hyos0415/finance_verifier)는
3~4B급 로컬 SLM으로 금융 답변의 근거 관계를 판정했고, 그 과정에서 **자연어 판단만으로는
구조적으로 잡히지 않는 실패 하나**를 확인했다.

```
공식 조건:  A · B · C 를 모두 충족해야 우대금리
AI 답변:    "A 와 C 를 하면 우대금리를 받을 수 있다"   ← B 가 빠졌다

Verifier:   A 있음 ✓  C 있음 ✓  → SUPPORTED (오답)
정답:       UNSUPPORTED
```

**Claim에 적힌 것의 일치는 잘 보지만, Claim에 적히지 않은 필수조건을 evidence 전체에서
능동적으로 찾아내지는 못한다.** Qwen3.5-4B와 Nemotron Ultra 550B(130배 큰 모델)가 같은
지점에서 같은 실수를 했다 — 체급으로 해소되는 문제가 아니라는 뜻이다.

가설:

> 조건 구조를 명시적으로 표현하면 — 특히 **어느 혜택에 어떤 조건이 걸리는지**를
> 혜택 단위로 묶으면 — 필수조건 누락을 **결정론적으로** 잡을 수 있다.

같은 구조로 두 번째 실패도 겨냥한다: **INSUFFICIENT ↔ UNSUPPORTED 경계 혼동**
("정보가 없음"과 "명시적으로 틀림"을 구분 못 하는 것). claim이 가리키는 필드가
evidence 구조에 있는지 조회하면 판정이 아니라 조회가 된다.

## 이 프로젝트가 하지 않는 것

**"Graph를 써보는 프로젝트"가 아니다.** 위 가설이 참이어도 그래프 순회는 필요 없을 수
있고, 심지어 **구조화된 evidence를 그냥 LLM에게 주는 것만으로 해결될 수도 있다.**
그 가능성들을 **먼저** 검증한다 — `docs/handoff/v2.md` §3의 반증 게이트가 그 방어선이다.
게이트에서 "그래프 필요 없음"이 나오면 그게 결론이고, 그것도 결과다.

## 시작하기

**→ [`START-HERE.md`](./START-HERE.md)** 부터 읽는다. 현재 상태와 다음에 할 일이 있다.

## 계보

```
News-Arena / KAG_LlamaIndex     Graph-first 접근 → 한계 발견
        ↓
finance_verifier                Eval-first / failure-first → condition_omission 발견
        ↓
FINeprint                       그 failure를 겨냥한 구조적 보완 + ablation 측정
```
