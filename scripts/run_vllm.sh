#!/usr/bin/env bash
# vLLM OpenAI 호환 서버를 Docker로 띄운다 (WSL2 + Docker Desktop).
# finance_verifier `scripts/run_vllm_container.sh`를 재사용하고 세 가지를 바꿨다.
#   1) --max-model-len 6144 — 우리 파일럿 프롬프트는 공시 원문 전문을 넣는다.
#      들어가야 한다. 2048이면 vLLM이 400을 낸다 ("max_tokens cannot be greater than max_model_len")
#   2) vLLM 컴파일 캐시를 호스트에 마운트 — 없으면 컨테이너를 다시 띄울 때마다
#      torch.compile 약 3.5분을 다시 지불한다(실측). 모델을 왕복시킬 때 특히 크다
#   3) 모델 사전 다운로드는 `hf` 를 쓴다 — 이미지의 huggingface-cli 는 deprecated 라
#      아무 일도 하지 않고 exit 0 으로 끝난다(실측)
#
# 사용법: scripts/run_vllm.sh <model> [extra vllm args...]
#   Git Bash에서 -v 마운트는 MSYS_NO_PATHCONV=1 + Windows 경로여야 한다
#   (없으면 경로가 뭉개져 마운트가 조용히 실패하고 모델을 다시 받는다)
#
# 모델 사전 다운로드:
#   MSYS_NO_PATHCONV=1 docker run --rm \
#     -v "C:\Users\user\.cache\huggingface:/root/.cache/huggingface" \
#     --entrypoint hf vllm/vllm-openai:latest download <model>
set -euo pipefail

MODEL="${1:?usage: run_vllm.sh <model_name> [extra vllm args...]}"
shift || true

CONTAINER_NAME="vllm-server"
HF_CACHE_WIN_PATH='C:\Users\user\.cache\huggingface'
VLLM_CACHE_WIN_PATH='C:\Users\user\.cache\vllm'

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

MSYS_NO_PATHCONV=1 docker run -d --name "$CONTAINER_NAME" --gpus all \
  -e VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
  -v "${HF_CACHE_WIN_PATH}:/root/.cache/huggingface" \
  -v "${VLLM_CACHE_WIN_PATH}:/root/.cache/vllm" \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model "$MODEL" \
  --gpu-memory-utilization 0.85 \
  --max-model-len 6144 \
  --max-num-seqs 4 \
  "$@" >/dev/null

echo "started: $MODEL -> http://localhost:8000  (logs: docker logs -f $CONTAINER_NAME)"
