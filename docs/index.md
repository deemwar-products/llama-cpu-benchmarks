---
layout: home

hero:
  name: "I tried four LLM speedup techniques on a CPU box."
  text: "Three made it slower."
  tagline: "One made it 1.5× faster but broke parallel tool calls. The winner is the boring default. Eleven cells of pain documented inside."
  actions:
    - theme: brand
      text: Read the article →
      link: /article
    - theme: alt
      text: Engine bake-off
      link: /article-engines
    - theme: alt
      text: Raw results
      link: /results

features:
  - title: TurboQuant's "8× faster"
    details: '...is a synthetic-GPU-kernel-isolation number that doesn''t survive real workloads. Four independent measurements (paper, PR table, H200 user, our run) all show TurboQuant ranging from 1.18× to 2.2× SLOWER end-to-end. The memory savings are real and unconditional; the speed wins are not.'
  - title: Speculative decoding
    details: 'Published 2.5–3× CPU speedup is real — but only on 7B+ targets. At our 4B / 4-core / 0.8B-draft scale, draft + verify orchestration eats more than the drafts save. We measured 1.48× SLOWER.'
  - title: ik_llama.cpp
    details: 1.62× faster prompt eval via IQK matmul kernels. 1.53× faster end-to-end on Qwen. But parallel tool-call generation collapses 80% → 0% on master, and Phi-4-mini doesn''t load at all (tied-embeddings layout). Hard veto for production.'
  - title: Gemma-4-E4B-it quietly won
    details: '94.3% tool-calling accuracy, **100% on multi-function and parallel calls**, 6.2s p50 latency. Beats Qwen 3.5 4B (91.4%, 13.7s) and Phi-4-mini-instruct (0% drop-in, 74.3% with a system-prompt workaround) outright.'
  - title: Phi-4-mini ships broken for `--jinja` tool-calling
    details: 'llama.cpp falls back to "Chat format: peg-native" — Phi-4''s tool schema isn''t surfaced, the model responds in English prose to tool-able prompts. 30-character workaround in the article restores 74.3% accuracy. Lose parallel calls anyway.'
  - title: The actual ship recommendation
    details: 'Stock `ghcr.io/ggml-org/llama.cpp:full`. Gemma-4-E4B-it at Q4_K_M. FP16 KV cache. `--jinja --reasoning off --reasoning-budget 0`. No quantized KV. No draft model. No fork. No alternate engine. Nothing in the bake-off displaced this.'
---

## What this is

A week of running a single, narrow benchmark — **35 BFCL-style tool-calling cases on three ~4B models, three quantization variants, three inference engines, on one shared CPU box** — to find out what actually makes a small open-weight LLM faster on commodity AVX2 silicon. Eleven cells, two of them skipped with structured "this doesn't work because…" notes, every number reproducible from a public repo.

The headline takeaways are in the article; the data is on the [results page](/results); the spec is in `docs/specs/`; the harness is stdlib-only Python in `harness/`; everything's under MIT.

## Why you might care

- You're picking a small tool-calling LLM and you don't want to run the benchmarks yourself.
- You read the TurboQuant marketing and want to know if it's real on CPU. *(It's real. It's not fast.)*
- You're tempted by speculative decoding for a 4B target on 4 cores. *(Don't.)*
- You want a public, sanitized, decision-grade table to share with your team for "what should we ship?" discussions.

## What we did NOT do

- Run a GPU. We have no usable GPU on this box. The article calls out where wins likely *do* live (vLLM on AMX, TurboQuant on mid-range single GPUs at long context, Metal on Apple Silicon).
- Run multi-user batched workloads. This is single-stream interactive tool-calling. Different optimum.
- Test all engines exhaustively. **OpenVINO** and **vLLM CPU** are the two we didn't run; both are documented as follow-up territory in the engine bake-off article.

## Where to go

- **[The article](/article)** — the narrative version, ~6 min read.
- **[Engine bake-off article](/article-engines)** — the deeper dive into 4 inference engines we tested.
- **[Results table](/results)** — straight numbers, no prose.
- **[HTTP API](/api)** — fetch the data programmatically.
- **[Spec: TurboQuant bake-off](/specs/llama-cpp-turboquant-benchmark)** · **[Spec: Engine bake-off](/specs/cpu-fast-inference-bake-off)** — methodology + what we measured and why.
