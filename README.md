# llama-local-benchmarks

Benchmarks for small (~4B) open-weight tool-calling LLMs on commodity Hetzner CPU hardware (deemwar prod-app-1).

Compares **Qwen3.5-4B** vs **Gemma-4-4B** vs **Phi-4-mini** under **standard** vs **TurboQuant** KV-cache compression — measuring tool-calling accuracy, throughput, and memory.

## Status

Draft spec: [`docs/specs/llama-cpp-turboquant-benchmark.md`](docs/specs/llama-cpp-turboquant-benchmark.md)

## Layout

```
docs/specs/   experiment spec(s) — review before running
harness/      Python BFCL test harness
scripts/      build + run helpers (Docker, llama.cpp variants)
results/      per-cell JSON + aggregate summary (created on first run)
```
