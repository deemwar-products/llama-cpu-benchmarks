#!/usr/bin/env bash
# Attempt to build a TurboQuant-capable llama.cpp inside a Docker container.
# Tries forks in rank order, stops on first success.
#
# Output: /opt/llamabench/llamacpp-tq/build-status.json with which fork won
# (or all-failed) and a CPU-runnable binary path if successful.
#
# Runs the build inside ubuntu:22.04 so the prod host stays clean — no apt.
set -uo pipefail

WORKDIR=/opt/llamabench
BUILD_HOST="${WORKDIR}/llamacpp-tq"
STATUS_FILE="${BUILD_HOST}/build-status.json"
LOG_DIR="${WORKDIR}/logs"
mkdir -p "${BUILD_HOST}" "${LOG_DIR}"

declare -a FORKS=(
  "atomicmilkshake|https://github.com/atomicmilkshake/llama-cpp-turboquant.git|master"
  "TheTom|https://github.com/TheTom/llama-cpp-turboquant.git|master"
  "MartinCrespoC|https://github.com/MartinCrespoC/QuantumLeap---Llama.cpp-TurboQuant.git|main"
  "PippBauda|https://github.com/PippBauda/llama.cpp-turboquant-mtp.git|main"
)

write_status() {
  local fork="$1" outcome="$2" detail="$3"
  python3 - <<PY
import json, time
out = {
  "attempted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "fork": "${fork}",
  "outcome": "${outcome}",
  "detail": ${detail@Q},
}
with open("${STATUS_FILE}", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
PY
}

for entry in "${FORKS[@]}"; do
  IFS='|' read -r fork url branch <<<"${entry}"
  echo "=== Attempting ${fork} (${url}, ${branch}) ==="
  log="${LOG_DIR}/tq-build-${fork}.log"
  : > "${log}"

  # Build inside ubuntu:22.04 with cgroup-pinned resources that don't touch
  # cores 8-11 (those are the benchmark cores) or interfere with prod tenants
  # more than the existing share. Use cores 4-7 with cap and modest memory.
  docker run --rm --name "tq-build-${fork}" \
    --cpus=4 --cpuset-cpus=4-7 --memory=8g --memory-swap=8g \
    -v "${BUILD_HOST}:/work" \
    ubuntu:22.04 \
    bash -lc "
      set -eu
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq >/dev/null
      apt-get install -y -qq git build-essential cmake curl libcurl4-openssl-dev pkg-config >/dev/null
      cd /work
      rm -rf src
      git clone --depth 1 --branch '${branch}' '${url}' src 2>&1 | tail -5
      cd src
      # Try cmake with TurboQuant; CPU-only, no CUDA.
      mkdir -p build
      cd build
      cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=ON -DGGML_AVX2=ON \
        -DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF \
        2>&1 | tail -30
      cmake --build . --target llama-server llama-bench --config Release -j4 2>&1 | tail -30
      ls -la bin/llama-server bin/llama-bench 2>/dev/null || ls -la llama-server llama-bench 2>/dev/null
      # Try to detect the turbo3 KV flag in llama-server --help
      BIN=\$(find . -name llama-server -type f -executable | head -1)
      if [ -z \"\${BIN}\" ]; then echo 'NO_BINARY'; exit 31; fi
      \$BIN --help 2>&1 | grep -iE 'turbo|cache-type' | head -10 || true
    " >>"${log}" 2>&1

  rc=$?
  if [ "${rc}" -eq 0 ] && [ -d "${BUILD_HOST}/src/build" ]; then
    BIN_PATH=$(docker run --rm -v "${BUILD_HOST}:/work" ubuntu:22.04 \
      bash -c "find /work/src/build -name llama-server -type f -executable 2>/dev/null | head -1" 2>>"${log}")
    if [ -n "${BIN_PATH}" ]; then
      echo "  → built; binary at ${BIN_PATH}"
      # Quick check: does the binary advertise turbo cache type?
      TURBO_CHECK=$(docker run --rm -v "${BUILD_HOST}:/work" ubuntu:22.04 \
        bash -lc "apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq libcurl4-openssl-dev >/dev/null 2>&1; ${BIN_PATH} --help 2>&1 | grep -iE 'turbo' | head -5" 2>>"${log}" || true)
      if [ -n "${TURBO_CHECK}" ]; then
        write_status "${fork}" "success" "$(printf %q "${TURBO_CHECK}")"
        echo "  → SUCCESS — turbo flag present"
        exit 0
      fi
      write_status "${fork}" "built-no-turbo-flag" "binary built but '--help | grep turbo' returned empty"
      echo "  → built but no turbo flag — moving on"
    else
      write_status "${fork}" "no-binary" "build completed but no llama-server binary found"
      echo "  → no binary produced"
    fi
  else
    err_tail="$(tail -15 "${log}" 2>/dev/null | tr '\n' ' ' | head -c 600)"
    write_status "${fork}" "build-failed" "exit ${rc}; tail: ${err_tail}"
    echo "  → BUILD FAILED (exit ${rc})"
  fi
done

write_status "all" "all-failed" "no TurboQuant fork built a CPU-AVX2 binary that advertises a turbo cache flag"
echo "=== All four forks failed ==="
exit 41
