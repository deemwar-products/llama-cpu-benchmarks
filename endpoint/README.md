# endpoint/

Tiny stdlib-only Python HTTP service that exposes the per-cell benchmark JSONs.

## Routes

```
GET /             -> service identity + available cell IDs
GET /healthz      -> { ok: true }
GET /results      -> aggregated summary across all cells
GET /results/{id} -> single cell document with full BFCL trace
```

CORS: `Access-Control-Allow-Origin: *`.

## Run locally

```bash
RESULTS_DIR=./results PORT=8765 python3 server.py
```

## Run in Docker

```bash
docker build -t llamabench-endpoint:latest endpoint/
docker run -d --restart=unless-stopped \
  --name llamabench-endpoint \
  --cpus=0.5 --memory=256m \
  -v $(pwd)/results:/results:ro \
  -p 8765:8765 \
  llamabench-endpoint:latest
```

Binds the container's port 8765 to the host. Expose publicly through whatever proxy / firewall rules your host uses — there are no secrets in the response.

## Why stdlib only

Keeps the image tiny (~50 MB), no pip install, no FastAPI/uvicorn surface area. The endpoint serves O(KB) of JSON — there's no need for an async framework.
