# HTTP API

The same per-cell data the [results table](/results) and [article](/article) cite is available as plain JSON over HTTP, served by GitHub Pages alongside this site.

## Endpoints

| Path | Description |
|---|---|
| [`/api/summary.json`](/api/summary.json) | Aggregated table of all 6 cells |
| [`/api/results.json`](/api/results.json) | Alias for `summary.json` |
| `/api/cells/{cell_id}.json` | Per-cell raw result with full BFCL trace |

Cell IDs: `qwen3.5-4b_std`, `qwen3.5-4b_tq`, `gemma-4-e4b_std`, `gemma-4-e4b_tq`, `phi-4-mini_std`, `phi-4-mini_tq`.

CORS: `Access-Control-Allow-Origin: *`.

## Example

```bash
curl -s https://deemwar-products.github.io/llama-local-benchmarks/api/summary.json \
  | jq '.cells[] | {id: .cell_id, tps: .gen_eval_tps, tool: .overall_pass}'
```

```json
{ "id": "qwen3.5-4b_std", "tps": 9.17, "tool": 91.4 }
{ "id": "qwen3.5-4b_tq", "tps": 8.9, "tool": 90.0 }
...
```

## Schema

Each cell document:

```ts
type Cell = {
  cell_id: string
  model_id: string
  weight_quant: 'Q4_K_M'
  kv_quant: 'fp16' | 'turbo3'
  llamacpp_variant: string  // image tag or fork SHA
  throughput: { prompt_eval_tps: number; gen_eval_tps: number }
  memory:    { peak_rss_str: string }
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

## Optional local mirror

If you check out the repo and run the harness yourself, the per-cell JSONs land in `results/` and you can serve them with the stdlib `endpoint/` service (`docker build -t llamabench-endpoint endpoint/ && docker run …`). Useful for live re-runs that should update without redeploying the static site. Source: [`endpoint/`](https://github.com/deemwar-products/llama-local-benchmarks/tree/main/endpoint).
