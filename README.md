# Local LLM Workflow — vLLM + Claude Code + Codex

The goal of this repository is to build a workflow that connects the following tools.

| Tool                  | Role                                     |
| --------------------- | ---------------------------------------- |
| **Claude Code** | AI coding assistant (CLI)                |
| **Codex**       | AI coding assistant (Claude Code plugin) |
| **vLLM + Qwen** | Local LLM server (OpenAI-compatible API) |

## Workflow Overview

```
Cloud path (quota monitoring):
Claude Code ─ ANTHROPIC_BASE_URL=:8000 ─→ proxy.py (:8000) ─→ api.anthropic.com
                                              │
                                              └─ writes 5h-quota → ~/.claude/usage-status.json
                                                 → UserPromptSubmit hook (usage_route_hook.py)
                                                   forces Qwen delegation above threshold

Claude Code ──── review-gate integration ──── Codex
     │                                           │
     │                                        MCP (stdio)
     │                                           │
     │                                        mcp_qwen.py (same script used by Claude Code)
     │                                           │
     └─ MCP (stdio) ──── mcp_qwen.py ──── vLLM (:8001) ──── Qwen model
```

**Reducing token / message consumption:**

Both Claude Code and Codex can offload work to the local Qwen via MCP. The offload
decision is **not** tied to which cloud model is active — it is based on the **shape of
the subtask** (see [Delegation Principle](#delegation-principle)). When a subtask is
formulaic, localized, and easy to verify, the cloud client passes it to Qwen and keeps
file I/O, orchestration, and verification for itself. This reduces the expensive
reasoning the cloud model has to perform, which is what actually lowers API token
consumption. Model choice (and its effort level) is a separate axis: it controls how
deeply the cloud model reasons about the work it does keep, not whether offload happens.

A second, complementary axis is **quota-remaining based** routing: a monitoring proxy
captures the Anthropic 5-hour usage quota and a `UserPromptSubmit` hook biases routing
toward Qwen once the quota crosses a threshold — see
[Quota-based delegation](#quota-based-delegation-5h-quota-monitoring).

---

## Directory Contents

| File                                      | Description                                                                                           |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `sourceme`                              | bash/sh env vars (`export`)                                                                         |
| `sourceme.csh`                          | tcsh env vars (`setenv`)                                                                            |
| `proxy.py`                              | Transparent monitoring proxy (port 8000): captures Anthropic 5h-quota headers →`usage-status.json` |
| `~/.claude/usage-status.json`           | Latest Anthropic 5h-quota snapshot (written by `proxy.py`;)                                         |
| `usage_route_hook.py`                   | `UserPromptSubmit` hook: forces Qwen delegation when 5h quota ≥ threshold                          |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | vLLM startup — Qwen3-Coder-30B-A3B (128K ctx, cpu-offload 2 GB)                                      |
| `mcp_qwen.py`                           | MCP server — exposes Qwen as `ask_qwen` / `ask_qwen_code` tools                                  |
| `usage.log`                             | JSONL token-usage log (auto-created by `mcp_qwen.py`; git-ignored)                                  |
| `usage_report.py`                       | Aggregates `usage.log` token records (daily / per-tool summary)                                     |
| `README.md`                             | This file                                                                                             |

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

The server listens on `http://0.0.0.0:8001`.

### 3b. Start the monitoring proxy (optional, for quota-based delegation)

```bash
python3 vllm/proxy.py   # listens on :8000, forwards to api.anthropic.com
```

Then `source vllm/sourceme` (sets `ANTHROPIC_BASE_URL=http://localhost:8000`) and start
Claude Code so its API traffic flows through the proxy. See
[Quota-based delegation](#quota-based-delegation-5h-quota-monitoring).

## 4. Claude Code MCP Integration

`mcp_qwen.py` is an MCP server that exposes the local Qwen model as two tools callable directly from Claude Code sessions. Routing rules delegate subtasks that are good offload candidates (formulaic, localized, easy to verify) to Qwen, while Claude Code keeps file I/O, tool calls, orchestration, and verification. The offload decision is based on task shape, not on which model is active (see [Delegation Principle](#delegation-principle)).

```
Claude Code → MCP (stdio) → mcp_qwen.py → vLLM :8001 → Qwen3-Coder-30B-A3B
```

### Setup (one-time)

**1. Register the MCP server:**

```bash
claude mcp add -s user qwen-local python3 $REP/vllm/mcp_qwen.py
```

The `-s user` flag installs it globally (all projects). Omit it for project-local registration.

**2. Verify:**

Inside Claude Code, run `/mcp` — `qwen-local` should appear with status `connected`.

## 5. Codex MCP Integration

The same `mcp_qwen.py` server can be registered with the Codex CLI. Codex can then call
`ask_qwen` / `ask_qwen_code` during its runs to offload work to the local GPU,
reducing OpenAI API token consumption.

```
Codex CLI → MCP (stdio) → mcp_qwen.py → vLLM :8001 → Qwen3-Coder-30B-A3B
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

---

## Quota-based delegation (5h-quota monitoring)

Delegation has **two axes**:

1. **Task-shape based** (always on): offload a subtask to Qwen when it is formulaic,
   localized, and easy to verify — see [Delegation Principle](#delegation-principle).
2. **Quota-remaining based** (new): when the Anthropic 5-hour usage quota is running low,
   *bias the routing aggressively toward Qwen* even for subtasks that would normally stay
   in the cloud. This is what `proxy.py` + `usage_route_hook.py` implement.

```
Claude Code ─ ANTHROPIC_BASE_URL=:8000 ─→ proxy.py (:8000) ─→ api.anthropic.com
                                              │ reads anthropic-ratelimit-unified-5h-* headers
                                              ▼
                                    ~/.claude/usage-status.json
                                              ▲ read on every prompt
                  usage_route_hook.py (UserPromptSubmit hook) ── inject "prefer Qwen" when 5h ≥ θ
```

### proxy.py — transparent monitoring proxy (port 8000)

`proxy.py` is a FastAPI proxy that forwards requests/responses to Anthropic **verbatim**
(no body modification). Its only job is to passively read the unified rate-limit headers
from each upstream response and write the latest snapshot to `~/.claude/usage-status.json`:

| Header                                         | Stored key                             |
| ---------------------------------------------- | -------------------------------------- |
| `anthropic-ratelimit-unified-5h-utilization` | `utilization_5h` (0.0–1.0)          |
| `anthropic-ratelimit-unified-5h-remaining`   | `remaining_5h`                       |
| `anthropic-ratelimit-unified-5h-reset`       | `reset_5h` (Unix epoch)              |
| `anthropic-ratelimit-unified-7d-utilization` | `utilization_7d` (weekly, reference) |

Start it and route Claude Code through it:

```bash
python3 vllm/proxy.py
# Listening on http://0.0.0.0:8000  (forwards to https://api.anthropic.com by default)

export ANTHROPIC_BASE_URL=http://localhost:8000   # done automatically by sourceme
```

The status write is atomic and best-effort; it never alters or breaks the proxied
request. Override the backend with `PROXY_BACKEND` and the status path with
`USAGE_STATUS_PATH`.

Registered in `~/.claude/settings.json` under `UserPromptSubmit`. On every prompt it reads
`usage-status.json`; if `utilization_5h ≥ threshold` it injects an `additionalContext`
instruction telling Claude to prefer the local Qwen model (`ask_qwen` / `ask_qwen_code`)
as the first choice for code generation, debugging, refactoring, and self-contained
prose subtasks. Below the threshold it injects nothing (normal operation). It is
read-only and fails closed to a clean no-op (missing / stale / corrupt status → no
injection), so it can never block prompt submission.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "matcher": "", "hooks": [
        { "type": "command", "command": "python3 $REP/vllm/usage_route_hook.py" }
      ] }
    ]
  }
}
```

| Env var                  | Default                         | Purpose                                                  |
| ------------------------ | ------------------------------- | -------------------------------------------------------- |
| `QWEN_ROUTE_THRESHOLD` | `0.85`                        | 5h utilization (0.0–1.0) at/above which to force Qwen   |
| `QWEN_ROUTE_TOOLS`     | `ask_qwen, ask_qwen_code`     | MCP tool names recommended in the injected text          |
| `QWEN_ROUTE_MAX_AGE`   | `21600` (6h; `0` disables)  | Ignore the status file when older than this many seconds |
| `USAGE_STATUS_PATH`    | `~/.claude/usage-status.json` | Status file path (shared with `proxy.py`)              |

---

## Available Models

| Script                                    | Model                                          | Context | VRAM  | Notes                                                   |
| ----------------------------------------- | ---------------------------------------------- | ------- | ----- | ------------------------------------------------------- |
| `start_vllm_qwen3_coder_30b_a3b_awq.sh` | `QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ` | 128K    | 16 GB | **Default.** MoE 30B/3B-active, multi-file coding |

## Requirements

- Python 3.9+, CUDA 12.x
- NVIDIA GPU with ≥16 GB VRAM (RTX 4080 / 3090 / 4090 / A6000)
- vLLM 0.21.0

## Environment Variables

Set in the startup scripts:

- `CUDA_HOME=/usr`
- `VLLM_USE_DEEP_GEMM=0`
- `VLLM_USE_FLASHINFER_MOE_FP16=0`
- `VLLM_USE_FLASHINFER_SAMPLER=0`
- `OMP_NUM_THREADS=4`

## vLLM Server Options

Key flags used in `start_vllm_qwen3_coder_30b_a3b_awq.sh`:

| Flag                             | Value                                   | Purpose                                                                                                                   |
| -------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `--served-model-name`          | `local-model-qwen3-coder-30b-a3b-awq` | Model name exposed via API                                                                                                |
| `--port`                       | `8001`                                | Server listen port (OpenAI-compatible API)                                                                                |
| `--enable-auto-tool-choice`    | —                                      | Enable function/tool calling                                                                                              |
| `--tool-call-parser`           | `qwen3_xml`                           | Qwen3 XML tool parser; avoids long-context `qwen3_coder` infinite `!` loop and `hermes` raw `<tool_call>` leakage |
| `--reasoning-parser`           | `qwen3`                               | Separates `<think>` reasoning blocks from normal output and tool arguments                                              |
| `--trust-remote-code`          | —                                      | Allow custom model code from HuggingFace                                                                                  |
| `--language-model-only`        | —                                      | Skip multimodal pipeline overhead                                                                                         |
| `--override-generation-config` | `{"max_new_tokens":8192}`             | Server-side generation token limit                                                                                        |
| `--max-model-len`              | `131072`                              | Context window (128K)                                                                                                     |
| `--cpu-offload-gb`             | `2`                                   | Offload 2 GB of weights to CPU RAM for KV cache headroom                                                                  |
| `--max-num-seqs`               | `2`                                   | Max concurrent sequences                                                                                                  |
| `--kv-cache-dtype`             | `fp8`                                 | FP8 KV cache to reduce VRAM usage                                                                                         |
| `--gpu-memory-utilization`     | `0.95`                                | VRAM usage target                                                                                                         |
| `--enable-prefix-caching`      | —                                      | Cache common prefix (effective for multi-file work)                                                                       |
| `--enable-chunked-prefill`     | —                                      | Split long prefills into chunks for stable batching                                                                       |
| `--max-num-batched-tokens`     | `4096`                                | Fixed at 4096 to avoid Mamba alignment error with chunked-prefill                                                         |

---

## Qwen mcp

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

### Token usage logging

Every Qwen call made through `mcp_qwen.py` appends one JSON line to `vllm/usage.log`
(override the path with the `QWEN_USAGE_LOG` env var). Each record holds the timestamp,
tool name, input character count, and `prompt` / `completion` / `total` token counts from
the vLLM response, plus call latency. Logging is best-effort and never fails the call.

Summarize consumption with the aggregation script:

```bash
python3 vllm/usage_report.py                 # daily × tool table (default ./usage.log)
python3 vllm/usage_report.py --by day        # group by day only
python3 vllm/usage_report.py --by tool       # group by tool only
python3 vllm/usage_report.py --json          # machine-readable
python3 vllm/usage_report.py path/to/usage.log
```

This is the measurement baseline for evaluating delegation/compression changes
(before vs. after token comparison).

`usage_report.py` measures the **local Qwen** side (how much work was offloaded). For
the **cloud** side, `~/.claude/usage-status.json` (written by `proxy.py`) gives the live
Anthropic 5h-quota utilization — the trigger that drives quota-based delegation. Together
they show both halves of the picture: how much cloud quota remains, and how much work was
pushed to the local GPU in response.

### Routing rules

The offload decision is model-agnostic: it depends on the shape of the subtask, not on
which GPT model is active (see [Delegation Principle](#delegation-principle)). Regardless
of model, Codex reads/searches files locally, passes the relevant text to Qwen, applies
the returned edits, and runs verification. Qwen does not access files by path; it receives
only text provided by Codex.

| Task type                                                                    | Tool to use                         |
| ---------------------------------------------------------------------------- | ----------------------------------- |
| Boilerplate/stub generation, language translation                            | `ask_qwen_code(language, prompt)` |
| Comment/docstring translation, short explanations, summaries                 | `ask_qwen(prompt)`                |
| Multi-step reasoning, root-cause analysis, architecture, cross-file analysis | Codex handles directly              |

Model choice (and effort level) is a separate axis: a stronger model with higher effort
reasons more deeply about the work Codex keeps, but the boundary of what is worth
offloading stays the same.

---

## Delegation Mode

Both Claude Code and Codex act as orchestration layers that can route individual
subtasks to the local Qwen for the core reasoning or generation step. This applies
across all cloud models — the same policy governs Claude Code and Codex regardless of
which model or effort level is active.

### Delegation Principle

This section is the **single source of truth** for both the Qwen offload criteria and
the MCP call best practices. The client configuration files
(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`) should reference this section rather than
restate the rules, so all clients stay in sync.

The key design point is that delegation should **not** be handled as a static model-switch policy.
Instead, the decision should be based on the **task characteristics** and on whether moving work to
Qwen actually reduces the expensive reasoning burden on the primary agent.

In other words, the question is not "which model is active?" but "is this subtask a good candidate
for offload?".

Model choice and effort level are an **orthogonal** axis. They control how deeply the
cloud model reasons about the work it keeps — not whether a subtask is offloaded. A
weaker/cheaper model does not mean "offload everything," and a stronger model does not
mean "offload nothing"; the offload boundary is the same in both cases and is determined
only by task shape.

#### Offload criteria (when to route to Qwen)

**Good offload candidates**

- Highly repetitive or formulaic work
- Localized inputs with limited context (one file, one function, a short passage)
- Outputs that are easy to verify quickly
- Tasks where small formatting or wording differences are acceptable
- Boilerplate generation, stubs, short summaries, translation, and simple transformations

**Poor offload candidates**

- Cross-file reasoning or system-wide consistency checks
- Root-cause analysis and architecture decisions
- Tasks where mistakes can silently introduce bugs
- Cases where preparing the handoff context is almost as expensive as doing the work directly
- Anything requiring the delegate model to read files by path, call tools, or maintain state across calls

The decision procedure is the same for every client and every model:

1. classify the task by shape first
2. decide whether delegation reduces the primary agent's reasoning load
3. then choose whether to route the subtask to local Qwen

That keeps the system portable across Claude Code, Codex, and future clients, because the offload
decision is expressed in terms of work shape rather than in terms of a specific model family.

#### Call best practices (how to call the MCP tools)

These apply identically to every client (Claude Code, Codex, future clients).

**Tool selection**

| Tool                                | Use for                                                                      |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| `ask_qwen(prompt)`                | Prose: Q&A, explanations, summaries, translation, comment/docstring rewrites |
| `ask_qwen_code(language, prompt)` | Code: generation, refactoring, unit-test skeletons, stubs, code translation  |

**Routing rules**

1. **Pure Q&A / explanation / summary / translation** (good candidate)
   → call `ask_qwen(prompt=<full request>)`; return the response verbatim.
2. **Code generation / refactoring / unit tests** (formulaic, self-contained)
   → determine the language from context; call `ask_qwen_code(language=<lang>, prompt=<request + required context>)`; return verbatim.
3. **Tasks requiring file I/O** → the client reads/searches files itself, passes the
   actual relevant content (never a path) to Qwen, then applies the result with its own
   editing tools and verifies.
4. **Multi-step tasks** → break into the smallest steps; offload each good candidate;
   keep root-cause analysis and cross-file reasoning in the cloud model; the client owns
   orchestration, context packaging, and validation.

**Handoff constraints** — Qwen has no filesystem access, no tool access, and no memory
across calls. Always pass the actual relevant text in the prompt; never ask Qwen to read a
path, call a tool, or rely on a previous call.

**What NOT to do when offloading**

- Do not also generate the answer yourself for an offloaded subtask.
- Do not restate Qwen's output in your own words when its output suffices.
- Do not call Qwen and then layer your own commentary on top.
- Do not force-offload a poor candidate (cross-file, root-cause, high-risk) just to save tokens.

**Token budget** — see [Token Limits](#token-limits). In short: ≤ 2,048 output tokens per
call, ~129K (~126K) effective input budget. No soft cap on prompt size for speed reasons —
pack as much relevant context as the task needs. Split into multiple calls only when the
input exceeds ~129K (one file per call, combine yourself) or the expected answer exceeds the
2,048-token output limit (split the output across calls).

### Architecture

```
User → Claude Code → MCP (stdio) → mcp_qwen.py → vLLM :8001 → Qwen3-Coder-30B
User → Codex       → MCP (stdio) → mcp_qwen.py → vLLM :8001 → Qwen3-Coder-30B
```

The cloud model handles orchestration: reading files, running searches, applying edits, and verifying results. Qwen handles the text-in/text-out reasoning or generation step.

### Configuration locations

The offload criteria and call best practices live only in the [Delegation Principle](#delegation-principle)
above. The per-client files below do **not** restate them — they carry a pointer to that
section plus any client-specific note (tool names, who owns file I/O):

| Client      | Configuration file      |
| ----------- | ----------------------- |
| Claude Code | `~/.claude/CLAUDE.md` |
| Codex       | `~/.codex/AGENTS.md`  |

### Codex stop-review-gate delegation

The Codex stop-time review gate is launched by the Claude Code plugin hook:

| Plugin file                                                                               | Purpose                                                                         |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `~/.claude/plugins/cache/openai-codex/codex/1.0.3/scripts/stop-review-gate-hook.mjs`    | Runtime hook that calls `codex-companion.mjs task --json`                     |
| `~/.claude/plugins/cache/openai-codex/codex/1.0.3/prompts/stop-review-gate.md`          | Runtime prompt used for the stop-gate Codex task                                |
| `~/.claude/plugins/marketplaces/openai-codex/plugins/codex/prompts/stop-review-gate.md` | Source prompt to keep in sync so reinstall/cache refresh does not lose the rule |

The hook itself does not choose Qwen. It only builds the stop-gate prompt and starts
a Codex task. To make delegation reliable, add the Qwen rule to
`stop-review-gate.md` in both the cache and source plugin copies:

```text
When reviewing actual code changes and local Qwen MCP tools are available, delegate
the review reasoning to Qwen after gathering the relevant repository context locally.
Pass Qwen the concrete diff and relevant file snippets; do not ask Qwen to read paths
or use tools. Keep all file I/O, command execution, and final ALLOW/BLOCK decision in
Codex. If the previous turn did not make direct edits, return ALLOW immediately without
calling Qwen.
```

This preserves the fast path: if the previous Claude turn was only a status update,
summary, setup/login check, command output, or review result, Codex should return
`ALLOW` immediately and not call Qwen. If the previous turn did make direct edits,
Codex should gather the concrete diff and relevant snippets locally, ask Qwen for
the review reasoning, then make the final `ALLOW` / `BLOCK` decision itself.

This prompt-level rule still requires the Codex session to have `qwen-local` MCP
available via `~/.codex/config.toml`. If the MCP server is not exposed to the
stop-gate Codex session, the prompt cannot make Codex call Qwen.

### Token Limits

| Limit                    | Value                                | Source                                                 |
| ------------------------ | ------------------------------------ | ------------------------------------------------------ |
| Output per call (client) | **≤ 2,048 tokens**            | `mcp_qwen.py` `max_tokens=2048` (takes precedence) |
| Output ceiling (server)  | 8,192 tokens                         | `--override-generation-config max_new_tokens:8192`   |
| Context window           | **128K tokens**                | `--max-model-len 131072`                             |
| Effective input budget   | **≤ ~129,024 tokens (~126K)** | 131072 − 2048 (total context minus reserved output)   |

`131072` is the **combined** input+output budget, not input alone. The `2,048` / `8,192` figures are **output** limits, not input limits.

**Policy:** there is no soft cap on prompt size for speed reasons — use the full input budget (up to ~129K tokens) when the task needs it. Split into multiple calls only when the input genuinely exceeds ~129K (pass one file per call and combine results yourself), or when the expected answer would exceed the 2,048-token output limit (split the *output* across calls).

### Benefits

- Cloud API charges reduced substantially because only file I/O, MCP orchestration, and verification run on the cloud model
- Code generation, explanation, and refactoring run entirely on local GPU
- The same local model behavior is shared across Claude Code and Codex

### Caveats

- For subtasks that qualify as good offload candidates, the cloud model should not perform the core generation or reasoning itself; breaking the delegation rules wastes API tokens
- Return `ask_qwen` / `ask_qwen_code` output directly unless a short operational note is needed
- Requires both the MCP server (`mcp_qwen.py`) and the vLLM server to be running

---

## Tips: Codex stop-review-gate rg Process Lingering Issue

Codex's `stop-review-gate` hook spawns `codex-companion.mjs`, which scans the repository with `rg .`. After the task completes or times out, child `rg` processes can remain orphaned — keeping load average elevated.

### Root Cause & Primary Mitigation: Operate at the Second Level or Deeper

The harness launch root (the top-level workspace directory) is not a single git
repository — it holds many independently-cloned repositories. When `git` is run
from that root it fails, so the review gate falls back to extracting the diff with
a repository-wide `rg .`, which is exactly what spawns the lingering `rg` processes.

**The first-line fix is to always operate at the second level or deeper**, i.e.
`cd` into the concrete target project (`<workspace-root>/<project>/<subdir>`, a
real git working tree) before any `git` / diff operation, instead of the launch
root. Inside a single repository `git` stays valid and the gate extracts a real
diff rather than scanning the whole tree. This general rule is documented in both
`~/.claude/CLAUDE.md` (Claude Code) and `~/.codex/AGENTS.md` (Codex). The `Stop`
hook below remains as a belt-and-suspenders cleanup for any `rg` that still leaks.

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

---

## Tips: Review Gate Token Reduction

When Codex Review Gate is enabled, each stop-time review can consume a noticeable
amount of Codex usage. In the current `openai-codex` plugin (`1.0.3`),
`/codex:setup` only supports enabling or disabling the review gate:

```bash
/codex:setup --enable-review-gate
/codex:setup --disable-review-gate
```

To reduce review depth, set the Codex reasoning effort in `~/.codex/config.toml`
or a trusted project `.codex/config.toml`:

```toml
model_reasoning_effort = "minimal"
```
