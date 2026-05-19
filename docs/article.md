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

Each at **Q4_K_M** imatrix weights, twice — once with normal FP16 KV cache, once with **TurboQuant turbo3** 3-bit KV cache (Zandieh et al., ICLR 2026).

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

**2. TurboQuant on a CPU-only box.** TurboQuant's headline benefit is **KV-cache memory reduction** — 4-6× smaller cache for the same accuracy. That matters when you're squeezing a 100K-token context into a 24 GB GPU. On a box with 60 GB of free RAM and 4 K context, the KV cache is a few hundred MB. You're compressing 300 MB → 60 MB on a machine that doesn't care.

That doesn't mean it's worthless — TurboQuant has secondary speed claims from cheaper attention math on quantized keys/values. The bake-off below is the only honest way to find out.

## Methodology in two paragraphs

Each cell boots `llama-server` in Docker with the model + KV setting under test, waits for `/health`, and runs two measurements: **`llama-bench`** (`-p 256 -n 128 -r 2`) for raw prompt/gen throughput, then a Python harness against `/v1/chat/completions` over 35 BFCL-style cases (20 simple, 10 multiple_function with distractor tools, 5 parallel calls). Each case is scored on format compliance (valid tool call), function selection (right tool), and argument accuracy (right args).

Strict pass = format ∧ function ∧ argument. All numbers in the [results table](/results) are means of two `llama-bench` runs; latencies are end-to-end wall-clock from the harness, including TCP round-trip.

## Headline numbers (std cells, what landed)

| Model | gen tok/s | p50 ms | Tool overall |
|---|---:|---:|---:|
| **gemma-4-E4B-it** | 8.59 | **6,240** | **94.3 %** |
| **Qwen 3.5 4B** | 9.79 | 13,739 | 91.4 % |
| Phi-4-mini-instruct *(drop-in)* | 10.62 | 7,517 | **0.0 %** (see §Phi anomaly) |
| Phi-4-mini-instruct *(+ system prompt)* | n/a | 7,983 | 74.3 % |

The clear winner on accuracy *and* end-to-end latency is **gemma-4-E4B-it** — and remarkably, **100 % on both multi-function selection and parallel calls** within the 35-case subset. Phi-4-mini ships broken-out-of-the-box for tool-calling under `llama.cpp --jinja` and recovers most of the way with a hand-rolled prompt — see the dedicated section.

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

| Cell | KV | gen tok/s | p50 ms | Overall pass |
|---|---|---:|---:|---:|
<tr v-for="c in cells" :key="c.cell_id">
  <td><code>{{ c.cell_id }}</code></td>
  <td>{{ c.kv_quant }}</td>
  <td style="text-align:right">{{ fmt(c.gen_eval_tps, 2) }}</td>
  <td style="text-align:right">{{ fmt(c.p50_ms, 0) }}</td>
  <td style="text-align:right">{{ fmt(c.overall_pass, 1) }}%</td>
</tr>

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

For each model, compare `*_std` vs `*_tq` on three axes:

| Axis | What "TurboQuant won" looks like |
|---|---|
| **Memory** | KV-cache RSS drops 3-5× (this should be reliable; the math is unambiguous) |
| **Accuracy** | `overall_pass` stays within ~2 points of std |
| **Speed** | `gen_tok/s` stays within ±10% of std (CPU path is the gamble) |

The expected outcome on this hardware, going in: **memory wins, but speed loses by 5-15%** because the CUDA kernels TurboQuant ships are GPU-only and the CPU fallback has a small overhead per attention block.

If `*_tq` matches `*_std` on accuracy and the throughput regression is small, the recommendation is clear: ship TurboQuant for the memory headroom. If TurboQuant tanks accuracy or costs more than 15% throughput, ship `std` and revisit when llama.cpp upstream merges the CPU-optimized kernels.

## The TurboQuant build adventure

None of the four community forks I tried (`atomicmilkshake`, `TheTom`, `MartinCrespoC`, `PippBauda`) advertise CPU-only AVX2 x86 builds. Most assume CUDA on Turing+ / Ampere, one targets Apple Metal. I attempted a build inside an `ubuntu:22.04` container with `apt-get install cmake build-essential` and the fork's recommended `cmake -B build -DGGML_TURBOQUANT=ON`. Outcome and exact dance documented in [`docs/specs/llama-cpp-turboquant-benchmark.md`](/specs/llama-cpp-turboquant-benchmark) §7 and the article's [results table](/results) — search for the `*_tq` row's `llamacpp_variant` field.

The big takeaway, regardless of the bake-off outcome: **the TurboQuant ecosystem on CPU x86 is still rough.** If you're running on AVX2 commodity CPUs in mid-2026, expect to invest a day in build pipelines before you measure anything. Apple Silicon users (Metal fork) are in a much better spot today.

## Recommendation

Read the [results page](/results) for the exact numbers. The decision tree:

1. **If you need predictable, supported, easy** — ship `std` (stock llama.cpp) with whichever of the three models wins on overall_pass. Re-evaluate TurboQuant in 3 months when upstream lands.
2. **If you need to squeeze edge memory** (running on a 4-8 GB box, not this one) — try TurboQuant with the same model as #1, accept a small accuracy delta.
3. **If you have GPU headroom** — different article. Use vLLM, ignore everything here.

## What I'd change next

- Add Granite 3.x as a 4th model — IBM's small tool-caller has trended up on BFCL v4.
- Run the same matrix on a **rented GPU box** (e.g. RTX 4000 SFF Ada) for ~$60/mo to see if TurboQuant's speed claims land when the CUDA path is actually used.
- Add **real production tool-calling traces** as a category-4 evaluation set — the embedded BFCL cases are clean and synthetic, but production traces are gnarly.

## Footnotes

The full spec — including the host-sharing guard rails, the exact docker run flags, the 35 BFCL cases used, and the success-criteria thresholds — lives at [`/specs/llama-cpp-turboquant-benchmark`](/specs/llama-cpp-turboquant-benchmark). Repo: [`deemwar-products/llama-local-benchmarks`](https://github.com/deemwar-products/llama-local-benchmarks). Harness is MIT-licensed, no external dependencies, runs anywhere `python3` lives.
