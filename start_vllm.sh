#!/bin/sh
export CUDA_HOME=/usr
vllm serve Qwen/Qwen3-14B-AWQ \
  --served-model-name local-model \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --quantization awq_marlin \
  --max-model-len 40960 \
  --gpu-memory-utilization 0.94
