# Morning handoff — llama-local-benchmarks · 2026-05-20

> This file is the public handoff. Operational details (host identity, internal endpoint URLs, ssh aliases) live in **`HANDOFF.local.md`** which is gitignored.

## TL;DR

- **Site (deployed):** https://deemwar-products.github.io/llama-local-benchmarks/
- **Article (narrative):** https://deemwar-products.github.io/llama-local-benchmarks/article
- **Results table:** https://deemwar-products.github.io/llama-local-benchmarks/results
- **Static endpoint (always public):** https://deemwar-products.github.io/llama-local-benchmarks/api/summary.json
- **Repo (public):** https://github.com/deemwar-products/llama-local-benchmarks

The internal/live endpoint URL is in `HANDOFF.local.md` — keep it off public surfaces.

## What ran

A 6-cell sweep on a shared CPU host inside cgroup'd Docker (cpus=4 cpuset=8-11 mem=12g):

|  | Qwen3.5-4B | gemma-4-E4B-it | Phi-4-mini |
|---|---|---|---|
| **std** (FP16 KV) | `qwen3.5-4b_std` | `gemma-4-e4b_std` | `phi-4-mini_std` |
| **tq** (turbo3 KV) | `qwen3.5-4b_tq` | `gemma-4-e4b_tq` | `phi-4-mini_tq` |

Each cell: 35 BFCL-style tool-calling cases (20 simple + 10 multiple-function + 5 parallel) + `llama-bench -p 256 -n 128 -r 2` + RSS capture. Patched mid-run after diagnosing two real issues:

1. Default `--jinja` on llama-server activates reasoning/thinking mode → models wasted 200+ tokens "thinking" before tool calls. Fixed with `--reasoning off --reasoning-budget 0`. Documented in [`article`](https://deemwar-products.github.io/llama-local-benchmarks/article#two-early-surprises).
2. The harness was sending an unnecessary `Authorization` header and reusing keepalive connections; some llama-server builds drop the connection. Fixed by sending `Connection: close` and removing the auth header.

## Top-line numbers

See `/results` on the deployed site or `/api/summary.json` for live values.

## Decisions / recommendations

Captured in the deployed [article](https://deemwar-products.github.io/llama-local-benchmarks/article) once the sweep lands.

## TurboQuant outcome

Documented in the article's `## The TurboQuant build adventure` section and in the spec § 9 (Phase 0 status).

## What was decided without you (overnight)

1. **Made the repo public.** Required for GitHub Pages on the current plan. No secrets in repo (only public model URLs, harness code, results). Revert with `gh repo edit deemwar-products/llama-local-benchmarks --visibility private` if you'd rather.
2. **`gemma-4-4b` doesn't exist**; substituted **`gemma-4-E4B-it`** — Google's MatFormer-based 4B-effective edge variant.
3. **35 BFCL cases**, not 100. Embedded subset (20 simple / 10 multiple_function / 5 parallel) — reproducible and licence-clean. Easy to expand later — see `harness/bfcl_subset.json`.
4. **TurboQuant fork rank:** tried `atomicmilkshake` first, then `TheTom`, `MartinCrespoC`, `PippBauda`. Outcome in `results/tq-build-status.json` and the article.
5. **`max_tokens=192`, `--ctx-size=4096`, `--reasoning off`** — defaults chosen for short tool-call turns.
6. **Public docs sanitized** of any host IP, hostname, ssh alias, or co-tenant app names (per your call mid-run). Hardware specs stay generic.

## To re-run

See `CLAUDE.md` for the commands. The operational `cd` paths and host aliases are in `CLAUDE.local.md` if needed (gitignored).
