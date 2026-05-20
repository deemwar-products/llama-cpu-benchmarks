# HTTP API

The same per-cell data the [results table](/results) and [article](/article) cite is available as plain JSON over HTTP, served by GitHub Pages alongside this site.

## Endpoints

| Path | Description |
|---|---|
| [`/api/summary.json`](/api/summary.json) | Aggregated table of all cells |
| [`/api/results.json`](/api/results.json) | Alias for `summary.json` |
| `/api/cells/{cell_id}.json` | Per-cell raw result with full BFCL trace |

Standard cells: `qwen3.5-4b_std`, `qwen3.5-4b_tbq3`, `gemma-4-e4b_std`, `gemma-4-e4b_tbq3`, `phi-4-mini_std`, `phi-4-mini_std_workaround`, `phi-4-mini_tbq3`.

CORS: `Access-Control-Allow-Origin: *`.

## Example

```bash
curl -s https://deemwar-products.github.io/llama-cpu-benchmarks/api/summary.json \
  | jq '.cells[] | {id: .cell_id, tps: .gen_eval_tps, tool: .overall_pass}'
```

## Schema

Each cell document:

```ts
type Cell = {
  cell_id: string
  model_id: string
  weight_quant: 'Q4_K_M'
  kv_quant: 'fp16' | 'tbq3_0' | 'tbq4_0'
  llamacpp_variant: string  // image tag or PR/fork SHA
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

If you check out the repo and run the harness yourself, the per-cell JSONs land in `results/` and you can serve them with the stdlib `endpoint/` service (`docker build -t llamabench-endpoint endpoint/ && docker run …`). Useful for live re-runs that should update without redeploying the static site. Source: [`endpoint/`](https://github.com/deemwar-products/llama-cpu-benchmarks/tree/main/endpoint).
