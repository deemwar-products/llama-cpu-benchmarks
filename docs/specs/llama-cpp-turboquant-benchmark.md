# Spec — llama.cpp Small-Model Tool-Calling Benchmark (Qwen × Gemma × Phi, Standard vs TurboQuant)

**Repo:** `deemwar-products/llama-local-benchmarks`
**Status:** Draft v1 · awaiting Muthu's approval
**Date:** 2026-05-20
**Driver:** Muthukumaran Navaneethakrishnan
**Target host:** `ssh-prod-app-deemwar` (deemwar prod-app-1, Hetzner, WireGuard `10.8.0.2`)

---

## 1. Goal

Benchmark the three best open-weight small (~4B) edge models from Qwen, Google, and Microsoft on a single production-class CPU box, head-to-head on **tool-calling accuracy**, **throughput (tokens/sec)**, and **memory footprint** — with and without **TurboQuant** (Google DeepMind, ICLR 2026) KV-cache compression. Produce a decision-grade table that says: which model + quant config we ship for edge / local-LLM workloads on commodity Hetzner hardware.

## 2. Non-goals

- No GPU benchmarking. Target host has no NVIDIA GPU (Intel UHD P630 iGPU only).
- No multimodal / vision testing. Text + tool-calling only.
- No fine-tuning. Stock instruct checkpoints only.
- No model >9B. Edge-size focus.
- Not a llama.cpp upstream contribution. Internal benchmark.

## 3. Target Hardware (probed 2026-05-20)

| Resource | Value |
|---|---|
| CPU | Intel Xeon E-2176G — 6c/12t @ 3.7 GHz, AVX2 yes, **AVX-512 no** |
| RAM | 62 GB total, ~60 GB available (38 GB reclaimable from buff/cache) |
| Disk | 847 GB on `/dev/md2`, 766 GB free |
| GPU | Intel UHD P630 iGPU (no CUDA, Vulkan possible but out-of-scope) |
| OS | Ubuntu 22.04.5 LTS, kernel 5.15.0-164 |
| Live tenants | `reqsume-*`, `video-ai-*`, `video-worker`, `video-http`, `promtail`, `kamal-proxy` |

**Implication:** CPU-only inference. Speed bound by AVX2 throughput, not memory. Live prod workloads share the box — benchmark must be cgroup-isolated.

## 4. Model Matrix

Three best-in-class ~4B instruct models with native tool-calling, May 2026:

| Vendor | Model | Params | Context | Tool-calling | License | GGUF source |
|---|---|---|---|---|---|---|
| Alibaba | `Qwen3.5-4B-Instruct` | 4B | 128K | Native (Qwen tool format) | Apache 2.0 | Bartowski / Unsloth |
| Google | `Gemma-4-4B` | 4B | 128K | Native (6 dedicated tool tokens) | Apache 2.0 | google/ggml-org |
| Microsoft | `Phi-4-mini-instruct` | 3.8B | 128K | Native (JSON schema) | MIT | Bartowski / microsoft |

**Why these three:**
- **Qwen3.5-4B**: Qwen series has led BFCL in its weight class for most of 2025-26.
- **Gemma-4-4B**: Released 2026-04-02, purpose-built for edge/mobile with dedicated tool-call special tokens (`<|tool>`, `<|tool_call>`, `<|tool_result>`).
- **Phi-4-mini**: Microsoft's flagship small tool-caller — built-in function calling, JSON schema, 200K vocab, 128K context.

## 5. Quantization Matrix

| Cell ID | Weight quant | KV cache | Note |
|---|---|---|---|
| `std` | Q4_K_M imatrix (Bartowski) | FP16 (default) | Baseline; what most users run today |
| `tq` | Q4_K_M imatrix (Bartowski) | TurboQuant `turbo3` (3-bit) | TurboQuant arm |

**Weight quant kept constant** at Q4_K_M imatrix across all six runs — the variable under test is the KV-cache compression, not weight precision. This isolates TurboQuant's effect.

**Why Q4_K_M imatrix**: best quality-per-byte at the 4-bit weight level on CPU; widely published; reproducible via Bartowski's pipeline.

## 6. Full Run Matrix (6 cells)

```
                Qwen3.5-4B   Gemma-4-4B   Phi-4-mini
    std/Q4_K_M       1            2            3
    tq/Q4_K_M        4            5            6
```

## 7. TurboQuant fork choice

Upstream llama.cpp does not yet have TurboQuant merged (active discussion in `ggml-org/llama.cpp#20969`). Candidate forks:

| Fork | Notes | Pick rank |
|---|---|---|
| `atomicmilkshake/llama-cpp-turboquant` | turbo2/3/4 + TriAttention; primary fork by activity | **1 (default)** |
| `TheTom/llama-cpp-turboquant` | Has `tools/quantize/README.md`; secondary if #1 fails | 2 |
| `MartinCrespoC/QuantumLeap` | Markets CPU + Ollama-compatible API | 3 |
| `PippBauda/llama.cpp-turboquant-mtp` | TurboQuant+ + MTP integration | 4 |

**Open question:** none of these forks explicitly advertise CPU-only AVX2 x86 builds. Most reference CUDA (Turing+/Ampere) or Apple Metal. Phase 0 (§9) gates Phase 1 on whether any fork actually builds and runs on this CPU.

## 8. llama.cpp Build & Run Configuration

### 8.1 Baseline llama.cpp (for `std` cells)

```bash
git clone https://github.com/ggml-org/llama.cpp.git llama.cpp-std
cd llama.cpp-std
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_AVX2=ON -DGGML_LLAMAFILE=ON
cmake --build build --config Release -j$(nproc)
```

### 8.2 TurboQuant llama.cpp (for `tq` cells)

```bash
git clone https://github.com/atomicmilkshake/llama-cpp-turboquant.git llama.cpp-tq
cd llama.cpp-tq
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_AVX2=ON -DGGML_TURBOQUANT=ON
cmake --build build --config Release -j$(nproc)
```

Falls back to forks #2/#3/#4 in order if #1 fails to build or run on AVX2-only CPU.

### 8.3 Production-safety constraints (mandatory)

All benchmark runs are wrapped in Docker with strict resource caps to avoid disturbing the live `reqsume-*` and `video-ai-*` tenants:

```bash
docker run --rm \
  --cpus=4 --cpuset-cpus=8-11 \
  --memory=12g --memory-swap=12g \
  --name llamabench-${cell_id} \
  -v $(pwd)/models:/models:ro \
  -v $(pwd)/results:/results \
  llamabench:${variant} \
  ${cmd}
```

- **Pinned to cores 8-11** (4 cores). Cores 0-7 left to prod tenants.
- **12 GB memory cap** (~6 GB model + 6 GB headroom).
- **Off-peak window**: runs scheduled 02:00-06:00 IST or weekend mornings (low video-ai/reqsume traffic). Per-run runtime ≤30 min.
- **Kill switch**: if host load_avg(1m) > 8.0 or prod healthchecks fail, abort the run.

### 8.4 Run flags (per cell)

```bash
# Standard cell (std)
llama-server --model /models/${model}-Q4_K_M.gguf \
  --threads 4 --ctx-size 8192 \
  --jinja --port 11434

# TurboQuant cell (tq)
llama-server --model /models/${model}-Q4_K_M.gguf \
  --threads 4 --ctx-size 8192 \
  --jinja --port 11434 \
  --cache-type-k turbo3 --cache-type-v turbo3
```

(Exact TurboQuant flag spelling confirmed against chosen fork's docs in Phase 0.)

## 9. Two-Phase Execution

### Phase 0 — Feasibility (1-2 hours, blocking gate)

1. Clone & build candidate TurboQuant fork (#1) on prod-app-1 inside Docker.
2. Run `llama-cli` smoke test with **Gemma-4-2B-Q4_K_M** + `--cache-type-k turbo3 --cache-type-v turbo3` and a one-tool prompt.
3. Gate criteria:
   - (a) Build succeeds on AVX2-only x86, no GPU/Metal required.
   - (b) Smoke test completes one tool-call turn end-to-end.
   - (c) Memory + CPU stay inside the cgroup caps.
4. If gate fails → fall back through fork ranks 2 → 3 → 4. If all four fail, Phase 1 reduces to **3 cells (std only)** and the TurboQuant arm is documented as "not feasible on commodity CPU as of 2026-05-20."

### Phase 1 — Full sweep (≈ 1 day of off-peak runs)

For each of the 6 cells:
1. `llama-bench` → raw prompt eval tok/s + gen eval tok/s + peak RSS.
2. Tool-calling harness (§10) → BFCL-subset accuracy %.
3. Latency probe → 100 × {256-in / 128-out} turns, record p50 / p95 wall-clock.

Output → `results/${cell_id}.json` + aggregated `results/summary.md` table.

## 10. Tool-Calling Test Harness

### 10.1 Test set

Subset of **Berkeley Function Calling Leaderboard (BFCL) v3**, three categories:

| Category | N cases | What it tests |
|---|---|---|
| `simple` | 50 | Single function, single arg set |
| `parallel` | 25 | Multiple functions in one turn |
| `multiple_function` | 25 | Pick the right function from N candidates |

**Total: 100 cases per model × quant cell = 600 evaluations.**

### 10.2 Driver

Python harness (`harness/run_bfcl.py`) — talks to `llama-server` over its OpenAI-compatible `/v1/chat/completions` endpoint with `tools=[...]`. Server is invoked with `--jinja` so the model's native chat template handles tool-call formatting.

### 10.3 Scoring

| Metric | Definition |
|---|---|
| `format_pass_rate` | % of cases where output is a valid JSON tool call (parseable) |
| `function_accuracy` | % where the correct function was selected (AST match) |
| `argument_accuracy` | % where all args match expected (AST match) |
| `overall_pass` | strict: format ∧ function ∧ argument all pass |

## 11. Metrics & Output Schema

Per cell, written to `results/${cell_id}.json`:

```json
{
  "cell_id": "qwen3.5-4b_tq",
  "model": "Qwen3.5-4B-Instruct",
  "weight_quant": "Q4_K_M",
  "kv_quant": "turbo3",
  "llamacpp_variant": "atomicmilkshake/llama-cpp-turboquant@<sha>",
  "host": "deemwar-prod-app-1",
  "throughput": {
    "prompt_eval_tps": 0.0,
    "gen_eval_tps": 0.0
  },
  "memory": {
    "peak_rss_mb": 0,
    "kv_cache_rss_mb": 0
  },
  "latency_ms": {
    "p50": 0,
    "p95": 0
  },
  "tool_calling": {
    "format_pass_rate": 0.0,
    "function_accuracy": 0.0,
    "argument_accuracy": 0.0,
    "overall_pass": 0.0,
    "n_cases": 100
  },
  "started_at": "ISO8601",
  "duration_sec": 0
}
```

Aggregated into `results/summary.md` as a Markdown table for human review.

## 12. Success Criteria

**Per-model gate (any one model passes "ship for edge"):**

| Metric | Threshold | Rationale |
|---|---|---|
| `gen_eval_tps` | ≥ **10 tok/s** | usable for interactive tool-use on edge |
| `tool_calling.overall_pass` | ≥ **70%** | matches BFCL "competent" tier for ~4B class |
| `tool_calling.format_pass_rate` | ≥ **95%** | reliable JSON emission is table-stakes |
| `memory.peak_rss_mb` | ≤ **6000** | leaves headroom inside 12 GB cgroup |

> ⚠️ **OPEN: Muthu to confirm or override these thresholds.** Defaults set conservatively against what's reported in BFCL v3 for 4B-class models. Tighten or relax per your edge product requirements.

**TurboQuant arm success (separate gate):**

| Metric | TurboQuant must achieve | vs. `std` baseline |
|---|---|---|
| `kv_cache_rss_mb` | ≥ 3× reduction | confirms compression works |
| `tool_calling.overall_pass` | within 2 pp of `std` | confirms no quality regression |
| `gen_eval_tps` | within ±10% of `std` | confirms no major CPU-path slowdown |

If TurboQuant fails the "no regression" gate on this hardware, **the recommendation is to ship `std` quants** — the experiment still publishable as a negative result.

## 13. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| TurboQuant fork doesn't build on AVX2-only CPU | High | Phase-1 reduced to 3 cells | Phase 0 gate; try all 4 forks |
| Benchmark disturbs prod tenants | Medium | Prod incident | cgroup cap; off-peak; load_avg kill switch |
| Gemma-4 / Qwen3.5 / Phi-4 chat-template parser bug in llama.cpp | Medium | Tool-call format failures inflated | Pin to llama.cpp ≥ 2026-05-01 build with Qwen3/Gemma4 fixes; smoke-test each chat template before BFCL run |
| Bartowski-Gemma-4 imatrix GGUF not yet published | Low | Have to generate our own imatrix | Fallback to vanilla Q4_K_M; flag in results |
| BFCL v3 subset doesn't generalize to our actual edge workloads | Low | Wrong winner chosen | Document delta; if Muthu has internal tool-call traces, add as Cat-4 |

## 14. Deliverables

1. `results/summary.md` — markdown comparison table, all six cells.
2. `results/${cell_id}.json` × 6 — raw per-cell data.
3. `results/decision.md` — one-page recommendation: which model + quant config to ship.
4. `harness/run_bfcl.py` — reusable test harness (so we can re-benchmark when Phi-5 / Qwen3.6 / Gemma-5 drop).
5. Updated `CLAUDE.md` reflecting the chosen winner (after spec approval).

## 15. Open Questions (Muthu must answer before Phase 0 starts)

1. **Success-bar numbers** — accept defaults in §12 (10 tok/s, 70% overall_pass, 95% format, 6 GB RSS), or override?
2. **Fork preference** — start Phase 0 with `atomicmilkshake/llama-cpp-turboquant` (default), or another?
3. **Off-peak window** — confirm 02:00-06:00 IST is safe for prod tenants on prod-app-1 (or pick a different window)?
4. **BFCL subset adequacy** — do you have internal tool-calling traces from `reqsume` / `video-ai` we should add as a Cat-4 evaluation set?
5. **Phi-4-mini vs Phi-4 multimodal** — confirm we test the text-only `Phi-4-mini-instruct`, not the multimodal variant (multimodal adds vision tokens which skew tool-call benchmarks).

## 16. References

- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core) · [Function calling with Gemma 4](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)
- [Qwen3.5 — Unsloth docs](https://unsloth.ai/docs/models/qwen3.5)
- [Phi-4-mini · Microsoft HF](https://huggingface.co/microsoft/Phi-4-mini-instruct) · [Phi-4 function calling guide](https://github.com/microsoft/PhiCookBook/blob/main/md/02.Application/07.FunctionCalling/Phi4/FunctionCallingBasic/README.md)
- [TurboQuant — Google Research](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/) · [ICLR 2026 paper](https://openreview.net/pdf/6593f484501e295cdbe7efcbc46d7f20fc7e741f.pdf)
- [llama.cpp TurboQuant discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)
- [atomicmilkshake/llama-cpp-turboquant](https://github.com/atomicmilkshake/llama-cpp-turboquant)
- [BFCL v4 leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html)
