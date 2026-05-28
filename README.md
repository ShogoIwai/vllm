# Local LLM Workflow — vLLM + Claude Code + Codex

The goal of this repository is to build a workflow that connects the following tools.

| Tool                   | Role                                          |
| ---------------------- | --------------------------------------------- |
| **Claude Code**  | AI coding assistant (CLI)                     |
| **Codex**        | AI coding assistant (Claude Code plugin)      |
| **vLLM + Qwen**  | Local LLM server (OpenAI-compatible API)      |
| **sgpt / Cline** | Clients for standalone local LLM verification |

## Workflow Overview

```
Claude Code ──── review-gate integration ──── Codex
     │                                           │
     │                                        MCP (stdio)
     │                                           │
     │                                        mcp_qwen.py (same script used by Claude Code)
     │                                           │
     └─ MCP (stdio) ──── mcp_qwen.py ──── vLLM (:8000) ──── Qwen model
                               ↑
sgpt (CLI)      → OpenAI API ──┤
Cline (VS Code) → OpenAI API ──┘
```

**Reducing token / message consumption:**

- **Claude Code**: When switched to a lightweight model (e.g. Haiku), core inference can be delegated to the local Qwen via MCP. This minimizes Claude API token consumption while maintaining output quality.
- **Codex**: Delegation depends on the active cloud model. With `gpt-5.4-mini`, Codex acts as a routing/orchestration layer and delegates core reasoning and generation to local Qwen. With stronger GPT-5.x models, Codex normally delegates only simple subtasks such as boilerplate generation, comment translation, and short summaries.

**Standalone local LLM verification:**
sgpt (CLI) and Cline (VS Code extension) can be used to verify the vLLM server and Qwen model independently of Claude Code.

---

## Available Models

| Script                                    | Model                                          | Context | VRAM  | Notes                                                   |
| ----------------------------------------- | ---------------------------------------------- | ------- | ----- | ------------------------------------------------------- |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | `QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ` | 128K    | 16 GB | **Default.** MoE 30B/3B-active, multi-file coding |
| `start_vllm_qwen3_6_27b_awq.sh`         | `QuantTrio/Qwen3.6-27B-AWQ`                  | 128K    | 16 GB | General purpose, reasoning                              |
| `start_vllm_qwen2_5_coder_14b_awq.sh`   | `Qwen/Qwen2.5-Coder-14B-Instruct-AWQ`        | 32K     | 16 GB | Lightweight, fast startup                               |

## Directory Contents

| File                                      | Description                                                          |
| ----------------------------------------- | -------------------------------------------------------------------- |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | vLLM startup — Qwen3-Coder-30B-A3B (128K ctx, cpu-offload 2 GB)     |
| `start_vllm_qwen3_6_27b_awq.sh`         | vLLM startup — Qwen3.6-27B (128K ctx, cpu-offload 8 GB)             |
| `start_vllm_qwen2_5_coder_14b_awq.sh`   | vLLM startup — Qwen2.5-Coder-14B (32K ctx, fast)                    |
| `proxy.py`                              | Legacy max_tokens-capping proxy for Claude Code (port 8001)          |
| `sourceme`                              | bash/sh env vars (`export`)                                        |
| `sourceme.csh`                          | tcsh env vars (`setenv`)                                           |
| `mcp_qwen.py`                           | MCP server — exposes Qwen as `ask_qwen` / `ask_qwen_code` tools |
| `README.md`                             | This file                                                            |

---

## Requirements

- Python 3.9+, CUDA 12.x
- NVIDIA GPU with ≥16 GB VRAM (RTX 4080 / 3090 / 4090 / A6000)
- vLLM 0.21.0

## vLLM Server Options

Key flags used in `start_vllm_qwen3_coder_30b_a3b_awq.sh`:

| Flag                             | Value                                   | Purpose                                                  |
| -------------------------------- | --------------------------------------- | -------------------------------------------------------- |
| `--served-model-name`          | `local-model-qwen3-coder-30b-a3b-awq` | Model name exposed via API                               |
| `--enable-auto-tool-choice`    | —                                      | Enable function/tool calling                             |
| `--tool-call-parser`           | `qwen3_coder`                         | Qwen3 tool format parser                                 |
| `--trust-remote-code`          | —                                      | Allow custom model code from HuggingFace                 |
| `--language-model-only`        | —                                      | Skip multimodal pipeline overhead                        |
| `--override-generation-config` | `{"max_new_tokens":8192}`             | Server-side generation token limit                       |
| `--max-model-len`              | `131072`                              | Context window (128K)                                    |
| `--cpu-offload-gb`             | `2`                                   | Offload 2 GB of weights to CPU RAM for KV cache headroom |
| `--max-num-seqs`               | `2`                                   | Max concurrent sequences                                 |
| `--kv-cache-dtype`             | `fp8`                                 | FP8 KV cache to reduce VRAM usage                        |
| `--gpu-memory-utilization`     | `0.95`                                | VRAM usage target                                        |
| `--enable-prefix-caching`      | —                                      | Cache common prefix (effective for multi-file work)      |

## Environment Variables

Set in the startup scripts:

- `CUDA_HOME=/usr`
- `VLLM_USE_DEEP_GEMM=0`
- `VLLM_USE_FLASHINFER_MOE_FP16=0`
- `VLLM_USE_FLASHINFER_SAMPLER=0`
- `OMP_NUM_THREADS=4`

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

| Field        | Value                                   |
| ------------ | --------------------------------------- |
| API Provider | `OpenAI Compatible`                   |
| Base URL     | `http://localhost:8000/v1`            |
| API Key      | `dummy`                               |
| Model ID     | `local-model-qwen3-coder-30b-a3b-awq` |

## 6. Claude Code MCP Integration (Recommended)

`mcp_qwen.py` is an MCP server that exposes the local Qwen model as two tools callable directly from Claude Code sessions. When Claude Code runs on a lightweight model such as Haiku, routing rules can delegate core reasoning and generation to Qwen while Claude Code handles file I/O, tool calls, and orchestration.

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

Just ask Claude Code normally — it will call Qwen automatically when the configured rules say the task should be delegated. You can also be explicit: "ask Qwen to …".

**Good fit:** boilerplate, short snippet explanation, comment translation, test stubs, file-context tasks (Claude reads files and passes content to Qwen)
**Not suitable for Qwen directly:** tasks requiring Qwen itself to access the filesystem, call tools, or maintain state across calls — for those, Claude Code reads/searches files with its own tools and passes only the relevant text to Qwen

> **Requires** the vLLM server to be running (`vllm/start_vllm_qwen3_coder_30b_a3b_awq.sh`).

To switch models, update `MODEL_ID` in `mcp_qwen.py` and restart Claude Code.

## 7. Codex MCP Integration (Recommended)

The same `mcp_qwen.py` server can be registered with the Codex CLI. Codex can then call
`ask_qwen` / `ask_qwen_code` during its runs to offload work to the local GPU,
reducing OpenAI API token consumption.

```
Codex CLI → MCP (stdio) → mcp_qwen.py → vLLM :8000 → Qwen3-Coder-30B-A3B
```

### Setup (one-time)

**1. Register the MCP server:**

```bash
codex mcp add qwen-local -- python3 $REP/vllm/mcp_qwen.py
```

This writes a `[mcp_servers.qwen-local]` entry to `~/.codex/config.toml` globally.

**2. Verify:**

```bash
codex mcp list
# qwen-local  python3  .../mcp_qwen.py  -  enabled
```

**3. Keep delegation rules in `~/.codex/AGENTS.md`:**

The `AGENTS.md` file is loaded by Codex at the start of each session. Keep the executable routing
rules there; this README documents the setup and expected behavior.

### Routing modes

| Active Codex model                     | Codex role                   | Qwen delegation scope                                                                                 |
| -------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| `gpt-5.4-mini` / `gpt5.4-mini`     | Routing and orchestration    | Delegate Q&A, summaries, translation, code generation, refactoring, tests, and file-context reasoning |
| Stronger GPT-5.x models                | Primary reasoning/generation | Delegate only simple, self-contained subtasks                                                         |

For `gpt-5.4-mini`, Codex should read/search files locally, pass the relevant content to Qwen, apply the returned edits, and run verification commands. Qwen does not access files by path; it receives only text provided by Codex.

For stronger GPT-5.x models, the optional delegation logic is:

| Task type                                                    | Tool to use                         |
| ------------------------------------------------------------ | ----------------------------------- |
| Boilerplate/stub generation, language translation            | `ask_qwen_code(language, prompt)` |
| Comment/docstring translation, short explanations, summaries | `ask_qwen(prompt)`                |
| Multi-step reasoning, root-cause analysis, architecture, cross-file analysis | Codex handles directly |

---

## Case Study: Lightweight Delegation Mode

Lightweight cloud models can be used as orchestration layers while local Qwen performs the core reasoning and generation. This pattern applies to both **Claude Code with Haiku** and **Codex with `gpt-5.4-mini`**.

### Architecture

```
User → Claude Code (Haiku)     → MCP (stdio) → mcp_qwen.py → vLLM :8000 → Qwen3-Coder-30B
User → Codex (gpt-5.4-mini)   → MCP (stdio) → mcp_qwen.py → vLLM :8000 → Qwen3-Coder-30B
```

The cloud model handles orchestration: reading files, running searches, applying edits, and verifying results. Qwen handles the text-in/text-out reasoning or generation step.

### Configuration locations

| Client      | Lightweight model trigger                             | Routing rules file      |
| ----------- | ----------------------------------------------------- | ----------------------- |
| Claude Code | Model ID contains `haiku`                           | `~/.claude/CLAUDE.md` |
| Codex       | Model ID contains `gpt-5.4-mini` or `gpt5.4-mini` | `~/.codex/AGENTS.md`  |

### Shared routing contract

Keep executable rules in the client-specific configuration file. The common contract is:

- The cloud client handles file I/O, searches, edits, tool calls, and verification.
- Qwen receives only prompt text supplied by the cloud client; it cannot access paths, tools, or prior calls.
- `ask_qwen` is for prose tasks such as Q&A, explanations, summaries, and translation.
- `ask_qwen_code` is for code generation, refactoring, test skeletons, and code translation.
- For lightweight routing models, delegate each reasoning or generation step to Qwen.
- For stronger models, delegate only simple self-contained subtasks and keep root-cause analysis, architecture, and broad cross-file reasoning in the cloud model.

### Token Limits

| Limit                    | Value                     | Source                                                 |
| ------------------------ | ------------------------- | ------------------------------------------------------ |
| Output per call (client) | **≤ 2,048 tokens**  | `mcp_qwen.py` `max_tokens=2048` (takes precedence) |
| Output ceiling (server)  | 8,192 tokens              | `--override-generation-config max_new_tokens:8192`   |
| Context window           | **128K tokens**     | `--max-model-len 131072`                             |
| Effective input budget   | **≤ ~126K tokens** | 131072 − 2048                                         |

**Practical guideline:** keep each `ask_qwen` prompt under ~8K tokens for fast responses. For large files, pass one file per call and combine results yourself.

### Benefits

- Cloud API charges reduced substantially because only file I/O, MCP orchestration, and verification run on the cloud model
- Code generation, explanation, and refactoring run entirely on local GPU
- The same local model behavior is shared across Claude Code and Codex

### Caveats

- The lightweight cloud model should not perform the core generation or reasoning itself; breaking the delegation rules wastes API tokens
- Return `ask_qwen` / `ask_qwen_code` output directly unless a short operational note is needed
- Requires both the MCP server (`mcp_qwen.py`) and the vLLM server to be running

---

## Tips: Review Gate Token Reduction Strategies

When Codex Review Gate is enabled, tokens are consumed heavily during each adversarial review. Currently, the following two methods are applied.

### Active Reduction Methods

#### ① `--review-effort=minimal` (High token reduction)

```bash
/codex:setup --review-effort=minimal
```

Significantly reduces token consumption by minimizing review depth.

#### ② `--runtime=shared` (Speed improvement)

```bash
/codex:setup --runtime=shared
```

Reduces sandbox startup overhead and enables resource reuse across multiple turns.

---

## Tips: Codex stop-review-gate rg Process Lingering Issue

Codex's `stop-review-gate` hook spawns `codex-companion.mjs`, which scans the repository with `rg .`. After the task completes or times out, child `rg` processes can remain orphaned — keeping load average elevated.

### Fix: Claude Code `Stop` Hook

Add the following to `~/.claude/settings.json`. Claude Code runs it automatically when each session ends, killing any lingering `rg` processes before they accumulate.

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "MY_SID=$(ps -p $$ -o sid= 2>/dev/null | tr -d ' '); pgrep -u \"$(id -un)\" rg 2>/dev/null | while read p; do [ \"$(ps -p $p -o sid= 2>/dev/null | tr -d ' ')\" = \"$MY_SID\" ] && kill $p 2>/dev/null; done; true"
          }
        ]
      }
    ]
  }
}
```

The hook matches `rg` processes by **session ID (SID)**. SID is inherited from the parent at fork and does not change when a process becomes orphaned — so even after `codex-companion.mjs` exits and `rg` is reparented to init, it retains the Claude Code session's SID.

> **Best-effort:** this is not a perfect filter. `rg` processes started from the same terminal session that launched Claude Code share the same SID and would also be killed. In practice this trade-off is acceptable — intentional long-running `rg` searches in the same terminal as an active Claude Code session are rare.
