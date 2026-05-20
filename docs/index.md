---
layout: home

hero:
  name: llama-local-benchmarks
  text: Small-model tool-calling on a commodity CPU box
  tagline: Qwen 3.5 × Gemma 4 × Phi-4-mini, with and without TurboQuant KV-cache compression, on a single commodity CPU box.
  actions:
    - theme: brand
      text: Read the findings →
      link: /article
    - theme: alt
      text: Results table
      link: /results
    - theme: alt
      text: Spec
      link: /specs/llama-cpp-turboquant-benchmark

features:
  - title: 6-cell matrix
    details: 3 models × 2 KV-cache settings (standard FP16 vs TurboQuant tbq3_0 from upstream PR #21089) at Q4_K_M weights, 35 BFCL-style tool-calling cases each.
  - title: Real production hardware
    details: Xeon E-2176G, 6c/12t, 62 GB RAM, AVX2, no GPU. Shared with other workloads via strict cgroup caps so the benchmark can't disturb them.
  - title: Open, reproducible
    details: Public GitHub repo, MIT-licensed harness, raw per-cell JSONs, live HTTP endpoint serving the same data the article cites.
---

## What this is

A head-to-head of the three best open-weight ~4B tool-calling instruct models available as of May 2026 — **Qwen 3.5 4B**, **Google gemma-4-E4B-it**, **Microsoft Phi-4-mini-instruct** — measured on a single commodity x86 CPU box, with and without **TurboQuant** (Google DeepMind, ICLR 2026) KV-cache compression.

## What it answers

1. Which of the three is the best small tool-caller on a CPU-only edge box?
2. Does TurboQuant transfer from H100 GPUs to commodity x86 CPUs?
3. What throughput and accuracy should you actually expect when running a ~4B model on a Coffee Lake Xeon?

## Where to start

- **[Findings article](/article)** — the narrative version, ~5 min read.
- **[Results table](/results)** — straight numbers, no prose.
- **[HTTP API](/api)** — fetch the same data programmatically.
- **[Spec](/specs/llama-cpp-turboquant-benchmark)** — what was tested, how, and the prod-safety constraints.
