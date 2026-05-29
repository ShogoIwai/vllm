#!/bin/sh
set -eu

export CUDA_HOME=/usr
export VLLM_USE_DEEP_GEMM=0
export VLLM_USE_FLASHINFER_MOE_FP16=0
export VLLM_USE_FLASHINFER_SAMPLER=0
export OMP_NUM_THREADS=4

# tool-call-parser=qwen3_xml: qwen3_coder は長文 ctx でツール呼び出し時に無限「!」ループ
#   (next_token_id=0) に陥り、hermes はストリーミング時に生 <tool_call> XML を漏らす。
#   qwen3_xml が長文・高速ストリーミングを両立 (vLLM 0.21.0 で実装確認済み)。
# reasoning-parser=qwen3: <think> 思考ブロックを隔離し、編集系ツールの引数に思考ログが
#   混入するのを防ぐ。
# chunked-prefill 有効時の Mamba アライメントエラー回避のため max-num-batched-tokens=4096 固定。
vllm serve QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ \
  --served-model-name local-model-qwen3-coder-30b-a3b-awq \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml \
  --reasoning-parser qwen3 \
  --trust-remote-code \
  --language-model-only \
  --override-generation-config '{"max_new_tokens":8192}' \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-batched-tokens 4096 \
  --max-model-len 131072 \
  --cpu-offload-gb 2 \
  --max-num-seqs 2 \
  --kv-cache-dtype fp8 \
  --gpu-memory-utilization 0.95 \
  --host 0.0.0.0 \
  --port 8000
