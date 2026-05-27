# Qwen2.5-Coder-14B-AWQ + vLLM Setup

Run `Qwen/Qwen2.5-Coder-14B-Instruct-AWQ` on a single RTX 3090 24GB via vLLM and consume it as an OpenAI-compatible API from various clients.

```
sgpt (CLI)      → OpenAI compatible API → vLLM (:8000) → Qwen2.5-Coder-14B-Instruct-AWQ
Cline (VS Code) → OpenAI compatible API → vLLM (:8000) → Qwen2.5-Coder-14B-Instruct-AWQ
```

**Recommended client: Cline** (VS Code extension). opencode hangs on large files due to client-side token counting; sgpt works well for quick CLI tasks.

## Directory Contents

| File                                    | Description                                                        |
| --------------------------------------- | ------------------------------------------------------------------ |
| `start_vllm_qwen2_5_coder_14b_awq.sh` | vLLM server startup script — Qwen2.5-Coder-14B (fast, default)    |
| `start_vllm_qwen3_6_27b_awq.sh`       | vLLM server startup script — Qwen3.6-27B (slow, cpu-offload 10GB) |
| `sourceme`                            | bash/sh env vars (`export`)                                      |
| `sourceme.csh`                        | tcsh env vars (`setenv`)                                         |
| `proxy.py`                            | Legacy max_tokens-capping proxy for Claude Code (port 8001)        |
| `README.md`                           | This file                                                          |

## Requirements

- Python 3.9+, CUDA 12.x
- NVIDIA GPU with ≥24 GB VRAM (RTX 3090 / 4090 / A6000)
- vLLM 0.21.0

## Quick Start

### 1. Install vLLM

```bash
pip install vllm==0.21.0
```

### 2. Authenticate with Hugging Face

```bash
pip install huggingface_hub
huggingface-cli login
```

Get a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens). The model (~16 GB, AWQ quantized) downloads automatically on first `vllm serve`.

### 3. Start vLLM Server

```bash
./start_vllm_qwen2_5_coder_14b_awq.sh
```

The server listens on `http://0.0.0.0:8000`.

### 4. Configure sgpt (CLI option)

sgpt reads `API_BASE_URL` from `~/.config/shell_gpt/.sgptrc` — make sure it is set to `http://localhost:8000/v1` (not `default`). `DEFAULT_MODEL` should also be set to the local model name.

```bash
# bash / sh
source vllm/sourceme
sgpt "hello"

# tcsh
source vllm/sourceme.csh
sgpt "hello"
```

### 5. Configure Cline (Recommended)

[Cline](https://marketplace.visualstudio.com/items?itemName=saoudrizwan.claude-dev) is a VS Code extension. Install it from the Extensions marketplace, then configure:

| Field        | Value                                 |
| ------------ | ------------------------------------- |
| API Provider | `OpenAI Compatible`                 |
| Base URL     | `http://localhost:8000/v1`          |
| API Key      | `dummy`                             |
| Model ID     | `local-model-qwen2.5-coder-14b-awq` |

---

## proxy.py Usage

`proxy.py` is a legacy FastAPI proxy that caps `max_tokens` to prevent context overflow in clients that send excessive token limits. It sits between the client and vLLM on port 8001:

```
opencode → proxy :8001 → vLLM :8000
```

Start it:

```bash
python vllm/proxy.py
# Listening on http://0.0.0.0:8001
```

If a client sends `max_tokens > 8192`, the proxy silently caps it to `8192`. To use it, set `baseURL` in opencode config to `http://localhost:8001/v1` if the proxy exposes OpenAI-compatible `/v1` routes.

The proxy is **optional** — the vLLM startup script already sets `max_new_tokens=8192` in `override-generation-config`, making the proxy unnecessary for opencode. It remains useful for clients that do not respect the server-side generation config.

---

## vLLM Server Options

Key flags used in `start_vllm_qwen2_5_coder_14b_awq.sh`:

| Flag                             | Value                                 | Purpose                                        |
| -------------------------------- | ------------------------------------- | ---------------------------------------------- |
| `--served-model-name`          | `local-model-qwen2.5-coder-14b-awq` | Model name exposed via API                     |
| `--enable-auto-tool-choice`    | —                                    | Enable function/tool calling                   |
| `--tool-call-parser`           | qwen3_coder                           | Qwen2.5 tool format parser                     |
| `--trust-remote-code`          | —                                    | Allow custom model code from HuggingFace       |
| `--language-model-only`        | —                                    | Skip multimodal pipeline overhead              |
| `--override-generation-config` | `{"max_new_tokens":8192}`           | Server-side generation token limit             |
| `--max-model-len`              | `32768`                             | Context window (model max_position_embeddings) |
| `--max-num-seqs`               | `4`                                 | Max concurrent sequences                       |
| `--gpu-memory-utilization`     | `0.94`                              | VRAM usage target                              |
| `--enable-prefix-caching`      | —                                    | Cache common prefix for speed                  |

## Environment Variables

Set in the startup script:

- `CUDA_HOME=/usr`
- `VLLM_USE_DEEP_GEMM=0`
- `VLLM_USE_FLASHINFER_MOE_FP16=0`
- `VLLM_USE_FLASHINFER_SAMPLER=0`
- `OMP_NUM_THREADS=4`
