# CLAUDE.md — llama-local-benchmarks

This repo benchmarks the three best open-weight ~4B tool-calling instruct models from Qwen / Google / Microsoft on a single commodity CPU box, with and without **TurboQuant** (Google DeepMind, ICLR 2026) KV-cache compression.

Read this file before doing anything in the repo.

## Target host (general shape)

All benchmark execution runs on a **shared CPU host** (specific identity intentionally kept out of this public file — see `CLAUDE.local.md` if present for operational details). The host concurrently runs **other unrelated workloads**, so every benchmark container must stay cgroup-isolated.

Hard rules when running anything on that host:

1. **Always cgroup-cap.** Every benchmark container must use `--cpus=4 --cpuset-cpus=8-11 --memory=12g --memory-swap=12g`. Cores 0-7 are reserved for the rest of the system.
2. **Off-peak windows only** for new runs.
3. **Workspace is `/opt/llamabench/`** on the host — never write benchmark artifacts elsewhere.
4. **Models live in `/opt/llamabench/models/`** as raw GGUF files. They are gitignored.
5. **Never `apt install` on the host.** Use the prebuilt llama.cpp Docker images, or build from source inside a throwaway `ubuntu:22.04` container.
6. **Never expose internal hostnames, IPs, or co-tenant app names in any committed file** — this repo is public.

## Layout

```
docs/                  VitePress site (deployed to GitHub Pages)
  specs/               experiment specs — read before running
  .vitepress/config.mts site config; base path /llama-local-benchmarks/
  public/api/          static JSON endpoints served from the site
harness/               BFCL Python test harness (run_bfcl.py + bfcl_subset.json)
scripts/               per-cell driver shell scripts (run_cell.sh, etc.)
endpoint/              stdlib HTTP service serving results JSON
results/               per-cell JSON + aggregated summary.json (created on run)
.github/workflows/     CI for VitePress deploy
```

## The 6-cell matrix

|  | Qwen3.5-4B | gemma-4-E4B-it | Phi-4-mini |
|---|---|---|---|
| **std** (FP16 KV) | `qwen3.5-4b_std` | `gemma-4-e4b_std` | `phi-4-mini_std` |
| **tbq3** (tbq3_0 KV, PR #21089) | `qwen3.5-4b_tbq3` | `gemma-4-e4b_tbq3` | `phi-4-mini_tbq3` |

Weight quant is constant: **Q4_K_M imatrix** (Bartowski / Unsloth). Only the KV cache changes.

## To re-run one cell

On the target host:

```bash
cd /opt/llamabench
./run_cell.sh qwen3.5-4b_std Qwen3.5-4B-Q4_K_M.gguf ghcr.io/ggml-org/llama.cpp:full fp16
```

Writes `results/qwen3.5-4b_std.json`.

## To re-run the full sweep

```bash
cd /opt/llamabench
for m in "qwen3.5-4b_std:Qwen3.5-4B-Q4_K_M.gguf:fp16" \
         "gemma-4-e4b_std:gemma-4-E4B-it-Q4_K_M.gguf:fp16" \
         "phi-4-mini_std:Phi-4-mini-instruct-Q4_K_M.gguf:fp16"; do
  IFS=: read cell file kv <<<"$m"
  ./run_cell.sh "$cell" "$file" ghcr.io/ggml-org/llama.cpp:full "$kv"
done
```

TQ cells require a TurboQuant-capable llama.cpp build (see `results/` for the recorded image tag and `docs/specs/llama-cpp-turboquant-benchmark.md` §7-8).

## To publish updates

Push to `main`. The `Deploy VitePress docs` workflow:
1. Copies `results/*.json` into `docs/public/api/` and strips any `host:` field from the JSON (sanitization step).
2. Builds VitePress.
3. Deploys to GitHub Pages → `https://deemwar-products.github.io/llama-local-benchmarks/`.

## When changing the harness

- `harness/bfcl_subset.json` is the source of truth. Embedded subset (not externally licensed) so future re-runs are pinned.
- Adding a category: extend `harness/run_bfcl.py:score_case` with the new shape, and add cases with the matching expected schema.
- The harness is stdlib-only — keep it that way so it runs anywhere `python3` exists.

## Hard rules (do not violate)

- Never `apt install` on the benchmark host — always use Docker.
- Never run a benchmark without the cgroup caps in §1.
- Never `git push --force` to `main` of this repo — the GitHub Pages deploy reads from `main`.
- Never commit `*.gguf` files (gitignored).
- Never paste contents of any vault directory or `*.env` file into anything.
- Never expose internal hostnames, IPs, SSH aliases, or co-tenant app names in committed files.

## Re-using the harness elsewhere

`harness/run_bfcl.py` works against any OpenAI-compatible `/v1/chat/completions` endpoint that emits `tool_calls` in the standard shape, or smuggles a tool call into `message.content` as a fenced JSON blob. Tested against `llama-server --jinja`. Should also work against vLLM, Ollama, and the OpenAI API.
