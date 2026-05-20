# I tried four LLM inference techniques on a CPU box. Three made it slower.

*A week of benchmarks. 11 cells. Two days fixing other people's bugs. One winner — and it's the boring default.*

— *Published 2026-05-20 · raw data at [/api](/api) · all 11 cells on [/results](/results)*

---

## The setup, in one paragraph

A single Xeon E-2176G — 6c/12t, AVX2, no AVX-512, no GPU, 62 GB RAM, shared with other unrelated workloads. The kind of commodity Hetzner-class box you actually run a side project on. I picked the three best ~4B open-weight tool-callers as of May 2026 (Qwen 3.5 4B, Google gemma-4-E4B-it, Microsoft Phi-4-mini), all at Q4_K_M imatrix weights, and put them through 35 BFCL-style tool-calling cases on top of stock `llama.cpp:full`. That's my baseline. Then I tried to make it go faster — four different ways.

::: tip TL;DR
**Ship stock llama.cpp + gemma-4-E4B-it at Q4_K_M with FP16 KV.** Don't change inference engine. Don't enable TurboQuant. Don't add speculative decoding. The boring default beat everything else I tried on this hardware shape.
:::

## The scoreboard

| Technique I tried | Throughput vs stock | What broke |
|---|---|---|
| **TurboQuant `tbq3_0` KV** (PR #21089) | **2.2× slower** | accuracy −17 pp on Qwen, parallel calls 0 % |
| **Speculative decoding** (0.8B draft → 4B target) | **1.48× slower** | small accuracy regression |
| **ik_llama.cpp** (ikawrakow CPU fork) | **1.05–1.53× faster** | parallel calls 0 % on Qwen + Gemma; Phi-4 doesn't load |
| **OpenVINO backend** | not run | — *(real follow-up territory)* |
| **vLLM CPU backend** | not run | different model format, multi-user design |

Three losses. One technique-with-caveats that's faster but loses the headline feature (parallel tool calls). The boring default — `ghcr.io/ggml-org/llama.cpp:full`, FP16 KV, `--jinja --reasoning off` — is the local optimum at this hardware shape.

## Surprise #1: the TurboQuant 8× speedup doesn't survive contact with real hardware

TurboQuant (Zandieh et al., **ICLR 2026**, from Google Research / DeepMind) is a vector-quantization technique for the KV cache. The paper's headline is **8× faster** attention math. There's an active llama.cpp PR ([#21089](https://github.com/ggml-org/llama.cpp/pull/21089), open) bringing CPU AVX2 support. I had high expectations.

I measured four data points across published runs + my own:

| Source | Hardware | TurboQuant vs baseline |
|---|---|---|
| Google paper headline | H100 GPU, attention-kernel isolation | **8× faster** ← marketing |
| PR #21089's own table | 4-thread CPU, Qwen3.5-4B | **2.1× slower** vs `q4_0` KV |
| Discussion #21829 user | 2× H200 GPU | **1.18× slower** vs FP16 KV |
| **My run** | Xeon E-2176G AVX2 CPU | **2.2× slower** end-to-end per BFCL turn vs FP16 KV |

That 8× number is real, but only inside a specific synthetic benchmark: GPU, attention-kernel-bound workload, dequant+matmul math isolated from end-to-end inference. Move any of those variables and TurboQuant is *slower*. The maintainers themselves admit it in discussion #21829: at high memory bandwidth, the dequant overhead exceeds the memory savings; they recommend it only for "mid-range single GPU setups" at long context.

It's a **memory-saving** technique partly marketed as a speed technique. The memory savings are real and unconditional. The speed wins are conditional on a specific failure mode (memory-bandwidth-bound) that most workloads don't have. Mine especially: 60 GB free RAM at 4 K context, the KV cache is hundreds of megabytes.

And the accuracy claim — "matches FP16 within rounding distance" — was a PPL number, not a tool-calling number. On BFCL, Qwen dropped from 91.4 % to 74.3 % overall and **parallel call accuracy collapsed from 80 % to 0 %**.

## Surprise #2: speculative decoding is anti-pattern below 7B targets

Speculative decoding is built into llama.cpp (`--spec-draft-model` or `--lookup`). The pitch: a small draft model speculates ahead, the target verifies in parallel, net **2.5–3× CPU speedup with zero quality loss**.

That's the number on **7B+ targets**. At my 4B-class scale on a 4-core cgroup, with a Qwen 0.8B draft against a Qwen 3.5 4B target, I measured **1.48× slower** end-to-end. Same accuracy, just slower.

Why: with 4 cores allocated, the cost of running the draft model and verifying its tokens against the target adds up to more than the per-token savings, because the target isn't large enough for its per-token cost to dwarf the orchestration overhead. Speculative decoding is great when target ≫ draft. When target = 5× draft on a small CPU budget, it's noise that costs you.

## Surprise #3: Phi-4-mini doesn't tool-call out of the box

I gave Phi-4-mini-instruct the same 35-case BFCL run with stock llama.cpp and `--jinja`. **0.0 % overall pass.** Not one single tool call.

Investigation: llama.cpp's chat-format detector logs `Chat format: peg-native` when Phi-4 loads — meaning it didn't recognise Phi-4's tool-calling format and fell back to a generic prose parser. With no tool schemas surfaced to the model, Phi responded in **English prose** to tool-able queries ("you can find weather at weather.com…"). With `tool_choice: required` it invented Python-like syntax (`get_weather_celsius("Tokyo")`). Either way: zero parseable tool calls.

The fix: prepend a one-line system prompt that contains the tool schemas in JSON and tells Phi to emit `{name, arguments}` JSON. Same 35 cases re-run: **74.3 % overall pass**. The model knows how to tool-call — the GGUF's chat template just doesn't tell it.

So: **if you want Phi-4-mini and you're using llama.cpp's drop-in `--jinja` tool-calling, expect 0 %** until either Microsoft's GGUF chat template is updated or llama.cpp adds a Phi-4 tool-format parser. If you can prepend a tools-in-system-prompt, you recover most of the way — but you've also lost parallel-call support (Phi can't emit a JSON array of calls under that prompt: 0/5 parallel cases pass).

## Surprise #4: Gemma-4-E4B-it quietly wins everything

I expected Qwen to win — Qwen has dominated BFCL in its weight class for most of 2025. It did not.

| Model | gen tok/s | p50 ms | Tool overall |
|---|---:|---:|---:|
| **gemma-4-E4B-it** | 8.59 | **6,240** | **94.3 %** |
| Qwen 3.5 4B | 9.79 | 13,739 | 91.4 % |
| Phi-4-mini *(drop-in)* | 10.62 | 7,517 | **0.0 %** |
| Phi-4-mini *(+ system prompt)* | n/a | 7,983 | 74.3 % |

Gemma is 13 % slower on raw `gen_eval_tps` but **2.2× faster end-to-end per turn** — because it emits shorter, tighter responses around the tool call. It's the **only model that hits 100 % on both multi-function selection and parallel calls** in this run. The dedicated tool tokens Google added in Gemma 4 (`<|tool>`, `<|tool_call>`, `<|tool_result>`) and llama.cpp's matching `peg-gemma4` chat format parser are doing real work.

If you're shipping a small tool-calling LLM on CPU today, you ship Gemma.

## Surprise #5: ik_llama.cpp wins on prompt eval, then breaks the headline feature

`ik_llama.cpp` is ikawrakow's CPU-tuned fork — he's a core llama.cpp dev, and the fork ships AVX2-specific IQK matmul kernels plus IQK Flash Attention. Published benchmark: ~2× faster on AVX2 Xeon.

On my hardware, on Qwen:

| Metric | stock | ik_llama | Δ |
|---|---:|---:|---|
| prompt tok/s | 35.85 | 58.08 | **1.62× faster** |
| gen tok/s | 9.79 | 8.37 | 0.85× *(slower)* |
| **p50 latency** | 13,739 ms | **8,977 ms** | **1.53× faster** |
| overall_pass | 91.4 % | 82.9 % | −8.6 pp |
| simple | 95 % | **100 %** | +5 pp |
| **parallel** | 80 % | **0 %** | **−80 pp** |

The win is in **prompt eval**, not generation — and tool-calling prompts include the tool schemas, so prompt eval matters a lot. But parallel tool calls collapse entirely on both Qwen and Gemma (gemma same pattern, 100 % → 0 %), and Phi-4-mini doesn't load at all (tied-embeddings tensor layout not supported in ik_llama master). It's a real speedup with hard coverage gaps.

If you don't need parallel tool calls, and you only run Qwen or Gemma, ik_llama is worth a look. For our actual ship target (Gemma + parallel calls intact), it's a hard veto.

## What I actually shipped

Same as where I started. **Stock `llama.cpp:full`. Gemma-4-E4B-it at Q4_K_M. FP16 KV. `--jinja --reasoning off --reasoning-budget 0`.** No quantized KV cache. No draft model. No fork. No alternative engine.

The interesting wins all live elsewhere:

- **A larger target model** (where speculative decoding actually pays off).
- **A wider/multi-socket CPU** with AMX (where vLLM's NUMA story kicks in).
- **A different hardware shape** — GPU, or Apple Silicon with the `PippBauda/llama.cpp-turboquant-mtp` Metal fork.
- **Long contexts** (32 K–128 K) where TurboQuant's KV memory savings become real.

For 4 K-context interactive tool-calling on commodity AVX2 — knowing the local optimum **is** the optimum is, itself, a result. Stock llama.cpp is the answer. Don't outsmart it.

## What's on the page

- **[/results](/results)** — all 11 cells, sortable. Raw JSON at [/api/summary.json](/api/summary.json).
- **[/article-engines](/article-engines)** — the engine bake-off deep dive (this article's source for ik_llama / specdec / TurboQuant numbers).
- **[/specs/llama-cpp-turboquant-benchmark](/specs/llama-cpp-turboquant-benchmark)** — the original spec covering model picks, hardware target, prod-safety constraints, the 35 BFCL cases.
- **[/specs/cpu-fast-inference-bake-off](/specs/cpu-fast-inference-bake-off)** — the engine bake-off spec.
- **Repo (public, MIT)**: [github.com/deemwar-products/llama-local-benchmarks](https://github.com/deemwar-products/llama-local-benchmarks).

If you find this useful or you have a counter-result on different hardware, please share.

## Method (short version)

Each cell: Docker container with cgroup caps (`--cpus=4 --cpuset-cpus=8-11 --memory=12g`) so the benchmark can't disturb co-tenant workloads. Boot the engine, wait for `/health`, run `llama-bench -p 256 -n 128 -r 2` for throughput, then 35 BFCL-style cases (20 simple + 10 multiple-function with distractors + 5 parallel) via `harness/run_bfcl.py` for tool-calling accuracy. Strict pass = format ∧ function ∧ argument. Latencies are end-to-end wall-clock from the harness, including TCP round-trip.

Spec, harness source, and per-cell JSON all in the [public repo](https://github.com/deemwar-products/llama-local-benchmarks).
