# Target hardware: deemwar prod-app-1

All benchmarks were run on a single shared production host, with cgroup limits to prevent disturbing live tenants.

## Probed specs (2026-05-20)

| Resource | Value |
|---|---|
| Host | `ssh-prod-app-deemwar` (Hetzner, WireGuard `10.8.0.2`) |
| CPU | Intel Xeon E-2176G — 6 cores / 12 threads @ 3.7 GHz |
| ISA features | AVX2 yes, AVX-512 **no** |
| RAM | 62 GB total (~60 GB available) |
| Swap | 31 GB |
| Disk | 847 GB on `/dev/md2`, ~765 GB free |
| GPU | Intel UHD P630 iGPU only (no NVIDIA, no CUDA) |
| OS | Ubuntu 22.04.5 LTS, kernel 5.15.0-164 |

## Live tenants

The box concurrently serves:

- `reqsume-app-web`, `reqsume-ui-web`
- `video-ai-api`, `video-ai-ui`, `video-ai-worker`, `video-http`, `video-worker`
- `promtail` (log shipper)
- `kamal-proxy` (Kamal reverse proxy)

## Prod-safety constraints

Every benchmark container runs with strict caps so it can't starve real workloads:

```bash
docker run --rm \
  --cpus=4 --cpuset-cpus=8-11 \
  --memory=12g --memory-swap=12g \
  ...
```

- **Cores 8-11** pinned to the benchmark; cores 0-7 reserved for prod tenants.
- **12 GB memory cap** — leaves ~50 GB for the rest of the system.
- Runs scheduled in low-traffic windows (early IST morning).
- If host `load_avg(1m)` exceeds 8.0 the run aborts automatically.

## What this implies for the experiment

- **CPU-only inference.** No CUDA path, no Vulkan path tested.
- **Speed-bound by AVX2, not memory.** TurboQuant's headline benefit is KV-cache memory reduction — interesting on GPUs with tight VRAM, less interesting on a box with 60 GB free RAM.
- **AVX-512 absent.** Some llama.cpp speedups (e.g. certain `Q4_K_M` matmul kernels) only kick in with AVX-512. This Coffee Lake box won't see them.
