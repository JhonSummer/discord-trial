#!/usr/bin/env bash
# Build pinned Lyra 1.3.2 (google/lyra 47698dad) encoder_main and decoder_main.
# The codec stays outside this repo. GCC 11 is required: TensorFlow 2.11 does
# not build with GCC 13. Bazelisk reads /opt/lyra/.bazelversion (5.3.2).
set -euo pipefail

ROOT="${LYRA_ROOT:-/opt/lyra}"
COMMIT="47698dadf0010abff6a848e02642f55f806d4842"
CC="${CC:-/usr/bin/gcc-11}"
CXX="${CXX:-/usr/bin/g++-11}"
PATCH="$(cd "$(dirname "$0")" && pwd)/patches/lyra-1.3.2-pin-deps.patch"

if [[ ! -x "$CC" || ! -x "$CXX" ]]; then
  echo "gcc-11 is required at CC=$CC CXX=$CXX" >&2
  exit 1
fi
if ! command -v bazel >/dev/null 2>&1 && ! command -v bazelisk >/dev/null 2>&1; then
  echo "bazelisk (or bazel) is required on PATH" >&2
  exit 1
fi

if [[ ! -d "$ROOT/.git" ]]; then
  git clone https://github.com/google/lyra.git "$ROOT"
fi
git -C "$ROOT" fetch --depth 1 origin "$COMMIT"
git -C "$ROOT" checkout --force --detach "$COMMIT"

if ! grep -q "b33e3bad4c46c8a6345525fd822af355e5ef9446" "$ROOT/WORKSPACE"; then
  git -C "$ROOT" apply "$PATCH"
fi

export CC CXX
export USE_BAZEL_VERSION=5.3.2
cd "$ROOT"
bazel build -c opt \
  //lyra/cli_example:encoder_main \
  //lyra/cli_example:decoder_main \
  --jobs="${JOBS:-2}" \
  --local_ram_resources="${LOCAL_RAM_MB:-4096}"
echo "Lyra tools: $ROOT/bazel-bin/lyra/cli_example/{encoder,decoder}_main"
