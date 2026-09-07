# -*- coding: utf-8 -*-
"""R2 표본 20문장과 손 라벨 — `docs/spec/r2-sample-sentences.md` 의 기계용 사본 (`prereg-27` 정답표).

**전부 합성 문장이다.** 사람이 검토하면 md 와 이 파일을 함께 고친다. 측정(`measure_r2.py`)은 이 파일을 읽는다.

라벨 모양
    scope    권역 · 은행 목록 · 상품군 · 기간 · 예금 금액 · 적금 월 납입 (없으면 None / [])
    traded   거래 은행 목록 · [] = 없다고 말함 · None = 말 안 함
    answers  {상태 키: 값} — 값은 "예"·"아니오"·"모름". 기관 상대 유형은 `유형@공시이름`
    정정     2026-09-07 v1 측정 뒤 — 권역 라벨 8개(#2·7·11·12·14·15·19·20)를 "bank" 에서 None 으로. 라벨 규칙("말이 없으면 비운다")과
             프롬프트 규칙("말이 없으면 null")에 라벨 자신이 어긋나 있었다. 모델 출력을 보고 라벨을 맞춘 것이 아니라 규칙에 라벨을 맞춘 것이다 —
             v1 의 85% 는 정정 전 값으로 prereg-27 §6 에 그대로 남긴다
    also_ok  "둘 다 맞다" — 모델이 이 답을 더 채워도 틀린 것으로 세지 않는다 (`prereg-27` §3)
"""
from __future__ import annotations

S = [
    dict(n=1, text="우리은행 주거래고 적금 하나 들고 싶어. 매달 30만원 정도",
         scope=dict(group="bank", banks=["우리은행"], kinds="적금", term=None, amount_deposit=None, amount_monthly=300_000),
         traded=["우리은행"], answers={"주거래_장기거래_재예치@우리은행": "예"}),
    dict(n=2, text="목돈 3천만원을 1년 예금에 넣으려고. 거래하는 은행은 딱히 없어",
         scope=dict(group=None, banks=[], kinds="예금", term=12, amount_deposit=30_000_000, amount_monthly=None),
         traded=[], answers={}),
    dict(n=3, text="국민은행으로 급여 받고 있고 국민카드도 써. 적금 추천해줘",
         scope=dict(group="bank", banks=["국민은행"], kinds="적금", term=None, amount_deposit=None, amount_monthly=None),
         traded=["국민은행"], answers={"급여_연금이체@국민은행": "예", "카드실적@국민은행": "예"}),
    dict(n=4, text="저축은행 예금 금리가 높다길래 보려고. 저축은행은 한 번도 안 써봤어",
         scope=dict(group="savingsbank", banks=[], kinds="예금", term=None, amount_deposit=None, amount_monthly=None),
         traded=[], answers={}),
    dict(n=5, text="카카오뱅크만 써. 자동이체 걸어두는 건 상관없어",
         scope=dict(group="bank", banks=["주식회사 카카오뱅크"], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=["주식회사 카카오뱅크"], answers={"자동이체@주식회사 카카오뱅크": "예"}),
    dict(n=6, text="신한은행 계좌는 있는데 급여는 다른 데로 받아. 급여이체 옮길 생각은 없어",
         scope=dict(group="bank", banks=["신한은행"], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=["신한은행"], answers={"급여_연금이체@신한은행": "아니오"}),
    dict(n=7, text="6개월 짧게 예금 5천만원. 마케팅 동의는 싫어",
         scope=dict(group=None, banks=[], kinds="예금", term=6, amount_deposit=50_000_000, amount_monthly=None),
         traded=None, answers={"마케팅_정보동의": "아니오"}),
    dict(n=8, text="하나은행 오래 썼고 하나카드도 있어. 앱으로 가입할게",
         scope=dict(group="bank", banks=["주식회사 하나은행"], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=["주식회사 하나은행"],
         answers={"주거래_장기거래_재예치@주식회사 하나은행": "예", "카드실적@주식회사 하나은행": "예", "비대면_채널가입": "예"}),
    dict(n=9, text="웰컴저축은행 적금 보고 있어. 거긴 처음이야",
         scope=dict(group="savingsbank", banks=["웰컴저축은행"], kinds="적금", term=None, amount_deposit=None, amount_monthly=None),
         traded=[], answers={}, also_ok={"첫거래_신규고객@웰컴저축은행": "예"}),
    dict(n=10, text="농협 쓰는데 카드 실적은 잘 모르겠어",
         scope=dict(group="bank", banks=["농협은행주식회사"], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=["농협은행주식회사"], answers={}, also_ok={"카드실적@농협은행주식회사": "모름"}),
    dict(n=11, text="2년짜리 적금, 월 50만원. 미션 인증 같은 건 귀찬아서 안 해",
         scope=dict(group=None, banks=[], kinds="적금", term=24, amount_deposit=None, amount_monthly=500_000),
         traded=None, answers={"실천_미션_인증": "아니오"}),
    dict(n=12, text="회사가 판교라 점심마다 배달 시켜. 예금 알아보려고",
         scope=dict(group=None, banks=[], kinds="예금", term=None, amount_deposit=None, amount_monthly=None),
         traded=None, answers={}),
    dict(n=13, text="우리랑 국민 둘 다 거래 있어. 우리은행 급여이체, 국민은 카드만",
         scope=dict(group="bank", banks=[], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=["우리은행", "국민은행"], answers={"급여_연금이체@우리은행": "예", "카드실적@국민은행": "예"},
         also_ok={"카드실적@우리은행": "아니오", "급여_연금이체@국민은행": "아니오"}),
    dict(n=14, text="만 65세라 비과세 되는지 궁금해. 예금 1억",
         scope=dict(group=None, banks=[], kinds="예금", term=None, amount_deposit=100_000_000, amount_monthly=None),
         traded=None, answers={"고객군_자격": "예"}),
    dict(n=15, text="오픈뱅킹은 이미 등록돼 있고 쿠폰 코드는 없어",
         scope=dict(group=None, banks=[], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=None, answers={"오픈뱅킹_타행계좌등록": "예", "쿠폰_코드_추천인": "아니오"}),
    dict(n=16, text="SBI저축은행이랑 OK저축은행 써봤어. 예금으로 2천만원",
         scope=dict(group="savingsbank", banks=[], kinds="예금", term=None, amount_deposit=20_000_000, amount_monthly=None),
         traded=["SBI저축은행", "OK저축은행"], answers={}),
    dict(n=17, text="적금 들면서 같은 은행 청약통장도 만들 생각이야. 은행은 아직 안 정했어",
         scope=dict(group="bank", banks=[], kinds="적금", term=None, amount_deposit=None, amount_monthly=None),
         traded=None, answers={"타상품_보유동시가입": "예"}),
    dict(n=18, text="케이뱅크 첫 거래야. 급여이체는 못 옮겨",
         scope=dict(group="bank", banks=["주식회사 케이뱅크"], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=[], answers={"급여_연금이체@주식회사 케이뱅크": "아니오"}, also_ok={"첫거래_신규고객@주식회사 케이뱅크": "예"}),
    dict(n=19, text="목표 금액 채우는 건 자신 없고, 그냥 넣을 수 있는 만큼만",
         scope=dict(group=None, banks=[], kinds=None, term=None, amount_deposit=None, amount_monthly=None),
         traded=None, answers={"목표달성_납입실적": "아니오"}),
    dict(n=20, text="예금이랑 적금 다 보여줘. 12개월. 은행 상관없음",
         scope=dict(group=None, banks=[], kinds=None, term=12, amount_deposit=None, amount_monthly=None),
         traded=None, answers={}),
]
