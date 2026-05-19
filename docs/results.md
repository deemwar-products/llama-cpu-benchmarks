# Results

<script setup>
import { ref, onMounted, computed } from 'vue'
import { withBase } from 'vitepress'

const data = ref(null)
const err = ref(null)

onMounted(async () => {
  try {
    const res = await fetch(withBase('/api/summary.json'))
    if (!res.ok) throw new Error('HTTP ' + res.status)
    data.value = await res.json()
  } catch (e) {
    err.value = String(e)
  }
})

const cells = computed(() => data.value?.cells ?? [])
const generated = computed(() => data.value?.generated_at ?? null)
const pending = computed(() => data.value?.status === 'pending' || cells.value.length === 0)
const fmt = (v, d = 1) => (v == null ? '—' : Number(v).toFixed(d))
</script>

<div v-if="err" style="border:1px solid #f88;padding:1em;border-radius:6px;background:#fff5f5;color:#900;">
  Failed to load results: <code>{{ err }}</code>
</div>

<div v-else-if="pending" style="border:1px solid #ccc;padding:1em;border-radius:6px;background:#fafafa;">
  <strong>No results yet.</strong> The benchmark sweep hasn't landed in <code>docs/public/api/summary.json</code>.
  Run the sweep on <code>prod-app-1</code> and push to <code>main</code> — the CI will redeploy this page.
</div>

<template v-else>

Generated **{{ generated }}** · host **deemwar-prod-app-1** · {{ cells.length }} cells

| Cell | Model | KV | gen tok/s | prompt tok/s | p50 ms | p95 ms | Tool overall | Format pass |
|---|---|---|---:|---:|---:|---:|---:|---:|
<tr v-for="c in cells" :key="c.cell_id">
  <td><code>{{ c.cell_id }}</code></td>
  <td>{{ c.model_id }}</td>
  <td>{{ c.kv_quant }}</td>
  <td style="text-align:right">{{ fmt(c.gen_eval_tps, 2) }}</td>
  <td style="text-align:right">{{ fmt(c.prompt_eval_tps, 2) }}</td>
  <td style="text-align:right">{{ fmt(c.p50_ms, 0) }}</td>
  <td style="text-align:right">{{ fmt(c.p95_ms, 0) }}</td>
  <td style="text-align:right">{{ fmt(c.overall_pass, 1) }}%</td>
  <td style="text-align:right">{{ fmt(c.format_pass_rate, 1) }}%</td>
</tr>

</template>

## Reading the columns

- **gen tok/s** — generation throughput from `llama-bench` (`-n 128 -r 2`, mean).
- **prompt tok/s** — prompt-eval throughput from `llama-bench` (`-p 256 -r 2`, mean).
- **p50 / p95 ms** — end-to-end wall-clock per BFCL turn, including network round-trip.
- **Tool overall** — strict pass: valid JSON ∧ correct function ∧ all expected arguments present and equal.
- **Format pass** — strict pass on JSON / tool-call shape only (regardless of correctness).

## Raw JSON

Programmatic access at [`/api/summary.json`](/api/summary.json) and `/api/cells/{cell_id}.json`. See the [API page](/api) for the schema.
