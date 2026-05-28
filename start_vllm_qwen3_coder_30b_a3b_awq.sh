#!/bin/sh
set -eu

export CUDA_HOME=/usr
export VLLM_USE_DEEP_GEMM=0
export VLLM_USE_FLASHINFER_MOE_FP16=0
export VLLM_USE_FLASHINFER_SAMPLER=0
export OMP_NUM_THREADS=4

vllm serve QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ \
  --served-model-name local-model-qwen3-coder-30b-a3b-awq \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --trust-remote-code \
  --language-model-only \
  --override-generation-config '{"max_new_tokens":8192}' \
  --enable-prefix-caching \
  --max-model-len 131072 \
  --cpu-offload-gb 2 \
  --max-num-seqs 2 \
  --kv-cache-dtype fp8 \
  --gpu-memory-utilization 0.95 \
  --host 0.0.0.0 \
  --port 8000
