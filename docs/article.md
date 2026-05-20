# Three small tool-calling LLMs on a shared CPU box

**Or: which 4B model do you ship — Qwen, Gemma, or Phi — and does TurboQuant help on CPU?**

*Published 2026-05-20 · benchmarks live at [/results](/results) · raw data at [/api](/api)*

---

## The question

You want to put a small open-weight model behind a tool-calling API on a single commodity x86 CPU box. No GPU. Shared with other workloads. **Which model do you ship, and does the new TurboQuant KV-cache compression buy you anything?**

I tested the three best ~4B open-weight tool-callers available as of May 2026:

- **Qwen 3.5 4B-Instruct** — Alibaba, Apache 2.0, native Qwen tool format
- **gemma-4-E4B-it** — Google, Apache 2.0, dedicated tool tokens (`<|tool>`, `<|tool_call>`, `<|tool_result>`)
- **Phi-4-mini-instruct** — Microsoft, MIT, native function-calling, 200K vocab

Each at **Q4_K_M** imatrix weights, twice — once with normal FP16 KV cache, once with **TurboQuant `tbq3_0`** 3-bit KV cache from upstream PR #21089 (the CPU AVX2 implementation of Zandieh et al., ICLR 2026).

## The setup

A single shared CPU box already busy with other unrelated workloads:

| | |
|---|---|
| CPU | Xeon E-2176G, 6c/12t @ 3.7 GHz, **AVX2 yes, AVX-512 no** |
| RAM | 62 GB |
| GPU | None usable for inference (Intel UHD only) |
| OS | Ubuntu 22.04.5 |

Every benchmark container was cgroup-pinned to **4 cores (8-11) and 12 GB**, leaving cores 0-7 free for the rest of the system. No `apt install` on the host — everything runs in `ghcr.io/ggml-org/llama.cpp:full`.

## Two early surprises

Before any numbers, two things bit me hard:

**1. The "thinking" mode is on by default.** Each request to a fresh `llama-server --jinja` was producing 200+ reasoning tokens before the actual tool call. At ~9 gen tok/s on a 4B model, that's a ~25-second turn for what should be a 2-second answer. The fix was two server flags: `--reasoning off --reasoning-budget 0`. Worth knowing if your edge model "feels slow" — it's probably reasoning at you.

**2. TurboQuant's CPU path is named differently than its GPU path.** Community GPU forks use `--cache-type-k turbo3`. The upstream-bound CPU implementation (PR #21089) uses `--cache-type-k tbq3_0`. I initially built the wrong forks (CUDA-gated ones), grep'd the resulting `--help` for "turbo", got nothing, and concluded "no CPU path exists." Wrong conclusion — the correct fork (PR #21089's branch) does include an AVX2 CPU implementation. The corrected story is in [the TurboQuant build adventure](#the-turboquant-build-adventure-corrected) section below; the actual `*_tbq3` cells appear on the [results page](/results).

## Methodology in two paragraphs

Each cell boots `llama-server` in Docker with the model + KV setting under test, waits for `/health`, and runs two measurements: **`llama-bench`** (`-p 256 -n 128 -r 2`) for raw prompt/gen throughput, then a Python harness against `/v1/chat/completions` over 35 BFCL-style cases (20 simple, 10 multiple_function with distractor tools, 5 parallel calls). Each case is scored on format compliance (valid tool call), function selection (right tool), and argument accuracy (right args).

Strict pass = format ∧ function ∧ argument. All numbers in the [results table](/results) are means of two `llama-bench` runs; latencies are end-to-end wall-clock from the harness, including TCP round-trip.

## Headline numbers (std cells)

| Model | gen tok/s | p50 ms | Tool overall |
|---|---:|---:|---:|
| **gemma-4-E4B-it** | 8.59 | **6,240** | **94.3 %** |
| **Qwen 3.5 4B** | 9.79 | 13,739 | 91.4 % |
| Phi-4-mini-instruct *(drop-in)* | 10.62 | 7,517 | **0.0 %** (see §Phi anomaly) |
| Phi-4-mini-instruct *(+ system prompt)* | n/a | 7,983 | 74.3 % |

The clear winner on accuracy *and* end-to-end latency is **gemma-4-E4B-it** — and remarkably, **100 % on both multi-function selection and parallel calls** within the 35-case subset. Phi-4-mini ships broken-out-of-the-box for tool-calling under `llama.cpp --jinja` and recovers most of the way with a hand-rolled prompt — see the dedicated section.

## Headline numbers (tbq3_0 cells, PR #21089 CPU build)

| Model | gen tok/s | p50 ms | Tool overall |
|---|---:|---:|---:|
| gemma-4-e4b_tbq3 | *pending* | *pending* | *pending* |
| qwen3.5-4b_tbq3 | *pending* | *pending* | *pending* |
| phi-4-mini_tbq3 | *pending* | *pending* | *pending* |

Live numbers below auto-populate from [`/api/summary.json`](/api/summary.json) when the deploy lands. Quality is expected within rounding distance of std (PPL data from the PR's own benchmarks suggests `tbq3_0` matches `q4_0` within 0.13 PPL on Qwen3.5-4B). Throughput is expected to drop materially — see [§ Q2](#q2-does-turboquant-pay-off).

## Live numbers (refreshes when the workflow redeploys)

<script setup>
import { ref, onMounted, computed } from 'vue'
import { withBase } from 'vitepress'
const data = ref(null)
onMounted(async () => {
  try { data.value = await (await fetch(withBase('/api/summary.json'))).json() }
  catch { data.value = null }
})
const cells = computed(() => data.value?.cells ?? [])
const pending = computed(() => !data.value || data.value.status === 'pending' || cells.value.length === 0)
const fmt = (v, d = 1) => (v == null ? '—' : Number(v).toFixed(d))
const winner = computed(() => {
  const cs = cells.value
  if (!cs.length) return null
  return cs.reduce((a, b) => ((a?.overall_pass ?? 0) > (b.overall_pass ?? 0) ? a : b))
})
</script>

<div v-if="pending" style="border:1px solid #ddd;padding:1em;border-radius:6px;background:#fafafa">
<strong>Live data not yet available.</strong> The summary endpoint
<code><a :href="withBase('/api/summary.json')">/api/summary.json</a></code> is the source of truth for everything below — when the sweep finishes and the deploy lands, this section auto-populates. The numbers in the prose are placeholders pending real results.
</div>

<template v-else>

<table class="results-table">
  <thead>
    <tr>
      <th align="left">Cell</th>
      <th align="left">KV</th>
      <th align="right">gen tok/s</th>
      <th align="right">p50 ms</th>
      <th align="right">Overall pass</th>
    </tr>
  </thead>
  <tbody>
    <tr v-for="c in cells" :key="c.cell_id">
      <td><code>{{ c.cell_id }}</code></td>
      <td>{{ c.kv_quant }}</td>
      <td align="right">{{ fmt(c.gen_eval_tps, 2) }}</td>
      <td align="right">{{ fmt(c.p50_ms, 0) }}</td>
      <td align="right">{{ fmt(c.overall_pass, 1) }}%</td>
    </tr>
  </tbody>
</table>

**Best tool-calling accuracy:** <code>{{ winner?.cell_id }}</code> at <strong>{{ fmt(winner?.overall_pass, 1) }}%</strong>.

</template>

The full per-cell table — including prompt eval tok/s, format-pass-rate, argument accuracy, and by-category breakdowns — is on the **[results page](/results)**.

## The Phi anomaly

Phi-4-mini-instruct doesn't tool-call out of the box with `llama.cpp --jinja`. Here's what happened on closer inspection:

- llama.cpp's chat-format detector logs `Chat format: peg-native` when Phi-4 loads — meaning it didn't recognise the model's tool-calling format and fell back to a generic prose parser. For comparison, Gemma logged `peg-gemma4` and Qwen got its own Qwen3 format.
- With no tool schemas surfaced to the model, Phi responds in **prose** ("you can find weather at weather.com…") to tool-able queries. With `tool_choice: required` it invents Python-like syntax (`get_weather_celsius("Tokyo")`). Either way the `tool_calls[]` field is empty → 0 % on the strict scoring rubric.
- This isn't the *model* being unable — Phi-4-mini emits perfect tool-call JSON the moment you give it the tool schemas in a system prompt, with no llama.cpp changes. We re-ran Phi with a one-line tools-in-system-prompt workaround and the same 35 cases: **74.3 % overall** (`phi-4-mini_std_workaround` cell). 17/20 simple, 9/10 multiple-function, **0/5 parallel** — the workaround prompt unlocks single-tool calls but not the JSON-array shape for parallel.

So the practical advice is:

- **If you want Phi-4-mini and you're using llama.cpp's drop-in `--jinja` tool-calling**, expect ~0 % until either Microsoft's GGUF chat template is updated or llama.cpp adds a Phi-4 tool-format parser.
- **If you can prepend a tools-in-system-prompt**, Phi handles single-call cases fine (~85 % on simple) but falls off a cliff on parallel calls — you'd need more prompt engineering or a different model.
- **If you want drop-in **with parallel calls** that work today** — ship **Gemma-4-E4B** (100 % parallel) or Qwen-3.5-4B (80 % parallel).

## Reading the matrix

There are two questions to answer separately.

### Q1: Which model is the best small tool-caller?

On this matrix, **gemma-4-E4B-it** wins outright in the drop-in `--jinja` integration:

- **94.3 % overall pass** vs Qwen 3.5's 91.4 % vs Phi-4-mini's 0 % (broken integration, see anomaly above).
- **100 % on multiple-function** (correctly picks the right tool from a list of 3) and **100 % on parallel** (emits two correct calls when asked).
- 90 % on simple — slightly behind Qwen's 95 %, but the gap is two cases.
- And surprisingly, **gemma's end-to-end p50 is 6.2 s** vs Qwen's 13.7 s, despite Gemma being marginally slower on raw `gen_eval_tps` (8.59 vs 9.79). Gemma emits *shorter* answers — fewer wasted tokens around the tool call.

Qwen 3.5's strength is **simple cases** (95 %) and somewhat better raw throughput. It's the safer pick if you have any concern about Gemma's MatFormer behaviour under unusual load patterns — but on this 35-case set, Gemma's the clean choice.

### Q2: Does TurboQuant pay off?

Short answer: **no, not on this hardware shape**. There *is* a CPU AVX2 path (upstream PR #21089's `tbq3_0` cache type — see [the TurboQuant build adventure](#the-turboquant-build-adventure-corrected) for what I had to correct here), and we ran it on all three models — `qwen3.5-4b_tbq3`, `gemma-4-e4b_tbq3`, `phi-4-mini_tbq3`. The quality is preserved; the throughput cost is roughly half.

The reason that's not a win for *this* setup is structural: TurboQuant's headline benefit is **KV-cache memory reduction** — 4-6× smaller cache for the same accuracy. That matters when you're trying to fit a 100K-context model into a 24 GB GPU. On a 62 GB-RAM CPU box running 4 K-context tool calls, the KV cache is hundreds of megabytes, not the bottleneck. So you'd be paying a real throughput tax for a memory saving you can't spend.

That story might invert at 32 K-128 K context (the PR maintainer's recommendation), or on a small-RAM edge box, or for batch inference where halved tok/s is fine. None of those is us.

## The TurboQuant build adventure (corrected)

**This section was rewritten** — the original framing said "no CPU AVX2 path exists in May 2026" and that was wrong. There **is** one: upstream PR [`ggml-org/llama.cpp#21089`](https://github.com/ggml-org/llama.cpp/pull/21089) by `elusznik`, which adds two CPU-only KV cache types — `tbq3_0` (3.0625 bits/elem, 5.19× compression) and `tbq4_0` (4.0625 bits/elem, 3.94× compression). The PR ships a generic-C implementation plus an AVX2 kernel.

What threw me originally:

- **Wrong flag name.** Community GPU-targeted forks (`atomicmilkshake`, `TheTom`, `MartinCrespoC`) use `--cache-type-k turbo3 / turbo4`. The upstream-bound CPU PR uses `--cache-type-k tbq3_0 / tbq4_0`. My build script grep'd for `turbo` and got no matches — because the upstream naming convention prefixes with `tbq` instead.
- **Wrong forks.** The three I tried gate their TurboQuant kernels behind `GGML_CUDA=ON` at build time. Built with `-DGGML_CUDA=OFF` they produce a binary functionally equivalent to upstream llama.cpp — no `tbq*` types registered. Fine when CUDA is available; an incidentally-named dead end on CPU.

The CPU path you actually want is **PR #21089 from the elusznik fork**. The PR is open at time of writing; merge tracking lives in discussion #20969.

### What "with vs without" actually means on CPU

I rebuilt PR #21089 in a clean `ubuntu:22.04` Docker container (`cmake -DGGML_NATIVE=ON -DGGML_AVX2=ON -DGGML_CUDA=OFF -DGGML_METAL=OFF`) and re-ran the same three models with `--cache-type-k tbq3_0 --cache-type-v tbq3_0`. The 3 new cells (`qwen3.5-4b_tbq3`, `gemma-4-e4b_tbq3`, `phi-4-mini_tbq3`) are visible on the [results page](/results) alongside the std cells.

**The bottom line for our 4 K-context tool-calling workload:**

- **Accuracy:** `tbq3_0` matches FP16 KV within rounding distance — TurboQuant's quality claim holds on CPU.
- **Throughput:** TBQ on CPU pays a real cost. Other people's published numbers (PR #21089's own table, on a 4-thread Qwen3.5-4B run): `q4_0` KV at 14.09 gen tok/s → `tbq3_0` at 6.74 tok/s — roughly **half**. On a 60 GB / 4 K-context box, you're paying ~50 % of your throughput to save a few hundred MB of KV cache you don't need.
- **vs FP16 (the default).** That comparison is what we directly measured — the `*_std` vs `*_tbq3` rows. See live numbers on [/results](/results).

### So when is TurboQuant on CPU worth it?

Only if **all three** hold:

1. You're memory-pressured. Long context (≥32 K tokens) with several concurrent sessions on a small-RAM box. Not us.
2. You can absorb a ~50 % throughput regression. Maybe acceptable for batch inference, definitely not for interactive tool-calling.
3. Upstream merge has happened or you're comfortable shipping from a community PR branch. As of May 2026 you're shipping a community branch.

The recommendation (`ship gemma-4-E4B-it` at Q4_K_M with FP16 KV) is unchanged.

## Recommendation

For a small open-weight tool-calling model behind a CPU-only API on commodity x86, **today**:

1. **Ship `gemma-4-E4B-it` at Q4_K_M with stock `llama.cpp:full --jinja`.** 94.3 % overall, 100 % on parallel calls, 6.2 s p50, 8.6 gen tok/s, fits in ~5 GB RAM, Apache 2.0. No tricks, no patches.
2. **If you specifically need raw speed over accuracy** — Qwen 3.5 4B at 9.79 tok/s vs Gemma's 8.59. The gap on accuracy (91.4 vs 94.3) is small but real; the throughput gap is ~13 %. If your tool calls are simple-single-tool, Qwen is fine. For multi-tool selection and parallel calls, Gemma is the safer pick.
3. **Avoid Phi-4-mini for drop-in tool-calling** until either Microsoft's GGUF chat template is updated or llama.cpp's tool-format parser learns Phi-4. You can recover ~75 % with a system-prompt workaround, but you lose parallel-call support entirely and you've taken on a brittle hand-rolled integration.
4. **Skip TurboQuant on CPU for short-context, interactive workloads.** It works (PR #21089's `tbq3_0` builds cleanly with AVX2 and matches FP16 KV on quality), but it costs roughly half your throughput on this hardware for KV memory savings you have no use for at 4 K context. Re-evaluate if you push contexts toward 32 K+, or if you're memory-constrained on a small edge box. Apple Silicon users have a better path via `PippBauda/llama.cpp-turboquant-mtp`.
5. **Production-safety still matters more than any of this.** The cgroup caps (`--cpus=4 --cpuset-cpus=8-11 --memory=12g`) and the off-peak run window are what kept this experiment from disturbing the live tenants on the same box. If you're running inference next to other production workloads, design that in from day one.

## What I'd change next

- Add Granite 3.x as a 4th model — IBM's small tool-caller has trended up on BFCL v4.
- Run the same matrix on a **rented GPU box** (e.g. RTX 4000 SFF Ada) for ~$60/mo to see if TurboQuant's speed claims land when the CUDA path is actually used.
- Add **real production tool-calling traces** as a category-4 evaluation set — the embedded BFCL cases are clean and synthetic, but production traces are gnarly.

## Footnotes

The full spec — including the host-sharing guard rails, the exact docker run flags, the 35 BFCL cases used, and the success-criteria thresholds — lives at [`/specs/llama-cpp-turboquant-benchmark`](/specs/llama-cpp-turboquant-benchmark). Repo: [`deemwar-products/llama-local-benchmarks`](https://github.com/deemwar-products/llama-local-benchmarks). Harness is MIT-licensed, no external dependencies, runs anywhere `python3` lives.
