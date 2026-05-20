# Spec — CPU-Fast LLM Inference Bake-off (post-llama.cpp)

**Status:** Draft v1 · awaiting approval
**Date:** 2026-05-20
**Driver:** Muthukumaran Navaneethakrishnan
**Predecessor:** [`llama-cpp-turboquant-benchmark`](./llama-cpp-turboquant-benchmark.md) — concluded that `tbq3_0` costs ~2× throughput for KV-memory savings the hardware doesn't need. This spec is the follow-up: **stop tuning KV cache, swap the inference engine entirely.**

---

## 1. Goal

Find the **fastest single-stream tool-calling inference path** for ~4B open-weight models on the same commodity AVX2 CPU box, beating the **9.79 gen tok/s** (Qwen) / **8.59 gen tok/s** (Gemma) baseline established by stock `ghcr.io/ggml-org/llama.cpp:full`. Same models, same Q4_K_M weights, same BFCL accuracy harness — only the inference engine changes.

The end-state is a recommendation matrix readers can scan in 30 seconds: "for hardware shape X, ship engine Y."

## 2. Non-goals

- No new model selection (Qwen3.5-4B + gemma-4-E4B + Phi-4-mini stay as the targets).
- No GPU. Same Xeon E-2176G AVX2-only CPU box.
- No new quantization scheme (Q4_K_M stays the weight quant baseline).
- No batched / multi-user throughput. Single-stream interactive workload is what we care about.

## 3. The engine matrix

Five candidates, each a real production-grade alternative to stock `llama.cpp`:

| # | Engine | Why it's a candidate | Risk |
|---|---|---|---|
| **A** | **stock llama.cpp** (`ghcr.io/ggml-org/llama.cpp:full`) | already-measured baseline — Qwen 9.79 / Gemma 8.59 / Phi 10.62 gen tok/s | none — already done |
| **B** | **llama.cpp + speculative decoding** (mainline `--draft-model`) | published 2.5-3× CPU speedup with zero quality loss; uses the existing GGUF, the same llama-server, just adds a small draft model | needs a matched draft per target (e.g. Qwen3.5-0.5B for Qwen 4B); ~+500 MB RAM per model |
| **C** | **llama.cpp + OpenVINO backend** | upstream in May 2026; translates GGML compute graph → OpenVINO graph + kernel fusion + Intel CPU-specific optimisations; same GGUF in, same OpenAI-compatible server out | Q5_K / Q6_K only have runtime conversion (slower start); Coffee Lake gets a subset of OpenVINO's wins (no AMX) |
| **D** | **`ik_llama.cpp`** (ikawrakow fork) | published ~2× faster than mainline on AVX2 Xeon (5.05 vs 2.70 tok/s on E5-2683 v4); same llama-server CLI, same GGUF | fork; needs build from source; some quant types diverge from mainline |
| **E** | **vLLM CPU backend** (v0.9.1+) | PagedAttention, dynamic batching, V1 engine + IPEX for Intel; designed for production serving | best wins are on Xeon 6 with AMX (we have AVX2 only); high-throughput design — single-stream latency may be worse, not better |

Engines explicitly **dropped** after research:

- **SGLang** — Linux/WSL-only, slow model load (minutes), no clean CPU benchmark vs llama.cpp at this size class.
- **CTranslate2** — Transformer-translation lineage, less LLM-tuned, not Phi/Gemma/Qwen-first.
- **PowerInfer-2** — smartphone NPU/CPU hybrid, not our hardware shape.
- **Intel IPEX-LLM** — repo archived Jan 28 2026 (read-only), v2.2.0 still installable but signals abandonment.
- **mistral.rs** / **llamafile** — improvements already upstreamed to llama.cpp (tinyBLAS), no separate advantage on AVX2 Xeon.

## 4. Test plan

### 4.1 Phase 0 — feasibility (1-2 hrs)

For each of B, C, D, E:

1. Build / pull the engine in Docker on the benchmark host (no host `apt install`).
2. Boot it with **Qwen3.5-4B-Q4_K_M** (smallest, fastest-loading) under the cgroup cap (`--cpus=4 --cpuset-cpus=8-11 --memory=12g`).
3. Smoke test: one `/v1/chat/completions` round-trip with a `get_weather` tool. Validate the response contains a valid tool_call.
4. Gate criteria:
   - Build / pull succeeds.
   - Server boots in ≤120 s.
   - Smoke test returns a parsable tool call.

Engines that fail Phase 0 drop out and get documented in `results/build-status-engine-bakeoff.json`.

### 4.2 Phase 1 — single-model deep dive (3-4 hrs)

Pick the **2 fastest engines from Phase 0** and run **Qwen3.5-4B-Q4_K_M** + **gemma-4-E4B-it-Q4_K_M** + **Phi-4-mini-instruct-Q4_K_M** through each. Same 35-case BFCL subset, same `llama-bench`-equivalent throughput measurement (use each engine's native bench if available, else the harness's wall-clock).

Cells (max 6): `qwen3.5-4b_${engine}`, `gemma-4-e4b_${engine}`, `phi-4-mini_${engine}` × 2 engines.

### 4.3 Phase 2 — winner sweep, optional

If Phase 1 produces a clean winner with > 1.5× speedup over stock llama.cpp at no accuracy regression, expand the matrix:

- Run the winning engine on the full 4-model lineup (incl. Phi workaround).
- Add a long-context (16 K, 32 K) cell to check whether the win holds at longer contexts.
- Add a speculative-decoding overlay where applicable (engine B is itself a speculative variant; C/D/E may also have spec-dec hooks).

## 5. Per-engine setup notes

### B. llama.cpp + speculative decoding

```bash
# Target: Qwen 3.5-4B (Q4_K_M)
# Draft:  Qwen 3.5-0.5B (Q4_K_M) — same family, same tokenizer
docker run … ghcr.io/ggml-org/llama.cpp:full \
  --model     /models/Qwen3.5-4B-Q4_K_M.gguf \
  --model-draft /models/Qwen3.5-0.5B-Q4_K_M.gguf \
  --draft-max 8 --draft-min 4 \
  --threads 4 --ctx-size 4096 --jinja --reasoning off --reasoning-budget 0
```

Same flag for gemma-4-E2B-it as draft for E4B target. For Phi-4-mini, no smaller sibling exists; fall back to **n-gram lookup** (`--lookup`) which uses repeated prompt patterns instead of a draft model. Cost: ~500 MB extra RAM per cell, well inside the 12 GB cap.

### C. llama.cpp + OpenVINO backend

```bash
# Build llama.cpp with -DGGML_OPENVINO=ON inside ubuntu:22.04 base image
# (Intel publishes a ready image once OpenVINO 2026.1 lands; pin to that)
docker run … intel/openvino-llama-cpp:2026.1 \
  --model /models/Qwen3.5-4B-Q4_K_M.gguf \
  --device CPU \
  --threads 4 --ctx-size 4096 --jinja ...
```

Conversion of GGUF → OpenVINO graph happens on first model load (~30-90 s overhead). Subsequent boots are cached. Q4_K_M is natively supported; no runtime conversion needed.

### D. `ik_llama.cpp`

Build from `github.com/ikawrakow/ik_llama.cpp` master inside `ubuntu:22.04`. Same `cmake -DGGML_NATIVE=ON -DGGML_AVX2=ON -DGGML_CUDA=OFF` flow as PR #21089. Resulting `llama-server` accepts the same CLI as mainline. Run identical to engine A.

### E. vLLM CPU backend

```bash
docker run … vllm/vllm-openai:cpu-latest \
  --model microsoft/Phi-4-mini-instruct \
  --device cpu \
  --tensor-parallel-size 1 \
  --max-model-len 4096 \
  --dtype bfloat16 \
  --enable-tool-call
```

**Note:** vLLM consumes raw HuggingFace checkpoints, not GGUF. So this cell is *not* apples-to-apples with A–D on weight quant. To make it fair, either (a) use bf16 across the board on vLLM and accept a memory-fit risk, or (b) drop vLLM from the matrix as "not GGUF-comparable." The vLLM cell exists to surface whether a different model format wins outright; if it's slower than llama.cpp at bf16, it's irrelevant.

## 6. Measurement methodology

Identical to the original spec:

- **Throughput:** `llama-bench -p 256 -n 128 -r 2` (engines A-D). For engine E (vLLM), use vLLM's built-in `benchmark_throughput.py` with equivalent prompt/gen sizes.
- **Latency:** 100 BFCL turns × {256-in / 128-out via `/v1/chat/completions`}, record p50 / p95 wall-clock from the harness.
- **Accuracy:** same 35-case BFCL subset (`harness/run_bfcl.py`, embedded test set in `harness/bfcl_subset.json`).
- **Memory:** `docker stats` peak RSS during harness run.
- **Quality regression check:** if any engine drops > 5 % overall_pass vs stock llama.cpp, flag as "trades accuracy for speed" rather than a clean win.

## 7. Success criteria

A new engine **wins** if **all three** hold:

1. **Throughput**: ≥ 1.5× stock llama.cpp's `gen_eval_tps` on the same model + quant (Qwen3.5-4B baseline = 9.79 tok/s → win threshold ≥ 14.7 tok/s).
2. **Accuracy**: BFCL `overall_pass` within 2 pp of stock llama.cpp (Qwen baseline = 91.4 % → win threshold ≥ 89.4 %).
3. **Setup cost**: builds + boots inside Docker on this host in < 20 min total, no host system changes.

If **none** of B-E hit (1), recommendation stays `stock llama.cpp` and the spec exits with a published negative result.

If **B (speculative)** hits (1) and (2): ship it. Lowest-risk path — it's just a flag.

If **C (OpenVINO)** or **D (ik_llama.cpp)** hits (1) and (2): evaluate ops cost (a different container image, slightly more update friction) vs the throughput win.

If **E (vLLM)** wins despite the format mismatch: investigate whether bf16-on-CPU is sustainable for our memory budget.

## 8. Results layout

```
results/
  qwen3.5-4b_stock.json           ← already published
  qwen3.5-4b_specdec.json
  qwen3.5-4b_openvino.json
  qwen3.5-4b_ikllama.json
  qwen3.5-4b_vllm.json
  (same naming for gemma-4-e4b_* and phi-4-mini_*)
  build-status-engine-bakeoff.json
  summary-bakeoff.md              ← decision-grade table for the article follow-up
docs/article-engines.md           ← new findings article (companion to docs/article.md)
```

The existing site's `/api/summary.json` auto-includes any new cells dropped into `results/`. The article follow-up gets its own page.

## 9. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OpenVINO backend GGUF conversion has bugs on Q4_K_M for Phi-4 / Gemma-4 | Medium | Phase 0 fails for engine C on those models | Smoke-test each model separately; document model coverage in the results JSON |
| Speculative draft (Qwen3.5-0.5B etc.) tokenizer drift from target | Low | Acceptance rate near zero → no speedup | Use **same model family** for draft+target; for Phi use n-gram lookup instead |
| vLLM CPU consumes too much RAM at bf16 for 4B model | Medium | engine E falls outside 12 GB cap | Drop bf16 to fp16 if supported on CPU; else flag vLLM as out-of-budget |
| Benchmark contention with prod tenants (load avg spike) | Low | inflated latencies | strict cgroup caps + off-peak window (same constraint as predecessor spec §8.3) |

## 10. Open questions

1. **Draft model availability for Gemma 4.** Confirm gemma-4-E2B-it has a clean Q4_K_M GGUF on HF (unsloth published the E4B one already).
2. **Phi-4 + speculative decoding?** Phi-4-mini's tool-calling is already broken under llama.cpp `--jinja` (see article §Phi anomaly). Worth running spec-dec on the workaround variant or skipping Phi for engine B.
3. **Approval for ik_llama.cpp fork.** It's by one of the core llama.cpp devs, but it's still a fork. Acceptable in this repo as a research engine; not necessarily an ops recommendation.
4. **vLLM cell — keep or drop?** It's apples-to-oranges (different model format). Could deliver the surprise upset or could just confuse the comparison. Default: keep, mark clearly as different baseline.

## 11. References

- [DeployBase 2026 inference engine comparison](https://deploybase.ai/articles/best-llm-inference-engine)
- [Intel Xeon 6 + vLLM CPU benchmark](https://community.intel.com/t5/Blogs/Tech-Innovation/Artificial-Intelligence-AI/Accelerating-vLLM-Inference-Intel-Xeon-6-Processor-Advantage/post/1717082)
- [OpenVINO lands in llama.cpp (Medium write-up, Apr 2026)](https://medium.com/openvino-toolkit/openvino-lands-in-llama-cpp-run-gguf-models-on-intel-cpu-gpu-and-npu-d6fca1d633e8)
- [llama.cpp OpenVINO backend docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENVINO.md)
- [ik_llama.cpp AVX2 CPU benchmark (discussion #164)](https://github.com/ikawrakow/ik_llama.cpp/discussions/164)
- [ik_llama.cpp repo](https://github.com/ikawrakow/ik_llama.cpp)
- [Speculative decoding in llama.cpp (DeepWiki §8.3)](https://deepwiki.com/ggml-org/llama.cpp/8.3-speculative-decoding)
- [PremAI: Speculative Decoding 2-3× faster, 2026 update](https://blog.premai.io/speculative-decoding-2-3x-faster-llm-inference-2026/)
- [Intel IPEX-LLM (archived Jan 2026)](https://github.com/intel/ipex-llm)
- [llamafile / tinyBLAS — upstreamed to llama.cpp](https://justine.lol/matmul/)
- [PowerInfer-2 paper (smartphone NPU/CPU sparse)](https://arxiv.org/abs/2406.06282)
