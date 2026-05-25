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

Create `~/.config/opencode/config.json`.

This setup intentionally uses a lightweight `local` agent by default. The
default opencode build agent sends a large system prompt and tool schema, which
is slow on a local 27B model. Switch to `/agent build` only when file editing
tools are needed.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openai": {
      "name": "Local vLLM",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "apiKey": "dummy",
        "baseURL": "http://localhost:8000/v1"
      },
      "models": {
        "local-model-qwen3.6-27b-awq": {
          "name": "Qwen3.6 27B AWQ",
          "family": "qwen",
          "reasoning": true,
          "tool_call": true,
          "temperature": true,
          "limit": {
            "context": 131072,
            "output": 4096
          }
        }
      }
    }
  },
  "model": "openai/local-model-qwen3.6-27b-awq",
  "small_model": "openai/local-model-qwen3.6-27b-awq",
  "default_agent": "local",
  "compaction": {
    "auto": false,
    "prune": false
  },
  "agent": {
    "local": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "mode": "primary",
      "description": "Lightweight local chat agent without tools.",
      "temperature": 0.6,
      "top_p": 0.95,
      "tools": {
        "bash": false,
        "read": false,
        "glob": false,
        "grep": false,
        "edit": false,
        "write": false,
        "task": false,
        "webfetch": false,
        "todowrite": false,
        "skill": false,
        "question": false
      }
    },
    "build": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "temperature": 0.6,
      "top_p": 0.95,
      "tools": {
        "bash": true,
        "read": true,
        "glob": true,
        "grep": true,
        "edit": true,
        "write": true,
        "task": false,
        "webfetch": false,
        "todowrite": false,
        "skill": false,
        "question": false
      }
    },
    "general": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "temperature": 0.6,
      "top_p": 0.95,
      "tools": {
        "bash": false,
        "read": false,
        "glob": false,
        "grep": false,
        "edit": false,
        "write": false,
        "task": false,
        "webfetch": false,
        "todowrite": false,
        "skill": false,
        "question": false
      }
    },
    "plan": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "temperature": 0.6,
      "top_p": 0.95,
      "tools": {
        "bash": false,
        "read": false,
        "glob": false,
        "grep": false,
        "edit": false,
        "write": false,
        "task": false,
        "webfetch": false,
        "todowrite": false,
        "skill": false,
        "question": false
      }
    },
    "explore": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "temperature": 0.6,
      "top_p": 0.95,
      "tools": {
        "bash": true,
        "read": true,
        "glob": true,
        "grep": true,
        "edit": false,
        "write": false,
        "task": false,
        "webfetch": false,
        "todowrite": false,
        "skill": false,
        "question": false
      }
    },
    "title": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "disable": true,
      "temperature": 0.6,
      "top_p": 0.95
    },
    "summary": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "disable": true,
      "temperature": 0.6,
      "top_p": 0.95
    },
    "compaction": {
      "model": "openai/local-model-qwen3.6-27b-awq",
      "temperature": 0.6,
      "top_p": 0.95
    }
  },
  "mcp": {
    "notion": {
      "type": "local",
      "command": ["npx", "-y", "@notionhq/notion-mcp-server"],
      "environment": {
        "NOTION_TOKEN": "YOUR_NOTION_TOKEN"
      },
      "enabled": false
    }
  }
}
```

Notes:

- `baseURL` must include `/v1`; otherwise opencode will call
  `/chat/completions` instead of `/v1/chat/completions`.
- `small_model` is set explicitly so opencode does not fall back to a hosted
  model such as `gpt-5-nano` for title/summary/compaction tasks.
- Automatic compaction is disabled. Use `/compact` manually if needed.
- Notion MCP is disabled by default because its tool schema is large and slows
  local inference. Enable it only when needed.

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

The proxy is **optional** — the vLLM startup script already sets `max_new_tokens=4096` in `override-generation-config`, making the proxy unnecessary for opencode. It remains useful for clients that do not respect the server-side generation config.

## vLLM Server Options

Key flags used in `start_vllm_qwen3_6_27b_awq.sh`:

| Flag                               | Value                           | Purpose                                  |
| ---------------------------------- | ------------------------------- | ---------------------------------------- |
| `--served-model-name`            | `local-model-qwen3.6-27b-awq` | Model name exposed via API               |
| `--enable-auto-tool-choice`      | —                              | Enable function/tool calling             |
| `--tool-call-parser`             | `qwen3_coder`                 | Qwen3 tool format parser                 |
| `--reasoning-parser`             | `qwen3`                       | Qwen3 reasoning format parser            |
| `--default-chat-template-kwargs` | `{"enable_thinking":false}`   | Disable chain-of-thought thinking tokens |
| `--override-generation-config`   | `{"max_new_tokens":4096}`     | Server-side generation token limit       |
| `--max-model-len`                | `131072`                      | Context window                           |
| `--cpu-offload-gb`               | `8`                           | Offload some layers to CPU               |
| `--max-num-seqs`                 | `2`                           | Max concurrent sequences                 |
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
opencode --model openai/local-model-qwen3.6-27b-awq --agent local
```
