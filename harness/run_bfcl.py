#!/usr/bin/env python3
"""
BFCL-style tool-calling harness for llama.cpp / llama-server.

Talks to a running llama-server over its OpenAI-compatible /v1/chat/completions
endpoint with tools=[...], scores each test case on format / function / argument
accuracy, and writes a single results JSON.

Designed to run *inside* the llama-server's network, or against a forwarded port.

Usage:
    python3 run_bfcl.py \\
        --endpoint http://127.0.0.1:11434/v1 \\
        --model-id qwen3.5-4b \\
        --cell-id qwen3.5-4b_std \\
        --tests harness/bfcl_subset.json \\
        --out results/qwen3.5-4b_std.json

No third-party deps required — uses stdlib only (urllib + json).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def post_chat(endpoint: str, payload: dict[str, Any], timeout: int = 180, retries: int = 2) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload).encode("utf-8")
    url = f"{endpoint.rstrip('/')}/chat/completions"
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return json.loads(raw), elapsed_ms
        except (urllib.error.URLError, OSError, http.client.RemoteDisconnected, http.client.BadStatusLine) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(0.5 + attempt)
                continue
            raise
    assert last_err is not None
    raise last_err


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return a list of {name, arguments} from a chat completion message.
    Handles:
      - OpenAI-style message.tool_calls[].function.{name,arguments(JSON string)}
      - Models that smuggle a tool call into message.content as a JSON blob
    """
    calls: list[dict[str, Any]] = []
    tc = message.get("tool_calls") or []
    for entry in tc:
        fn = entry.get("function", {})
        name = fn.get("name")
        args_raw = fn.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw) if args_raw.strip() else {}
            except json.JSONDecodeError:
                args = {"__raw__": args_raw}
        else:
            args = args_raw
        if name:
            calls.append({"name": name, "arguments": args})

    if calls:
        return calls

    content = message.get("content") or ""
    if not content:
        return calls

    candidates = []
    fenced = re.findall(r"```(?:json|tool_code|tool_call)?\s*(\{[\s\S]*?\})\s*```", content)
    candidates.extend(fenced)
    if not candidates and "{" in content and "}" in content:
        start = content.find("{")
        end = content.rfind("}")
        if 0 <= start < end:
            candidates.append(content[start : end + 1])

    for blob in candidates:
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        name = obj.get("name") or obj.get("function") or obj.get("tool")
        args = obj.get("arguments") or obj.get("parameters") or obj.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass
        if name:
            calls.append({"name": name, "arguments": args})
            break

    return calls


def normalize(val: Any) -> Any:
    if isinstance(val, str):
        return val.strip().lower()
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return val


def args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not isinstance(actual, dict):
        return False
    for k, v_exp in expected.items():
        if k not in actual:
            return False
        if normalize(v_exp) != normalize(actual[k]):
            return False
    return True


def score_case(case: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, bool]:
    format_pass = len(calls) > 0 and all(isinstance(c.get("name"), str) for c in calls)
    if "expected_parallel" in case:
        wanted = case["expected_parallel"]
        names_match = sorted(c["name"] for c in calls) == sorted(w["name"] for w in wanted)
        if not names_match:
            return {"format": format_pass, "function": False, "argument": False, "overall": False}
        used_actual = list(calls)
        all_args_ok = True
        for w in wanted:
            best = None
            for i, c in enumerate(used_actual):
                if c["name"] == w["name"] and args_match(w["arguments"], c.get("arguments") or {}):
                    best = i
                    break
            if best is None:
                all_args_ok = False
                break
            used_actual.pop(best)
        return {
            "format": format_pass,
            "function": True,
            "argument": all_args_ok,
            "overall": format_pass and all_args_ok,
        }

    expected = case["expected"]
    call = calls[0] if calls else {"name": None, "arguments": {}}
    function_pass = call.get("name") == expected["name"]
    argument_pass = function_pass and args_match(expected.get("arguments", {}), call.get("arguments") or {})
    return {
        "format": format_pass,
        "function": function_pass,
        "argument": argument_pass,
        "overall": format_pass and function_pass and argument_pass,
    }


def run(args: argparse.Namespace) -> int:
    with open(args.tests, "r", encoding="utf-8") as f:
        tests = json.load(f)

    if args.limit:
        tests = tests[: args.limit]

    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))

    results: list[dict[str, Any]] = []
    latencies_ms: list[float] = []

    for idx, case in enumerate(tests, 1):
        payload = {
            "model": args.model_id,
            "messages": [{"role": "user", "content": case["query"]}],
            "tools": case["tools"],
            "tool_choice": "auto",
            "temperature": 0.0,
            "max_tokens": args.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        ok = True
        err: str | None = None
        elapsed_ms = 0.0
        calls: list[dict[str, Any]] = []
        try:
            resp, elapsed_ms = post_chat(args.endpoint, payload, timeout=args.timeout)
            latencies_ms.append(elapsed_ms)
            message = (resp.get("choices") or [{}])[0].get("message", {})
            calls = extract_tool_calls(message)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, http.client.RemoteDisconnected, http.client.BadStatusLine) as exc:
            ok = False
            err = f"{type(exc).__name__}: {exc}"

        score = score_case(case, calls) if ok else {"format": False, "function": False, "argument": False, "overall": False}
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "ok": ok,
                "error": err,
                "elapsed_ms": elapsed_ms,
                "calls": calls,
                "score": score,
            }
        )
        line_pass = "PASS" if score["overall"] else "FAIL"
        print(f"  [{idx:>3}/{len(tests)}] {case['id']:<14} {line_pass}  ({elapsed_ms:7.1f} ms)", flush=True)

    duration_sec = time.time() - started

    def rate(field: str) -> float:
        return round(100.0 * sum(1 for r in results if r["score"][field]) / max(len(results), 1), 2)

    summary = {
        "cell_id": args.cell_id,
        "model_id": args.model_id,
        "endpoint": args.endpoint,
        "tests_file": os.path.basename(args.tests),
        "n_cases": len(results),
        "started_at": started_iso,
        "duration_sec": round(duration_sec, 2),
        "tool_calling": {
            "format_pass_rate": rate("format"),
            "function_accuracy": rate("function"),
            "argument_accuracy": rate("argument"),
            "overall_pass": rate("overall"),
        },
        "latency_ms": {
            "p50": round(statistics.median(latencies_ms), 2) if latencies_ms else None,
            "p95": round(statistics.quantiles(latencies_ms, n=20)[18], 2) if len(latencies_ms) >= 20 else None,
            "mean": round(statistics.fmean(latencies_ms), 2) if latencies_ms else None,
        },
        "by_category": {
            cat: {
                "n": sum(1 for r in results if r["category"] == cat),
                "overall_pass": round(
                    100.0 * sum(1 for r in results if r["category"] == cat and r["score"]["overall"])
                    / max(sum(1 for r in results if r["category"] == cat), 1),
                    2,
                ),
            }
            for cat in sorted({r["category"] for r in results})
        },
        "results": results,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"\n  → {args.cell_id}: overall={summary['tool_calling']['overall_pass']}% "
        f"format={summary['tool_calling']['format_pass_rate']}% "
        f"p50={summary['latency_ms']['p50']}ms  ({len(results)} cases, {duration_sec:.1f}s)"
    )
    print(f"  → wrote {args.out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", default=os.environ.get("LLAMA_ENDPOINT", "http://127.0.0.1:11434/v1"))
    p.add_argument("--model-id", default="local-model")
    p.add_argument("--cell-id", required=True)
    p.add_argument("--tests", default=os.path.join(os.path.dirname(__file__), "bfcl_subset.json"))
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
