#!/usr/bin/env bash
# Run one benchmark cell end-to-end on the host.
# Usage: run_cell.sh <cell_id> <model_basename.gguf> <variant_image> <kv_mode>
#   <kv_mode> ∈ {fp16, turbo3}
set -euo pipefail

CELL_ID="${1:?cell_id required}"
MODEL_FILE="${2:?model basename required}"
IMAGE="${3:-ghcr.io/ggml-org/llama.cpp:full}"
KV_MODE="${4:-fp16}"

WORKDIR=/opt/llamabench
MODEL_PATH="/models/${MODEL_FILE}"
HOST_PORT=11434
CONTAINER_NAME="llamabench-${CELL_ID}"
RESULTS="${WORKDIR}/results/${CELL_ID}.json"
BENCH_JSON="${WORKDIR}/results/${CELL_ID}.bench.json"
LOG="${WORKDIR}/logs/${CELL_ID}.log"

mkdir -p "${WORKDIR}/results" "${WORKDIR}/logs"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
echo "[${CELL_ID}] image=${IMAGE} kv=${KV_MODE} model=${MODEL_FILE}"

KV_FLAGS=()
if [[ "${KV_MODE}" == "turbo3" ]]; then
  KV_FLAGS=(--cache-type-k turbo3 --cache-type-v turbo3)
elif [[ "${KV_MODE}" == "q8_0" ]]; then
  KV_FLAGS=(--cache-type-k q8_0 --cache-type-v q8_0)
fi

echo "[${CELL_ID}] starting llama-server..."
docker run -d --name "${CONTAINER_NAME}" \
  --cpus=4 --cpuset-cpus=8-11 --memory=12g --memory-swap=12g \
  -v "${WORKDIR}/models:/models:ro" \
  -p ${HOST_PORT}:8080 \
  --entrypoint /app/llama-server \
  "${IMAGE}" \
  --model "${MODEL_PATH}" \
  --threads 4 --threads-batch 4 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 256 \
  --jinja --host 0.0.0.0 --port 8080 \
  --reasoning off --reasoning-budget 0 \
  "${KV_FLAGS[@]}" \
  >>"${LOG}" 2>&1

echo "[${CELL_ID}] waiting for /health..."
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:${HOST_PORT}/health" >/dev/null 2>&1; then
    echo "[${CELL_ID}] server up after ${i}s"
    break
  fi
  sleep 1
  if [[ $i -eq 90 ]]; then
    echo "[${CELL_ID}] FAILED to come up; last 40 lines:"
    docker logs --tail 40 "${CONTAINER_NAME}" || true
    exit 1
  fi
done

echo "[${CELL_ID}] capturing peak RSS baseline..."
PEAK_RSS_KB=$(docker stats --no-stream --format '{{.MemUsage}}' "${CONTAINER_NAME}" | awk '{print $1}')

echo "[${CELL_ID}] running BFCL harness..."
python3 "${WORKDIR}/run_bfcl.py" \
  --endpoint "http://127.0.0.1:${HOST_PORT}/v1" \
  --model-id "${CELL_ID}" \
  --cell-id "${CELL_ID}" \
  --tests "${WORKDIR}/bfcl_subset.json" \
  --out "${RESULTS}.harness" \
  --max-tokens 192 --timeout 180

echo "[${CELL_ID}] capturing peak RSS after harness..."
PEAK_RSS_AFTER=$(docker stats --no-stream --format '{{.MemUsage}}' "${CONTAINER_NAME}" | awk '{print $1}')

echo "[${CELL_ID}] running llama-bench for tok/s..."
docker run --rm \
  --cpus=4 --cpuset-cpus=8-11 --memory=12g --memory-swap=12g \
  -v "${WORKDIR}/models:/models:ro" \
  --entrypoint /app/llama-bench \
  "${IMAGE}" \
  -m "${MODEL_PATH}" \
  -t 4 -p 256 -n 128 -r 2 \
  "${KV_FLAGS[@]}" \
  -o json \
  > "${BENCH_JSON}" 2>>"${LOG}" || echo "[${CELL_ID}] llama-bench WARN exit code $?"

cleanup

echo "[${CELL_ID}] merging results..."
python3 - <<PY
import json, os, re, statistics
cell_id = "${CELL_ID}"
results_dir = "${WORKDIR}/results"
harness_file = "${RESULTS}.harness"
bench_file   = "${BENCH_JSON}"
out_file     = "${RESULTS}"

with open(harness_file) as f:
    h = json.load(f)

prompt_tps = gen_tps = None
try:
    with open(bench_file) as f:
        b = json.load(f)
    pp, tg = [], []
    for run in b:
        n_prompt = run.get("n_prompt") or 0
        n_gen    = run.get("n_gen") or 0
        ts       = run.get("avg_ts") or run.get("tokens_per_second")
        if ts is None:
            continue
        if n_prompt and not n_gen:
            pp.append(float(ts))
        elif n_gen and not n_prompt:
            tg.append(float(ts))
    prompt_tps = round(statistics.fmean(pp), 2) if pp else None
    gen_tps    = round(statistics.fmean(tg), 2) if tg else None
except Exception as exc:
    print("  bench parse failed:", exc)

merged = {
    "cell_id": cell_id,
    "model_id": h["model_id"],
    "weight_quant": "Q4_K_M",
    "kv_quant": "${KV_MODE}",
    "llamacpp_variant": "${IMAGE}",
    "host": "deemwar-prod-app-1",
    "throughput": {
        "prompt_eval_tps": prompt_tps,
        "gen_eval_tps": gen_tps,
    },
    "memory": {
        "peak_rss_str": "${PEAK_RSS_AFTER}",
    },
    "latency_ms": h["latency_ms"],
    "tool_calling": h["tool_calling"],
    "by_category": h["by_category"],
    "n_cases": h["n_cases"],
    "started_at": h["started_at"],
    "duration_sec": h["duration_sec"],
}
with open(out_file, "w") as f:
    json.dump(merged, f, indent=2)
print(f"  wrote {out_file}")
print(f"  → gen_tps={gen_tps} prompt_tps={prompt_tps} tool_overall={h['tool_calling']['overall_pass']}%")
PY

echo "[${CELL_ID}] DONE"
