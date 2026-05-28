# Local Qwen + vLLM Setup

Run quantized Qwen models on a single GPU via vLLM and consume them as an OpenAI-compatible API from various clients.

```
sgpt (CLI)      → OpenAI compatible API → vLLM (:8000) → Qwen model
Cline (VS Code) → OpenAI compatible API → vLLM (:8000) → Qwen model
Claude Code     → MCP (stdio)           → mcp_qwen.py  → vLLM (:8000) → Qwen model  ← Recommended
```

**Recommended client: Claude Code MCP** — offloads lightweight tasks to Qwen while keeping Claude API tokens for complex reasoning. Cline is a good alternative for VS Code users; sgpt works well for quick CLI queries.

## Available Models

| Script                                    | Model                                       | Context | VRAM  | Notes                            |
| ----------------------------------------- | ------------------------------------------- | ------- | ----- | -------------------------------- |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | `QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ` | 128K    | 16 GB | **Default.** MoE 30B/3B-active, multi-file coding |
| `start_vllm_qwen3_6_27b_awq.sh`         | `QuantTrio/Qwen3.6-27B-AWQ`                 | 128K    | 16 GB | General purpose, reasoning       |
| `start_vllm_qwen2_5_coder_14b_awq.sh`   | `Qwen/Qwen2.5-Coder-14B-Instruct-AWQ`      | 32K     | 16 GB | Lightweight, fast startup        |

## Directory Contents

| File                                      | Description                                                          |
| ----------------------------------------- | -------------------------------------------------------------------- |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | vLLM startup — Qwen3-Coder-30B-A3B (128K ctx, cpu-offload 2 GB)     |
| `start_vllm_qwen3_6_27b_awq.sh`         | vLLM startup — Qwen3.6-27B (128K ctx, cpu-offload 8 GB)             |
| `start_vllm_qwen2_5_coder_14b_awq.sh`   | vLLM startup — Qwen2.5-Coder-14B (32K ctx, fast)                    |
| `sourceme`                               | bash/sh env vars (`export`)                                          |
| `sourceme.csh`                           | tcsh env vars (`setenv`)                                             |
| `mcp_qwen.py`                            | MCP server — exposes Qwen as `ask_qwen` / `ask_qwen_code` tools     |
| `proxy.py`                               | Legacy max_tokens-capping proxy for Claude Code (port 8001)          |
| `README.md`                              | This file                                                            |

## Requirements

- Python 3.9+, CUDA 12.x
- NVIDIA GPU with ≥16 GB VRAM (RTX 4080 / 3090 / 4090 / A6000)
- vLLM 0.21.0

## Quick Start

### 1. Install vLLM

```bash
sudo apt install nvidia-cuda-toolkit # if necessary
pip install vllm==0.21.0
```

### 2. Authenticate with Hugging Face

```bash
pip install huggingface_hub
huggingface-cli login
```

Get a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens). The model downloads automatically on first `vllm serve`.

### 3. Start vLLM Server

```bash
vllm/start_vllm_qwen3_coder_30b_a3b_awq.sh   # default (30B, 128K ctx)
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

### 5. Configure Cline

[Cline](https://marketplace.visualstudio.com/items?itemName=saoudrizwan.claude-dev) is a VS Code extension. Install it from the Extensions marketplace, then configure:

| Field        | Value                                        |
| ------------ | -------------------------------------------- |
| API Provider | `OpenAI Compatible`                        |
| Base URL     | `http://localhost:8000/v1`                 |
| API Key      | `dummy`                                    |
| Model ID     | `local-model-qwen3-coder-30b-a3b-awq`     |

---

## Claude Code MCP Integration (Recommended)

`mcp_qwen.py` is an MCP server that exposes the local Qwen model as two tools callable directly from Claude Code sessions. Lightweight tasks are routed to Qwen, saving Claude API tokens for complex reasoning.

```
Claude Code → MCP (stdio) → mcp_qwen.py → vLLM :8000 → Qwen3-Coder-30B-A3B
```

### Setup (one-time)

**1. Register the MCP server:**

```bash
claude mcp add -s user qwen-local python3 $REP/vllm/mcp_qwen.py
```

The `-s user` flag installs it globally (all projects). Omit it for project-local registration.

**2. Verify:**

Inside Claude Code, run `/mcp` — `qwen-local` should appear with status `connected`.

### Available tools

| Tool              | Best for                                                           |
| ----------------- | ------------------------------------------------------------------ |
| `ask_qwen`      | General questions, code explanations, summaries, translations      |
| `ask_qwen_code` | Boilerplate generation, stub implementations, language translation |

### Usage

Just ask Claude Code normally — it will call Qwen automatically for suitable tasks. You can also be explicit: "ask Qwen to …".

**Good fit:** boilerplate, short snippet explanation, comment translation, test stubs
**Not suitable:** tasks needing file access, multi-step reasoning, or tool use

> **Requires** the vLLM server to be running (`vllm/start_vllm_qwen3_coder_30b_a3b_awq.sh`).

To switch models, update `MODEL_ID` in `mcp_qwen.py` and restart Claude Code.

---

## Case Study: Haiku Delegation Mode

Switching Claude Code to the cheaper **Haiku** model cuts API costs significantly, but Haiku has lower reasoning capability than Sonnet/Opus. The delegation pattern solves this: when Haiku is active, it routes generation and reasoning tasks to the local Qwen model via MCP, **minimizing Claude API token consumption while keeping output quality high**.

### Architecture

```
User → Claude Code (Haiku) → MCP (stdio) → mcp_qwen.py → vLLM :8000 → Qwen3-Coder-30B
```

Haiku acts as an orchestrator — handling file I/O and tool calls — while Qwen handles the actual generation and reasoning.

### CLAUDE.md Configuration

Add rules like the following to `~/.claude/CLAUDE.md` to control Haiku's behavior automatically when that model is active.

```markdown
## Haiku Delegation Mode

When your model ID contains "haiku":

**Goal:** Minimize Claude API token consumption by delegating to the local Qwen model via MCP.

### Routing Rules

1. **Q&A / explanation / summary / translation**
   → `ask_qwen(prompt=<full user message>)` — return verbatim

2. **Code generation / refactoring / unit tests**
   → `ask_qwen_code(language=<lang>, prompt=<full user message>)` — return verbatim

3. **Tasks requiring file context (read-then-ask pattern)**
   → Haiku reads the file with Read/Bash → passes the full text content as part of the prompt to `ask_qwen` / `ask_qwen_code` → applies the result with Edit/Write
   → Qwen itself does **not** access the filesystem; it receives only the text Haiku provides
   → If total content exceeds ~8K tokens, process one file at a time

> **Not supported by `ask_qwen` / `ask_qwen_code`:**
> tasks that require tool use, filesystem access inside Qwen, or stateful multi-step reasoning across calls.
> These are single-shot text-in / text-out calls.
```

### Token Limits

| Limit | Value | Source |
| ----- | ----- | ------ |
| Output per call (client) | **2,048 tokens** | `mcp_qwen.py` `max_tokens=2048` (takes precedence) |
| Output ceiling (server) | 8,192 tokens | `--override-generation-config max_new_tokens:8192` |
| Context window | **128K tokens** | `--max-model-len 131072` |
| Effective input budget | **≤ ~126K tokens** | 131072 − 2048 |

**Practical guideline:** keep each `ask_qwen` prompt under ~8K tokens for fast responses. For large files, pass one file per call and combine results yourself.

### Benefits

- Claude API charges reduced to near zero (only file I/O and MCP orchestration run on Haiku)
- Code generation, explanation, and refactoring run entirely on local GPU
- Output quality approaches Sonnet for generation tasks

### Caveats

- Haiku must not generate or reason on its own — breaking the delegation rules wastes API tokens
- Return `ask_qwen` / `ask_qwen_code` output verbatim; do not add Haiku commentary on top
- Requires both the MCP server (`mcp_qwen.py`) and the vLLM server to be running

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

If a client sends `max_tokens > 8192`, the proxy silently caps it to `8192`. The proxy is **optional** — the vLLM startup scripts already set `max_new_tokens=8192` via `override-generation-config`.

---

## vLLM Server Options

Key flags used in `start_vllm_qwen3_coder_30b_a3b_awq.sh`:

| Flag                             | Value                                      | Purpose                                        |
| -------------------------------- | ------------------------------------------ | ---------------------------------------------- |
| `--served-model-name`          | `local-model-qwen3-coder-30b-a3b-awq`   | Model name exposed via API                     |
| `--enable-auto-tool-choice`    | —                                          | Enable function/tool calling                   |
| `--tool-call-parser`           | `qwen3_coder`                            | Qwen3 tool format parser                       |
| `--trust-remote-code`          | —                                          | Allow custom model code from HuggingFace       |
| `--language-model-only`        | —                                          | Skip multimodal pipeline overhead              |
| `--override-generation-config` | `{"max_new_tokens":8192}`                | Server-side generation token limit             |
| `--max-model-len`              | `131072`                                 | Context window (128K)                          |
| `--cpu-offload-gb`             | `2`                                      | Offload 2 GB of weights to CPU RAM for KV cache headroom |
| `--max-num-seqs`               | `2`                                      | Max concurrent sequences                       |
| `--kv-cache-dtype`             | `fp8`                                    | FP8 KV cache to reduce VRAM usage              |
| `--gpu-memory-utilization`     | `0.95`                                   | VRAM usage target                              |
| `--enable-prefix-caching`      | —                                          | Cache common prefix (effective for multi-file work) |

## Environment Variables

Set in the startup scripts:

- `CUDA_HOME=/usr`
- `VLLM_USE_DEEP_GEMM=0`
- `VLLM_USE_FLASHINFER_MOE_FP16=0`
- `VLLM_USE_FLASHINFER_SAMPLER=0`
- `OMP_NUM_THREADS=4`
