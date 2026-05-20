# Engine bake-off — can anything beat stock llama.cpp on CPU?

**Or: TurboQuant lost. Speculative decoding lost. What else have I got?**

*Published 2026-05-20 (live) · companion to [the main article](/article) · cells on [/results](/results)*

---

## The setup

Same shared CPU box (Xeon E-2176G, AVX2 yes / AVX-512 no, 4-core cgroup, 12 GB memory cap). Same 35-case BFCL subset. Same Q4_K_M weights. Same `--reasoning off --reasoning-budget 0`. Only the inference engine changes per cell.

Baseline (already published):

| Model | Engine | gen tok/s | p50 ms | Overall pass |
|---|---|---:|---:|---:|
| Qwen 3.5 4B | stock llama.cpp | **9.79** | **13,739** | **91.4 %** |
| gemma-4-E4B-it | stock llama.cpp | 8.59 | 6,240 | 94.3 % |
| Phi-4-mini | stock llama.cpp | 10.62 | 7,517 | 0.0 %† |

†broken jinja tool-calling — see Phi anomaly in the [main article](/article#the-phi-anomaly). Workaround variant: 74.3 %.

## Engines tested

Five candidates from the [bake-off spec](/specs/cpu-fast-inference-bake-off). Two have results, three are next:

### Engine B — llama.cpp + speculative decoding

Same Qwen3.5-4B-Q4_K_M target, plus a Qwen3.5-0.8B-Q4_K_M draft model loaded via `--spec-draft-model` (modern flag is `-md`). `--spec-draft-n-max 8 --spec-draft-n-min 2`.

**Result on Qwen:**

| Metric | std | specdec | Δ |
|---|---:|---:|---|
| p50 latency | 13.7 s | **20.4 s** | **1.48× slower** |
| Overall pass | 91.4 % | 88.6 % | −2.9 pp |
| Simple / multi-func / parallel | 95 / 90 / 80 % | 90 / 90 / 80 % | small regression on simple |

**Counterintuitive verdict — slower, not faster.** Published 2.5-3× CPU speedups for speculative decoding are on **7B+ targets** where draft-model inference is genuinely tiny relative to target per-token cost. At the **4B-class scale on a 4-core cgroup**, draft+verify orchestration eats more than the drafts save. Anti-pattern for small models on CPU.

### Engine D — `ik_llama.cpp` (ikawrakow fork)

Published claim: ~2× faster than mainline on AVX2 Xeon. Built from current master (`40254a5`) inside `ubuntu:22.04` Docker: `cmake -DGGML_NATIVE=ON -DGGML_AVX2=ON -DGGML_CUDA=OFF -DGGML_METAL=OFF -DLLAMA_CURL=ON`. The build emits "Using optimized iqk matrix multiplications" + "Enabling IQK Flash Attention kernels" — both are AVX2-specific paths.

Runtime needs `libcurl4` and `libmtmd.so` from the build's own `examples/mtmd/` dir — runtime container needs `LD_LIBRARY_PATH=…/src:…/ggml/src:…/examples/mtmd`. Server boots in 2 s.

**Result on Qwen:**

| Metric | stock | ik_llama | Δ |
|---|---:|---:|---|
| prompt tok/s | 35.85 | **58.08** | **1.62× faster** |
| gen tok/s | 9.79 | 8.37 | 0.85× (slightly slower) |
| **p50 latency** | 13,739 ms | **8,977 ms** | **1.53× faster** |
| overall_pass | 91.4 % | 82.9 % | −8.6 pp |
| format_pass | 97.1 % | **100 %** | +2.9 pp |
| simple | 95 % | **100 %** | +5 pp |
| multi-func | 90 % | 90 % | same |
| **parallel** | 80 % | **0 %** | **−80 pp** |

**Mixed result.** The 1.53× end-to-end win is real and comes from **prompt evaluation, not generation** — tool-calling prompts include the tool schemas which ik_llama's IQK matmul kernels chew through 1.62× faster than mainline. Token generation is actually marginally slower.

The catch: **parallel-call generation breaks entirely.** Likely a chat-template handling difference in ik_llama master — worth filing upstream. Until fixed, ik_llama is a clean win **only when you don't need parallel tool calls** (simple + multi-function workloads only).

**Result on Gemma:**

| Metric | stock | ik_llama | Δ |
|---|---:|---:|---|
| prompt tok/s | 31.16 | 38.58 | 1.24× faster |
| gen tok/s | 8.59 | 7.62 | 0.89× (slower) |
| **p50 latency** | 6,240 ms | **5,959 ms** | **1.05× faster** |
| overall_pass | 94.3 % | 85.7 % | −8.6 pp |
| simple | 90 % | **100 %** | +10 pp |
| multi-func | 100 % | 100 % | same |
| **parallel** | 100 % | **0 %** | **−100 pp** |

Smaller end-to-end win (4.5 %) because Gemma's stock baseline is already efficient. The parallel-call breakage repeats — strong evidence it's a chat-template bug in ik_llama master, not model-specific.

**Result on Phi-4-mini: SKIPPED.** `ik_llama.cpp@40254a5` can't load `Phi-4-mini-instruct-Q4_K_M.gguf` — loader errors with `check_tensor_dims: tensor 'output.weight' not found`. Phi-4 uses tied embeddings (input embedding matrix doubles as output projection); ik_llama master doesn't handle that layout yet. The same GGUF loads fine on stock llama.cpp and on PR #21089.

### Engine A — stock llama.cpp (reference baseline)

Already on the [results page](/results). 9.79 / 8.59 / 10.62 gen tok/s for Qwen / Gemma / Phi.

## Engines not yet tested

- **Engine C — OpenVINO backend.** Upstream `-DGGML_OPENVINO=ON` build, or `intel/openvino-llama-cpp` image. The drop-in upgrade for Intel CPUs. Highest-expected-value next test.
- **Engine E — vLLM CPU backend.** Different model format (HF checkpoint, not GGUF) — not apples-to-apples. Included as an outside reference.

## Verdict

After three of the five engines on three models, the picture is decisive:

| Engine | Throughput vs stock | Accuracy vs stock | Coverage |
|---|---|---|---|
| **A — stock llama.cpp** | baseline | baseline | all 3 models ✓ |
| B — speculative decoding | **1.48× slower** end-to-end | −2.9 pp | works |
| C — OpenVINO backend | not attempted | — | — |
| **D — ik_llama.cpp** | **1.05-1.53× faster** end-to-end | **−8 to −9 pp** (parallel collapses) | Phi-4 doesn't load |
| E — vLLM CPU | not attempted (different format) | — | — |

**No engine cleanly beats stock llama.cpp at this hardware shape.** The closest is ik_llama.cpp, and "closest" has three asterisks:

1. The win is in **prompt evaluation**, not generation — so the speedup shrinks as the model gets relatively faster on stock (Qwen 1.53× → Gemma 1.05×).
2. **Parallel tool calls are completely broken** on ik_llama master (Qwen 80 % → 0 %, Gemma 100 % → 0 %). That's the exact category Gemma is best at and is what makes it our default ship recommendation. Hard veto for any production swap.
3. **Phi-4-mini doesn't load** on ik_llama (tied-embeddings tensor layout not yet supported). Hard coverage gap.

Speculative decoding is **anti-pattern at the 4B-target scale on CPU** — the published 2.5× wins are at 7B+ where draft inference is genuinely tiny vs target per-token cost. Below that scale, draft+verify orchestration eats more than the drafts save.

## Recommendation (no change)

**Ship stock llama.cpp + gemma-4-E4B-it at Q4_K_M.** Nothing in this bake-off displaced that. The interesting wins all live elsewhere — larger targets, multi-socket NUMA, GPU, or Apple Metal. None of which is the box we benchmarked on.

If you're memory-bandwidth-bound on a long-context use case (32 K+, low RAM headroom), TurboQuant's `tbq3_0` cache type from PR #21089 becomes worth a second look. For interactive 4 K-context tool-calling, it's a net loss.

## Engines we did not run, and why

- **C — OpenVINO backend.** Real candidate; not run due to time budget. Open as a follow-up — most plausible "drop-in win on Intel" we haven't measured.
- **E — vLLM CPU backend.** Different model format (HF checkpoints, not GGUF), high-throughput multi-user design that doesn't match our single-stream interactive workload. Likely an apples-to-oranges loss; left out.

## Method

Each cell:
1. Boot the engine in Docker with the same cgroup caps.
2. Wait for `/health`.
3. 35-case BFCL subset via the stdlib harness `/harness/run_bfcl.py` against `/v1/chat/completions` with `tools=[...]`.
4. Record p50/p95 wall-clock, overall_pass, format_pass_rate, by-category.
5. (Where applicable) separate `llama-bench` invocation for `gen_eval_tps` / `prompt_eval_tps`.

Spec — including success criteria — at [`/specs/cpu-fast-inference-bake-off`](/specs/cpu-fast-inference-bake-off).
