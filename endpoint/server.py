"""
Tiny HTTP endpoint serving per-cell llama.cpp benchmark results.

Reads JSON files from /results (mounted into the container) and exposes:

    GET /             -> health + list of cell ids
    GET /healthz      -> {"ok": true}
    GET /results      -> aggregated summary across all cells
    GET /results/{id} -> single cell document

Stdlib only. No FastAPI / Flask. Runs in any python:3.11-slim container.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

RESULTS_DIR = os.environ.get("RESULTS_DIR", "/results")
PORT = int(os.environ.get("PORT", "8765"))
HOST_LABEL = os.environ.get("HOST_LABEL", "shared-cpu-host")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def load_cells() -> list[dict]:
    cells: list[dict] = []
    if not os.path.isdir(RESULTS_DIR):
        return cells
    for name in sorted(os.listdir(RESULTS_DIR)):
        if not name.endswith(".json"):
            continue
        if name in {"summary.json", "results.json"} or name.endswith(".harness") or name.endswith(".bench.json"):
            continue
        path = os.path.join(RESULTS_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                cells.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    return cells


def build_summary(cells: list[dict]) -> dict:
    def row(c: dict) -> dict:
        return {
            "cell_id": c.get("cell_id"),
            "model_id": c.get("model_id"),
            "weight_quant": c.get("weight_quant"),
            "kv_quant": c.get("kv_quant"),
            "gen_eval_tps": (c.get("throughput") or {}).get("gen_eval_tps"),
            "prompt_eval_tps": (c.get("throughput") or {}).get("prompt_eval_tps"),
            "p50_ms": (c.get("latency_ms") or {}).get("p50"),
            "p95_ms": (c.get("latency_ms") or {}).get("p95"),
            "overall_pass": (c.get("tool_calling") or {}).get("overall_pass"),
            "format_pass_rate": (c.get("tool_calling") or {}).get("format_pass_rate"),
            "n_cases": c.get("n_cases"),
        }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": HOST_LABEL,
        "n_cells": len(cells),
        "cells": [row(c) for c in cells],
        "full": cells,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict | list) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"

        if path == "/healthz":
            return self._send_json(200, {"ok": True})

        if path == "/":
            cells = load_cells()
            ids = [c.get("cell_id") for c in cells]
            return self._send_json(
                200,
                {
                    "service": "llama-local-benchmarks",
                    "host": HOST_LABEL,
                    "endpoints": ["/results", "/results/<cell_id>", "/healthz"],
                    "available_cell_ids": ids,
                },
            )

        if path == "/results":
            return self._send_json(200, build_summary(load_cells()))

        if path.startswith("/results/"):
            cell_id = path[len("/results/") :]
            for c in load_cells():
                if c.get("cell_id") == cell_id:
                    return self._send_json(200, c)
            return self._send_json(404, {"error": "cell not found", "cell_id": cell_id})

        return self._send_json(404, {"error": "not found", "path": path})

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"serving results from {RESULTS_DIR} on :{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
