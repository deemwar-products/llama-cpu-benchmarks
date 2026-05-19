# HTTP API

The same per-cell data the [results table](/results) and [article](/article) cite is available as plain JSON over HTTP — both as static endpoints on this site (always available, served by GitHub Pages) and as a live FastAPI service on `prod-app-1` (refreshes when re-runs land, see [`endpoint/`](https://github.com/deemwar-products/llama-local-benchmarks/tree/main/endpoint) for the source).

## Static (this site)

| Path | Description |
|---|---|
| [`/api/summary.json`](/api/summary.json) | Aggregated table of all 6 cells |
| [`/api/results.json`](/api/results.json) | Alias for `summary.json` |
| [`/api/cells/{cell_id}.json`](/api/cells/) | Per-cell raw result with full BFCL trace |

Cell IDs: `qwen3.5-4b_std`, `qwen3.5-4b_tq`, `gemma-4-e4b_std`, `gemma-4-e4b_tq`, `phi-4-mini_std`, `phi-4-mini_tq`.

## Live service (prod-app-1)

```
http://<llama-bench-host>/results
http://<llama-bench-host>/results/{cell_id}
http://<llama-bench-host>/healthz
```

URL printed in the [morning handoff](https://github.com/deemwar-products/llama-local-benchmarks/blob/main/HANDOFF.md) and pinned to the repo README on each run.

## Example

```bash
curl -s https://deemwar-products.github.io/llama-local-benchmarks/api/summary.json | jq '.cells[] | {id: .cell_id, tps: .throughput.gen_eval_tps, tool: .tool_calling.overall_pass}'
```

```json
{ "id": "qwen3.5-4b_std", "tps": 18.4, "tool": 78.0 }
{ "id": "qwen3.5-4b_tq", "tps": 17.9, "tool": 77.0 }
...
```

## Schema

Each cell document:

```ts
type Cell = {
  cell_id: string
  model: string
  weight_quant: 'Q4_K_M'
  kv_quant: 'fp16' | 'turbo3'
  llamacpp_variant: string
  host: 'deemwar-prod-app-1'
  throughput: { prompt_eval_tps: number; gen_eval_tps: number }
  memory:    { peak_rss_mb: number;     kv_cache_rss_mb: number }
  latency_ms: { p50: number; p95: number; mean: number }
  tool_calling: {
    format_pass_rate: number
    function_accuracy: number
    argument_accuracy: number
    overall_pass: number
    n_cases: number
  }
  by_category: Record<'simple' | 'parallel' | 'multiple_function', { n: number; overall_pass: number }>
  started_at: string  // ISO-8601 UTC
  duration_sec: number
}
```
