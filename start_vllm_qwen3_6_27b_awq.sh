#!/bin/sh
set -eu

export CUDA_HOME=/usr
export VLLM_USE_DEEP_GEMM=0
export VLLM_USE_FLASHINFER_MOE_FP16=1
export VLLM_USE_FLASHINFER_SAMPLER=0
export OMP_NUM_THREADS=4

vllm serve QuantTrio/Qwen3.6-27B-AWQ \
  --served-model-name local-model-qwen3.6-27b-awq \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --trust-remote-code \
  --language-model-only \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --override-generation-config '{"max_new_tokens":4096}' \
  --enable-prefix-caching \
  --max-model-len 131072 \
  --cpu-offload-gb 8 \
  --max-num-seqs 2 \
  --gpu-memory-utilization 0.94 \
  --host 0.0.0.0 \
  --port 8000
