# llama-cpu-benchmarks

Benchmarks for small (~4B) open-weight tool-calling LLMs on a commodity x86 CPU box.

Compares **Qwen3.5-4B** vs **Gemma-4-E4B-it** vs **Phi-4-mini** under **standard** vs **TurboQuant** KV-cache compression — measuring tool-calling accuracy, throughput, and memory.

## Live site

**https://deemwar-products.github.io/llama-cpu-benchmarks/**

- [Findings article](https://deemwar-products.github.io/llama-cpu-benchmarks/article)
- [Results table](https://deemwar-products.github.io/llama-cpu-benchmarks/results)
- [Spec](https://deemwar-products.github.io/llama-cpu-benchmarks/specs/llama-cpp-turboquant-benchmark)
- [API JSON](https://deemwar-products.github.io/llama-cpu-benchmarks/api/summary.json)

## Layout

```
docs/specs/    experiment spec(s) — read before running
docs/          VitePress site sources
harness/       Python BFCL test harness
scripts/       per-cell driver shell scripts
endpoint/      optional stdlib HTTP service serving results JSON
results/       per-cell JSON + aggregate summary (created on run)
```
