// prereg-34 §A — 10명이 같은 순간에 "칸 채우기" 를 누르는 동안 다른 사람들의 "목록 보기" 가 느려지나.
//
//   browse : 0~70초 · 초당 5건 POST /screen  (은행권 12개월 · 답 없음)
//   burst  : 20초 시점 · 10 VU 동시에 POST /prefill 한 번씩 (합성 문장 10개 · 개인정보 없음)
//
// 실행:  k6 run tools/k6/prefill_burst.js            (웹 8000 · 모델 8081 이 떠 있어야 한다)
// 읽는 값: screen_before / screen_during p95 · prefill_ms 분포 · prefill_timeout 건수
import http from 'k6/http';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://127.0.0.1:8000';
const BURST_AT = 20; // s
const BURST_VUS = Number(__ENV.BURST_VUS || 10);   // 같은 순간에 누르는 사람 수 (prereg-34 §A5 · 15)

const screenBefore = new Trend('screen_before_ms', true);
const screenDuring = new Trend('screen_during_ms', true);
const prefillMs = new Trend('prefill_ms', true);
const prefillTimeout = new Counter('prefill_timeout');
const prefillFilled = new Counter('prefill_filled');

const SENTENCES = [
  '우리은행 적금 1년짜리 보고 싶어',
  '저축은행 예금 6개월로 알아보는 중',
  '카카오뱅크랑 토스뱅크 적금 비교하고 싶어. 2년',
  '농협은행 예금 2년 정도 넣을 생각',
  '신한은행은 거래 없고 국민은행만 써. 국민은행 적금 보고 싶어',
  '제주은행 적금 12개월',
  '하나은행 예금 36개월로 길게',
  '적금 짧은 기간으로 아무 은행이나',
  '부산은행이랑 경남은행 예금 비교',
  '케이뱅크 적금 1년 반',
  '수협은행 예금 6개월 생각 중',
  '광주은행 적금 3년으로 길게 가고 싶어',
  '전북은행 예금 1년',
  '아이엠뱅크 적금 2년 넣을까 고민',
  '기업은행 예금 24개월',
  'SC제일은행 정기예금 1년짜리 있나',
  '저축은행 적금 1년 아무데나',
  '토스뱅크 예금 6개월',
  '국민은행 적금 36개월 장기로',
  '신한은행 예금 12개월로 볼래',
];

export const options = {
  scenarios: {
    browse: {
      executor: 'constant-arrival-rate',
      rate: 5, timeUnit: '1s', duration: '90s',
      preAllocatedVUs: 10, maxVUs: 30,
      exec: 'browse',
    },
    burst: {
      executor: 'per-vu-iterations',
      vus: BURST_VUS, iterations: 1, startTime: `${BURST_AT}s`, maxDuration: '180s',
      exec: 'burst',
    },
  },
  summaryTrendStats: ['p(50)', 'p(95)', 'max', 'count'],
};

const FORM = { 'Content-Type': 'application/x-www-form-urlencoded' };
const testStart = Date.now();

export function browse() {
  const r = http.post(`${BASE}/screen`,
    'group=bank&term=12&snapshot=&order=hi&company=&kinds=&amount_deposit=&amount_monthly=&state_json=%7B%7D',
    { headers: FORM, timeout: '60s', tags: { kind: 'screen' } });
  const t = (Date.now() - testStart) / 1000;
  (t < BURST_AT ? screenBefore : screenDuring).add(r.timings.duration);
}

export function burst() {
  const s = SENTENCES[(__VU - 1) % SENTENCES.length];
  const body = `group=bank&term=12&snapshot=&order=hi&company=&kinds=&amount_deposit=&amount_monthly=&situation=${encodeURIComponent(s)}`;
  const r = http.post(`${BASE}/prefill`, body, { headers: FORM, timeout: '90s', tags: { kind: 'prefill' } });
  prefillMs.add(r.timings.duration);
  // 꺼짐(PREFILL_UNAVAILABLE) 과 붐빔(PREFILL_BUSY) 둘 다 실패로 센다 — 20명 시험에서 붐빔 문구를 놓친 뒤 고쳤다
  if (r.body && (r.body.includes('채울 수 없습니다') || r.body.includes('채우지 못했습니다'))) prefillTimeout.add(1);
  if (r.body && r.body.includes('문장에서 채움')) prefillFilled.add(1);
}
