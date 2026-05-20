---
layout: home

hero:
  name: "Gemma quietly won."
  text: "I tried 4 LLM speedups on CPU. 3 made it slower."
  tagline: "94% tool-calling accuracy. 6.2 s p50. Single Xeon, no GPU. Stock llama.cpp + Gemma-4-E4B-it beat every clever trick I threw at it — TurboQuant, speculative decoding, ik_llama.cpp, the lot."
  actions:
    - theme: brand
      text: Read the article →
      link: /article
    - theme: alt
      text: Engine bake-off
      link: /article-engines
    - theme: alt
      text: Raw results JSON
      link: /results

features:
  - title: TurboQuant — "8× faster"
    details: "The headline is a synthetic GPU-kernel number. On real CPU end-to-end it ran 2.2× slower and dropped Qwen accuracy 17 pp. Memory savings real; speed wins conditional."
  - title: Speculative decoding
    details: "Published 2.5–3× CPU speedup is real — only on 7B+ targets. At 4B on a 4-core cgroup: 1.48× SLOWER. Draft + verify orchestration eats more than the drafts save."
  - title: ik_llama.cpp
    details: "1.53× faster end-to-end on Qwen via IQK matmul kernels. But parallel tool calls collapse 80% → 0% and Phi-4 will not even load. Hard veto for production."
  - title: Gemma-4-E4B-it quietly won
    details: "94.3% overall. 100% on multi-function AND parallel calls. 6.2 s p50. Beat Qwen 3.5 4B and Phi-4-mini-instruct outright. This is the ship recommendation."
  - title: Phi-4-mini ships broken
    details: "Drop-in `--jinja` tool-calling = 0.0% pass — llama.cpp falls back to a prose parser. A 30-character system prompt rescues 74%. Lose parallel calls anyway."
  - title: What to actually ship
    details: "Stock `ghcr.io/ggml-org/llama.cpp:full` + Gemma-4-E4B-it Q4_K_M + FP16 KV + `--jinja --reasoning off --reasoning-budget 0`. No fork. No quantized KV. No draft model."
---

## In one paragraph

Three ~4B open-weight tool-calling models (Qwen 3.5 4B, Google Gemma-4-E4B-it, Microsoft Phi-4-mini), four CPU speedup techniques (TurboQuant KV quantization, speculative decoding, ik_llama.cpp, OpenVINO/vLLM as outside references), one shared Xeon E-2176G box, 35 BFCL tool-calling cases per cell, full cgroup isolation, sanitized public artifacts. Eleven cells of measured pain. The TL;DR is in the hero. The story is in [the article](/article). The data is on [/results](/results).

## Where to go

- **[The article](/article)** — narrative version, ~6 min, the one you share.
- **[Engine bake-off](/article-engines)** — deeper dive: stock vs specdec vs ik_llama.cpp, with numbers.
- **[Results table](/results)** — all 11 cells, sortable, no prose.
- **[HTTP API](/api)** — grab the JSON directly.
- **[Spec: TurboQuant bake-off](/specs/llama-cpp-turboquant-benchmark)** · **[Spec: Engine bake-off](/specs/cpu-fast-inference-bake-off)** — methodology and why each measurement was chosen.

All MIT, all reproducible from a [public repo](https://github.com/deemwar-products/llama-cpu-benchmarks).
