#!/bin/sh
set -eu

export CUDA_HOME=/usr
export VLLM_USE_DEEP_GEMM=0
export VLLM_USE_FLASHINFER_MOE_FP16=0
export VLLM_USE_FLASHINFER_SAMPLER=0
export OMP_NUM_THREADS=4

vllm serve Qwen/Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name local-model-qwen2.5-coder-14b-awq \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --trust-remote-code \
  --language-model-only \
  --override-generation-config '{"max_new_tokens":8192}' \
  --enable-prefix-caching \
  --max-model-len 32768 \
  --max-num-seqs 4 \
  --gpu-memory-utilization 0.94 \
  --host 0.0.0.0 \
  --port 8001
