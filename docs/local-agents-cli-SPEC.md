# local-agents-cli — Specification

> A Go CLI that runs a single curated LLM + embedding model fully offline, with
> RAG over your docs, a SKILL-based agent layer, an OpenAI-compatible HTTP
> server, and zip-based bundle export/import for air-gapped sharing.

Repo: `deemwar-products/local-agents-cli`

Sister projects:
- `deemwar-products/llama-cpu-benchmarks` — picks the default model + publishes the manifest
- `muthuishere/offline-llm-knowledge-system` — defines the RAG bundle format (chunks/orama/graph) and ships the browser counterpart

---

## 1. Goals

1. **One model, one embedding model.** No model zoo. The benchmark project picks the winner; the CLI installs that one.
2. **Works offline after install.** All inference, embeddings, and RAG run locally on CPU via `llama.cpp`.
3. **Single static binary.** Go. Ship one binary per OS/arch. `llama.cpp` is either embedded via cgo (`llama-cpp-go` style) or shelled out to a vendored `llama-server` — see §11.
4. **Every command works two ways:** interactive TUI prompts *and* fully-flagged non-interactive mode (for scripts, CI, tests).
5. **Skills are folders.** Drop a directory in `~/.local-agents/skills/<name>/` and the model can call it as a tool.
6. **Bundles are portable.** `export` produces a zip. `import` accepts a folder *or* an HTTPS signed URL. Imported bundle can be served immediately — no rebuild step.
7. **Dashboard built in.** `serve` exposes both an OpenAI-compatible `/v1` API and a static dashboard at `/`.
8. **Testable.** A `test` / `demo` command runs a canned scenario so users can see it working without bringing their own docs.

## 2. Non-goals

- Multi-model routing, model marketplaces, fine-tuning.
- GPU inference (browser sister project covers WebGPU).
- Cloud sync, accounts, telemetry.

## 3. Architecture

```
                ┌──────────────────────────────────────┐
                │       local-agents (Go binary)       │
                │                                      │
   CLI flags ─▶ │  cmd/  ──▶  internal/agent  ──▶  llama.cpp
   TUI prompts  │              │       │                  │
                │              ▼       ▼                  │
                │           skills    rag                 │
                │              │       │                  │
                │              ▼       ▼                  │
                │           tools   orama+graph           │
                │                       │                 │
                │                       ▼                 │
                │                  ~/.local-agents/       │
                │                  └── model/             │
                │                  └── embed/             │
                │                  └── bundles/<name>/    │
                │                  └── skills/<name>/     │
                │                                      │
                │  HTTP: /v1/chat/completions  +  /  │
                └──────────────────────────────────────┘
```

Data dir layout (configurable via `--data-dir` or `$LOCAL_AGENTS_HOME`):

```
~/.local-agents/
├── config.yaml              # active model, active bundle, server port
├── model/                   # GGUF + tokenizer (single model)
├── embed/                   # bge-small ONNX (single embedding model)
├── bundles/
│   └── <bundle-name>/
│       ├── manifest.json
│       ├── chunks.json
│       ├── orama-index.bin
│       ├── graph.json
│       └── sources/
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        └── tool                  # any executable
```

## 4. Commands

All commands obey three rules:
- No flags + TTY → interactive prompts.
- Flags supplied → non-interactive, scriptable.
- `--json` → machine-readable output on stdout.

### `local-agents init`
First-run setup. Interactively picks the model from the benchmark manifest, downloads model + embedding weights, writes `config.yaml`.

```
local-agents init                       # interactive
local-agents init --model qwen-3.5-4b --yes
local-agents init --manifest https://benchmarks.deemwar.dev/manifest.json
```

### `local-agents ingest <path>`
Chunks → embeds → builds Orama index → builds cosine-similarity graph. Output is a bundle directory.

```
local-agents ingest ./docs              # interactive: name + chunk size
local-agents ingest ./docs --name handbook --chunk-tokens 100 --graph-threshold 0.75
```

### `local-agents chat`
Terminal REPL. Streams tokens. Auto-loads the active bundle for RAG. Skills are wired as tool-calls.

```
local-agents chat                       # interactive REPL
local-agents chat --bundle handbook --prompt "summarize onboarding"
local-agents chat --no-rag --no-skills  # raw model
```

### `local-agents serve`
HTTP server.

```
local-agents serve                      # localhost:8080
local-agents serve --port 8088 --host 0.0.0.0 --bundle handbook
```

Routes:
- `POST /v1/chat/completions` — OpenAI-compatible, streaming SSE.
- `POST /v1/embeddings` — OpenAI-compatible.
- `GET  /v1/models` — single entry.
- `GET  /api/skills` — list installed skills.
- `GET  /api/bundles` — list installed bundles.
- `GET  /` — static dashboard (built from offline-llm-knowledge-system's import UI, repackaged to talk to `/v1`).

### `local-agents skills`
```
local-agents skills list
local-agents skills add ./my-skill              # folder, copied/symlinked
local-agents skills add https://.../skill.zip   # signed URL
local-agents skills remove <name>
local-agents skills run <name> -- <args>        # invoke directly, bypass model
```

### `local-agents export`
Packages a bundle + (optionally) the model + skills into a single zip.

```
local-agents export --bundle handbook --out handbook.zip
local-agents export --bundle handbook --include-model --include-skills --out full.zip
```

### `local-agents import <source>`
Accepts a folder path or an `https://` URL (signed URL supported — the CLI just GETs it).

```
local-agents import ./handbook                          # folder
local-agents import https://share.example.com/x.zip?sig=...   # signed URL
local-agents import https://... --serve                 # import + serve in one shot
```

### `local-agents test`
Canned demo. Downloads a tiny sample doc set, ingests, asks three pre-written questions, prints results. Used for smoke-testing an install and showing new users what "good" looks like.

```
local-agents test                       # full demo
local-agents test --quick               # skip ingest, use bundled sample
```

### `local-agents doctor`
Checks: model present, embedding present, llama-server reachable, disk space, port availability.

## 5. Bundle format (zip)

Compatible with `offline-llm-knowledge-system`'s browser zip where possible, so a CLI export can be imported in the browser app and vice versa.

```
bundle.zip
├── manifest.json           # name, version, embed-model-id, chunk-count, created-at
├── chunks.json             # [{id, text, vec[384], source, offset}, ...]
├── orama-index.bin         # serialized Orama hybrid index (BM25 + cosine)
├── graph.json              # adjacency list, cosine ≥ threshold
├── sources/                # original documents (PDF/DOCX/MD/TXT)
├── skills/                 # optional, only if --include-skills
│   └── <name>/...
└── model/                  # optional, only if --include-model
    └── <gguf-file>
```

## 6. Skills format

Each skill is a folder. Discovered at startup from `~/.local-agents/skills/`.

```
skills/weather/
├── SKILL.md
└── tool                    # any executable: bash, python, go binary
```

`SKILL.md` (frontmatter + prose):

```markdown
---
name: weather
description: Look up current weather for a city.
parameters:
  city: { type: string, description: "City name", required: true }
  units: { type: string, enum: [c, f], default: c }
---

# Weather

Calls the local weather cache. When the user asks about weather
conditions, forecasts, or "what's it like in <city>", invoke this.
```

Runtime contract:
- CLI converts frontmatter to an OpenAI-style tool schema.
- On tool-call, CLI executes `./tool` with arguments as JSON on stdin.
- Tool prints JSON to stdout; CLI feeds it back into the model.
- Non-zero exit code → error returned to model.

## 7. Model + embedding distribution

Source of truth: a `manifest.json` published by `llama-cpu-benchmarks` (e.g. `https://benchmarks.deemwar.dev/manifest.json`).

```json
{
  "schema": 1,
  "default_model": "qwen-3.5-4b-q4",
  "models": [
    {
      "id": "qwen-3.5-4b-q4",
      "gguf_url": "https://huggingface.co/.../qwen-3.5-4b-q4_k_m.gguf",
      "sha256": "...",
      "size_bytes": 2700000000,
      "context": 32768,
      "tool_calling": true,
      "bench": { "tokens_per_sec": 14.2, "bfcl_total": 0.78 }
    }
  ],
  "embedding": {
    "id": "bge-small-en-v1.5-q8",
    "onnx_url": "https://...",
    "sha256": "...",
    "dim": 384
  }
}
```

CLI verifies sha256 on download. `--manifest <url>` lets advanced users override.

## 8. Inference

Default: bundled `llama-server` binary (CPU build of llama.cpp) launched as a child process on a random local port; the CLI talks to it via its OpenAI-compatible HTTP API. This avoids cgo build complexity and matches what the benchmarks project already proves.

Alternative considered: cgo bindings (`go-llama.cpp`). Faster startup, but build matrix gets ugly. Open question — see §11.

## 9. RAG pipeline

On `chat` / `serve` with a bundle loaded:

1. Embed user query (bge-small ONNX, via `onnxruntime-go` or shelled-out python helper — TBD §11).
2. Orama hybrid search → top-K chunks.
3. Graph expansion: for each top-K, pull neighbors with cosine ≥ threshold (2-hop).
4. Assemble context, hand to llama-server with system prompt + tool schemas (skills).
5. Stream response. If tool-call, dispatch to skill, feed result back.

This mirrors the offline-llm-knowledge-system pipeline 1:1 so bundle compat is real, not aspirational.

## 10. Interactive vs non-interactive

Every prompt has a flag equivalent. Rules:

| Condition | Behavior |
|---|---|
| Stdin is a TTY and no flags given | Interactive (Bubble Tea TUI) |
| Any positional/flag arg present | Non-interactive |
| `--json` | Non-interactive + machine output |
| `--yes` | Non-interactive + auto-confirm |
| `CI=true` env | Non-interactive (best-effort defaults) |

Tests assert both modes for every command.

## 11. Open questions

1. **Inference embedding**: child-process `llama-server` (simple, cross-platform, slightly higher latency) vs. cgo bindings (one binary, harder build matrix). **Lean: child-process v1.**
2. **ONNX runtime in Go**: native `onnxruntime-go` (cgo), `gomlx`, or a small Python helper. **Lean: `onnxruntime-go` if it builds cleanly on all targets, else child-process Python.**
3. **Dashboard packaging**: embed React build via `embed.FS`. Probably yes, no question.
4. **Signed URL conventions**: do we validate signature, or treat URLs as opaque?
5. **Bundle compat boundary**: how strict? Browser app uses `orama-index.json.gz` (JSON serialized); CLI may prefer a binary format. Decision: keep JSON-gz for compat, accept the size hit.

## 12. Milestones

| # | Deliverable |
|---|---|
| M1 | `init`, `doctor`, child-process llama-server wiring, single-shot `chat --prompt` |
| M2 | `ingest`, `chat` REPL with RAG |
| M3 | `skills` (add/list/run), tool-calling in chat |
| M4 | `serve` with `/v1/*` + dashboard |
| M5 | `export` / `import` (folder + signed URL), `test` demo |
| M6 | Bundle compat with browser app verified both directions |

## 13. Repo layout (proposed)

```
local-agents-cli/
├── cmd/local-agents/main.go
├── internal/
│   ├── cli/              # cobra commands, TUI prompts
│   ├── manifest/         # manifest fetch + verify
│   ├── llama/            # child-process wrapper
│   ├── embed/            # onnx wrapper
│   ├── rag/              # chunking, orama, graph
│   ├── skills/           # SKILL.md parser + runner
│   ├── bundle/           # zip export/import
│   └── server/           # HTTP + static dashboard
├── web/                  # dashboard sources (vendored from offline-llm-knowledge-system import app)
├── testdata/             # docs + golden bundles for `local-agents test`
└── docs/
    └── SPEC.md           # this file
```
