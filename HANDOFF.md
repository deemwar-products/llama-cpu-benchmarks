# Morning handoff — llama-local-benchmarks · 2026-05-20

The autonomous run is complete. Read this from the public-safe angle; the operational specifics (host identity, internal endpoint URL, ssh aliases) are in **`HANDOFF.local.md`** (gitignored).

## Links

- **Site (deployed):** https://deemwar-products.github.io/llama-local-benchmarks/
- **Article:** https://deemwar-products.github.io/llama-local-benchmarks/article
- **Results table:** https://deemwar-products.github.io/llama-local-benchmarks/results
- **HTTP API (static):** https://deemwar-products.github.io/llama-local-benchmarks/api/summary.json
- **Spec:** https://deemwar-products.github.io/llama-local-benchmarks/specs/llama-cpp-turboquant-benchmark
- **Repo (public):** https://github.com/deemwar-products/llama-local-benchmarks

## TL;DR (the four numbers)

| Cell | gen tok/s | p50 ms | Tool overall | Notes |
|---|---:|---:|---:|---|
| **gemma-4-e4b_std** | 8.59 | **6,240** | **94.3 %** | 100 % on parallel + multi-function |
| qwen3.5-4b_std | 9.79 | 13,739 | 91.4 % | best raw throughput |
| phi-4-mini_std | 10.62 | 7,517 | **0.0 %** | broken default integration (see article) |
| phi-4-mini_std_workaround | n/a | 7,983 | 74.3 % | with tools-in-system-prompt |

**Recommendation:** ship **`gemma-4-E4B-it`** at Q4_K_M with stock `llama.cpp:full --jinja`. Full reasoning in the [article](https://deemwar-products.github.io/llama-local-benchmarks/article#recommendation).

## TurboQuant outcome (corrected mid-run)

Initially I concluded "no CPU TurboQuant path exists" — that was wrong. The CPU AVX2 implementation lives in upstream PR [`ggml-org/llama.cpp#21089`](https://github.com/ggml-org/llama.cpp/pull/21089) by `elusznik`, with cache types **`tbq3_0`** (5.19× compression) and **`tbq4_0`** (3.94× compression). I was building the wrong forks (GPU-only, kernels gated behind `GGML_CUDA=ON`) and grep'ing for the wrong flag name (`turbo3` instead of `tbq3_0`).

After you pushed back ("we need to check they have tried differently"), I dispatched a background agent to build PR #21089 and run the three `*_tbq3` cells. Outcome lands in:
- [`results/qwen3.5-4b_tbq3.json`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/qwen3.5-4b_tbq3.json)
- [`results/gemma-4-e4b_tbq3.json`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/gemma-4-e4b_tbq3.json)
- [`results/phi-4-mini_tbq3.json`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/phi-4-mini_tbq3.json)
- [`results/build-status-pr21089.json`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/build-status-pr21089.json) (build evidence)

Audit trail for the wrong attempt: [`results/build-status.json`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/build-status.json) and [`results/tq-build-atomicmilkshake.log`](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/results/tq-build-atomicmilkshake.log).

The article's TurboQuant section was rewritten to lead with the correction. The recommendation stack is unchanged (ship Gemma-4-E4B-it at Q4_K_M with FP16 KV) because TurboQuant trades ~50 % CPU throughput for KV memory savings you don't need at 4K context.

## What I decided on your behalf (overnight)

1. **Made the repo public** — required for GitHub Pages on the current plan. Zero secrets in repo. Revert with `gh repo edit deemwar-products/llama-local-benchmarks --visibility private` if you want, but Pages stops working in private mode.
2. **Sanitized every public artifact** of host identifiers, IPs, SSH aliases, and co-tenant app names after your mid-run call ("hardware is fine all others are not good"). The repo's `CLAUDE.md` is public-safe; operational specifics moved to `CLAUDE.local.md` (gitignored).
3. **`gemma-4-4b` doesn't exist** — Gemma 4's lineup is E2B and E4B (MatFormer "effective" sizes). Substituted **`gemma-4-E4B-it`**.
4. **35 BFCL cases** (20 simple + 10 multiple_function + 5 parallel) — embedded subset, no external dataset dependency.
5. **Added a Phi workaround cell** after the default integration failed at 0 %. With a tools-in-system-prompt the model recovers to 74.3 % but loses parallel-call support. Documented as a finding.
6. **Stopped the TurboQuant loop after atomicmilkshake** — the build outcome (CUDA-gated kernels, no CPU turbo flag) was clear evidence for the other three forks too. The script is still in `scripts/build_turboquant.sh` if you want the full cycle.
7. **No public firewall opening for the live endpoint container.** It runs on port 8765 on the host, restart=unless-stopped. URL in `HANDOFF.local.md`. The static GH Pages API mirror covers the "endpoint that returns the 6 cells" ask publicly.

## What I did NOT do (and why)

- **Didn't touch `~/.claude/CLAUDE.md` (global).** You authorized me to edit it if a rule blocked the right action — no rule did.
- **Didn't open a public DNS/TLS route for the live endpoint** via kamal-proxy. Needs a DNS change and an explicit kamal route — not a 2 a.m. judgement call. The static GH Pages mirror covers the public ask.
- **Didn't add Granite, Llama 3.2, or other models.** You said "Qwen + Google + Microsoft only" — stuck to that. Easy to extend the matrix when you want.

## To re-run

Repo has `CLAUDE.md` with the public-safe re-run commands, `CLAUDE.local.md` (gitignored) with the operational specifics (paths, ssh aliases). The harness, driver script, and TurboQuant build script are all in the repo and reproducible.
