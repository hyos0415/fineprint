# -*- coding: utf-8 -*-
"""파일럿 질문 30개를 만든다 (`docs/spec/prereg-02-pilot.md` §6.2 템플릿 고정).

템플릿 문구는 사전등록에 박혀 있다. 여기서 바꾸면 다른 실험이 된다.
출력: data/pilot/questions_<stamp>.json (git 제외)

사용법: python src/pilot/build_questions.py [YYYYMMDD]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = REPO_ROOT / "data" / "pilot"

TEMPLATE = """아래는 금융감독원에 공시된 예금·적금 상품의 정보입니다.

[상품명] {product_name} ({bank})
[기간별 금리] 12개월 기준 기본금리 {base_rate}%, 최고금리 {max_rate}%
[우대조건]
{spcl_cnd}

제 상황은 다음과 같습니다.
- 급여이체: {salary}
- 자동이체: {autopay}
- 카드 결제: {card}
- 이 은행과의 거래 이력: {first}
- 가입 방법: {online}
- 주택청약종합저축: {housing}
- 통장: {passbook}
- 이 은행의 기존 예치잔액: {balance}
- 가입 금액과 기간: 1,000만원 / 12개월

위에 적은 상태만 해당하고, 그 밖의 조건(봉사활동, 서약, 이벤트, 다른 상품 보유 등)은
해당하지 않는다고 가정하세요.

이 상품에 가입하면 연 몇 %를 받게 되나요? 설명한 뒤, 마지막 줄에 아래 형식의 JSON을
그대로 한 줄로 출력하세요.

{{"rate_percent": <숫자 또는 null>, "verdict": "computable" 또는 "unknown", "conditions_met": [<충족한 우대조건 이름들>]}}"""


def describe(state: dict) -> dict:
    """수치 상태를 사람이 읽는 문장으로 (prereg §3의 값을 그대로 옮긴다)."""
    won = lambda v: f"{v // 10_000:,}만원"
    return {
        "salary": f"매월 {won(state['급여_월입금액'])} 입금 ({state['급여_개월수']}개월 전 기간)"
                  if state["급여_월입금액"] else "없음",
        "autopay": f"매월 {state['자동이체_월건수']}건 (전 기간)" if state["자동이체_월건수"] else "없음",
        "card": f"월 {won(state['카드_월결제액'])} 결제" if state["카드_월결제액"] else "없음",
        "first": "이 은행과 거래한 적이 없음" if state["첫거래"] else "거래 이력 있음",
        "online": "모바일 앱으로 가입" if state["비대면가입"] else "영업점 창구에서 가입",
        "housing": "보유" if state["청약보유"] else "미보유",
        "passbook": "종이통장을 발급받지 않음(미발급 선택)" if state.get("통장미발급") else "종이통장 발급",
        "balance": won(state["기존예치잔액"]) if state["기존예치잔액"] else "0원",
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    stamp = sys.argv[1] if len(sys.argv) > 1 else "20260824"
    sample = json.loads((PILOT_DIR / f"sample_{stamp}.json").read_text(encoding="utf-8"))

    questions = []
    for item in sample["items"]:
        prompt = TEMPLATE.format(
            product_name=item["product_name"], bank=item["bank"],
            base_rate=item["base_rate"], max_rate=item["max_rate"],
            spcl_cnd=item["spcl_cnd"].strip(), **describe(item["state"]))
        questions.append({"qid": item["qid"], "stratum": item["stratum"],
                          "state_pattern": item["state_pattern"],
                          "product_name": item["product_name"],
                          "product_code": item["product_code"], "prompt": prompt})

    out = PILOT_DIR / f"questions_{stamp}.json"
    out.write_text(json.dumps({"snapshot": stamp, "questions": questions},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    lengths = [len(q["prompt"]) for q in questions]
    print(f"{len(questions)}문항 → {out.relative_to(REPO_ROOT)}")
    print(f"프롬프트 길이: 최소 {min(lengths)}자 · 평균 {sum(lengths)//len(lengths)}자 · 최대 {max(lengths)}자")
    print("\n--- Q01 미리보기 ---")
    print(questions[0]["prompt"][:700])


if __name__ == "__main__":
    main()
