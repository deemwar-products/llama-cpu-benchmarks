# Target hardware

All benchmarks ran on a single shared CPU box. The point of the experiment is what these models do on commodity x86 silicon without a GPU — the box's identity isn't load-bearing for any of the numbers, so it's deliberately omitted.

## Probed specs (2026-05-20)

| Resource | Value |
|---|---|
| CPU | Intel Xeon E-2176G — 6 cores / 12 threads @ 3.7 GHz |
| ISA features | AVX2 yes, AVX-512 **no** |
| RAM | 62 GB total (~60 GB available) |
| Swap | 31 GB |
| Disk | 847 GB, ~765 GB free |
| GPU | Intel UHD P630 iGPU only (no NVIDIA, no CUDA) |
| OS | Ubuntu 22.04.5 LTS, kernel 5.15.0-164 |

## Shared with other workloads

The host runs other unrelated production containers in parallel. Every benchmark container is cgroup-pinned so it can't starve them:

```bash
docker run --rm \
  --cpus=4 --cpuset-cpus=8-11 \
  --memory=12g --memory-swap=12g \
  ...
```

- **Cores 8-11** pinned to the benchmark; cores 0-7 reserved for the rest of the system.
- **12 GB memory cap** — leaves ~50 GB for everything else.
- Runs scheduled in low-traffic windows.
- An automatic kill triggers if host `load_avg(1m)` exceeds 8.0.

## What this implies for the experiment

- **CPU-only inference.** No CUDA path, no Vulkan path tested.
- **Speed-bound by AVX2, not memory.** TurboQuant's headline benefit is KV-cache memory reduction — interesting on GPUs with tight VRAM, much less interesting on a box with 60 GB free RAM.
- **AVX-512 absent.** Some llama.cpp speedups (specific `Q4_K_M` matmul kernels) only kick in with AVX-512. This Coffee Lake box won't see them.
