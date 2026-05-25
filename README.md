# Qwen3.6-27B-AWQ + vLLM + opencode Setup

Run `QuantTrio/Qwen3.6-27B-AWQ` on a single RTX 3090 24GB via vLLM and consume it as an OpenAI-compatible API from [opencode](https://opencode.ai).

```
opencode → OpenAI compatible API → vLLM (:8000) → Qwen3.6-27B-AWQ
```

## Directory Contents

| File                              | Description                                                 |
| --------------------------------- | ----------------------------------------------------------- |
| `start_vllm_qwen3_6_27b_awq.sh` | vLLM server startup script                                  |
| `proxy.py`                      | Legacy max_tokens-capping proxy for Claude Code (port 8001) |
| `README.md`                     | This file                                                   |

## Requirements

- Python 3.9+, CUDA 12.x
- NVIDIA GPU with ≥24 GB VRAM (RTX 3090 / 4090 / A6000)
- vLLM 0.21.0

## Quick Start

### 1. Install vLLM

```bash
pip install vllm==0.21.0
pip install flashinfer        # MOE optimization
```

### 2. Authenticate with Hugging Face

```bash
pip install huggingface_hub
huggingface-cli login
```

Get a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens). The model (~16 GB, AWQ quantized) downloads automatically on first `vllm serve`.

### 3. Start vLLM Server

```bash
cd /mnt/hdd/edgeai/rep/vllm
./start_vllm_qwen3_6_27b_awq.sh
```

The server listens on `http://0.0.0.0:8000`.

### 4. Install opencode

```bash
npm install -g opencode-ai
# or
curl -fsSL https://opencode.ai/install | sh
```

### 5. Configure opencode

Create `~/.config/opencode/config.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openai": {
      "apiKey": "dummy",
      "baseURL": "http://localhost:8000"
    }
  },
  "model": "openai/local-model-qwen3.6-27b-awq",
  "agent": {
    "build":   { "temperature": 0.6, "top_p": 0.95 },
    "general": { "temperature": 0.6, "top_p": 0.95 },
    "plan":    { "temperature": 0.6, "top_p": 0.95 },
    "explore": { "temperature": 0.6, "top_p": 0.95 }
  }
}
```

> `temperature`/`top_p` must go under `agent.<name>`, not at the top level.

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

If a client sends `max_tokens > 8192`, the proxy silently caps it to `8192`. To use it, set `baseURL` in opencode config to `http://localhost:8001`.

The proxy is **optional** — the vLLM startup script already sets `max_new_tokens=8192` in `override-generation-config`, making the proxy unnecessary for opencode. It remains useful for clients that do not respect the server-side generation config.

## vLLM Server Options

Key flags used in `start_vllm_qwen3_6_27b_awq.sh`:

| Flag                               | Value                           | Purpose                                  |
| ---------------------------------- | ------------------------------- | ---------------------------------------- |
| `--served-model-name`            | `local-model-qwen3.6-27b-awq` | Model name exposed via API               |
| `--enable-auto-tool-choice`      | —                              | Enable function/tool calling             |
| `--tool-call-parser`             | `qwen3_coder`                 | Qwen3 tool format parser                 |
| `--reasoning-parser`             | `qwen3`                       | Qwen3 reasoning format parser            |
| `--default-chat-template-kwargs` | `{"enable_thinking":false}`   | Disable chain-of-thought thinking tokens |
| `--override-generation-config`   | `{"max_new_tokens":8192}`     | Server-side token limit                  |
| `--max-model-len`                | `32768`                       | Context window                           |
| `--cpu-offload-gb`               | `8`                           | Offload some layers to CPU               |
| `--max-num-seqs`                 | `8`                           | Max concurrent sequences                 |
| `--gpu-memory-utilization`       | `0.94`                        | VRAM usage target                        |
| `--enable-prefix-caching`        | —                              | Cache common prefix for speed            |

## Environment Variables

Set in the startup script:

- `VLLM_USE_DEEP_GEMM=0`
- `VLLM_USE_FLASHINFER_MOE_FP16=1`
- `VLLM_USE_FLASHINFER_SAMPLER=0`
- `OMP_NUM_THREADS=4`

## Verification

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-model-qwen3.6-27b-awq",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 128
  }'

opencode --version
```
