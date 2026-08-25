# -*- coding: utf-8 -*-
"""파일럿 질문 30개를 한 모델에 돌린다 (`docs/spec/prereg-02-pilot.md` §6).

실행 조건은 사전등록에 고정돼 있다 — temperature 0, 재시도 없음,
로컬 k=1 / API k=3, chat_template_kwargs {"enable_thinking": false}.
원 응답 전문은 data/pilot/raw/ 에 저장하고 커밋하지 않는다.

사용법:
    python src/pilot/run_model.py qwen      [YYYYMMDD]
    python src/pilot/run_model.py kanana    [YYYYMMDD]
    python src/pilot/run_model.py haiku     [YYYYMMDD]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = REPO_ROOT / "data" / "pilot"
RAW_DIR = PILOT_DIR / "raw"

MODELS = {
    "qwen":   {"id": "Intel/Qwen3.5-4B-int4-AutoRound", "backend": "vllm", "k": 1},
    "kanana": {"id": "kakaocorp/kanana-2-3b-instruct",  "backend": "vllm", "k": 1},
    "haiku":  {"id": "claude-haiku-4-5-20251001",       "backend": "anthropic", "k": 3},
    # Sonnet 5는 temperature/top_p/top_k가 제거된 모델이다 (전달하면 400).
    # 온도를 고정할 수 없고 thinking이 기본 adaptive로 켜진다 — prereg §6에 기록.
    "sonnet": {"id": "claude-sonnet-5", "backend": "anthropic", "k": 3, "temperature": False},
}
MAX_TOKENS = 4096  # 512 → 6건, 1024 → Sonnet 32건이 잘렸다. 네 모델 공통 (prereg §6)
TIMEOUT = 180


def api_key() -> str:
    for env_path in (REPO_ROOT / ".env", REPO_ROOT.parent / "finance_verifier" / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*ANTHROPIC_API_KEY\s*=\s*(.+)\s*$", line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                if key:
                    return key
    raise SystemExit("ANTHROPIC_API_KEY를 찾지 못했다 (.env 확인)")


def post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_vllm(model_id: str, prompt: str) -> dict:
    payload = {"model": model_id, "temperature": 0, "max_tokens": MAX_TOKENS,
               "messages": [{"role": "user", "content": prompt}],
               "chat_template_kwargs": {"enable_thinking": False}}
    out = post("http://localhost:8000/v1/chat/completions", payload, {})
    choice = out["choices"][0]
    return {"text": choice["message"]["content"], "finish_reason": choice.get("finish_reason"),
            "usage": out.get("usage", {})}


def call_anthropic(model_id: str, prompt: str, key: str, use_temperature: bool = True) -> dict:
    payload = {"model": model_id, "max_tokens": MAX_TOKENS,
               "messages": [{"role": "user", "content": prompt}]}
    if use_temperature:
        payload["temperature"] = 0
    out = post("https://api.anthropic.com/v1/messages", payload,
               {"x-api-key": key, "anthropic-version": "2023-06-01"})
    text = "".join(b.get("text", "") for b in out.get("content", []))
    return {"text": text, "finish_reason": out.get("stop_reason"), "usage": out.get("usage", {})}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in MODELS:
        raise SystemExit(f"사용법: python {Path(__file__).name} {{{'|'.join(MODELS)}}} [YYYYMMDD]")
    tag = sys.argv[1]
    stamp = sys.argv[2] if len(sys.argv) > 2 else "20260824"
    spec = MODELS[tag]
    questions = json.loads((PILOT_DIR / f"questions_{stamp}.json").read_text(encoding="utf-8"))["questions"]
    key = api_key() if spec["backend"] == "anthropic" else ""

    print(f"[{tag}] {spec['id']} · {len(questions)}문항 × k={spec['k']} · temperature 0")
    runs, t0 = [], time.time()
    for i, q in enumerate(questions, 1):
        for rep in range(spec["k"]):
            started = time.time()
            try:
                if spec["backend"] == "vllm":
                    res = call_vllm(spec["id"], q["prompt"])
                else:
                    res = call_anthropic(spec["id"], q["prompt"], key,
                                         spec.get("temperature", True))
                res["error"] = None
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError) as exc:
                detail = exc.read().decode("utf-8", "replace")[:300] if hasattr(exc, "read") else str(exc)
                res = {"text": "", "finish_reason": None, "usage": {},
                       "error": f"{type(exc).__name__}: {detail}"}
            res.update({"qid": q["qid"], "rep": rep, "stratum": q["stratum"],
                        "state_pattern": q["state_pattern"], "elapsed_s": round(time.time() - started, 2)})
            runs.append(res)
        done = sum(1 for r in runs if r["error"] is None)
        print(f"  {i:2d}/{len(questions)} {q['qid']} {q['stratum']:5s} "
              f"{runs[-1]['elapsed_s']:5.1f}s  누적 성공 {done}/{len(runs)}", flush=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{tag}_{stamp}.json"
    out.write_text(json.dumps({"model_tag": tag, "model_id": spec["id"], "backend": spec["backend"],
                               "k": spec["k"], "snapshot": stamp, "max_tokens": MAX_TOKENS,
                               "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    errs = [r for r in runs if r["error"]]
    print(f"\n총 {len(runs)}회 · 실패 {len(errs)}회 · {time.time() - t0:.0f}초 → {out.relative_to(REPO_ROOT)}")
    for r in errs[:3]:
        print(f"  실패 [{r['qid']}] {r['error'][:120]}")


if __name__ == "__main__":
    main()
