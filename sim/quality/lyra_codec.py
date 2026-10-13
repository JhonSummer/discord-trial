"""Drive the pinned Lyra 1.3.2 encoder and decoder CLIs.

The binaries are produced by ``setup_lyra.sh`` from google/lyra commit
47698dadf0010abff6a848e02642f55f806d4842 (v1.3.2, Apache-2.0). This repo does
not vendor the codec. Set ``LYRA_ROOT`` if the checkout is not ``/opt/lyra``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

LYRA_COMMIT = "47698dadf0010abff6a848e02642f55f806d4842"
PACKET_BYTES = {3200: 8, 6000: 15, 9200: 23}


def resolve_tools() -> tuple:
    root = os.environ.get("LYRA_ROOT", "/opt/lyra")
    encoder = os.environ.get(
        "LYRA_ENCODER", os.path.join(root, "bazel-bin/lyra/cli_example/encoder_main")
    )
    decoder = os.environ.get(
        "LYRA_DECODER", os.path.join(root, "bazel-bin/lyra/cli_example/decoder_main")
    )
    model = os.environ.get("LYRA_MODEL_PATH", os.path.join(root, "lyra/model_coeffs"))
    missing = [path for path in (encoder, decoder, model) if not os.path.exists(path)]
    if missing:
        raise FileNotFoundError(
            "Lyra 1.3.2 tools not found: "
            + ", ".join(missing)
            + f". Build commit {LYRA_COMMIT} with sim/quality/setup_lyra.sh "
            "or set LYRA_ROOT / LYRA_ENCODER / LYRA_DECODER / LYRA_MODEL_PATH."
        )
    return encoder, decoder, model


def _run(cmd: list) -> None:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(
            "Lyra command failed with exit "
            f"{proc.returncode}: {' '.join(cmd)}\n{tail}"
        )


def encode(wav_path: str, bitrate: int, out_dir: str) -> str:
    if bitrate not in PACKET_BYTES:
        raise ValueError(f"Lyra v2 bitrate must be one of {sorted(PACKET_BYTES)}")
    encoder, _decoder, model = resolve_tools()
    os.makedirs(out_dir, exist_ok=True)
    _run([
        encoder,
        f"--input_path={wav_path}",
        f"--output_dir={out_dir}",
        f"--bitrate={bitrate}",
        "--enable_dtx=false",
        "--enable_preprocessing=false",
        f"--model_path={model}",
    ])
    stem = os.path.splitext(os.path.basename(wav_path))[0]
    encoded = os.path.join(out_dir, stem + ".lyra")
    if not os.path.isfile(encoded):
        raise RuntimeError(f"encoder did not write {encoded}")
    return encoded


def decode(lyra_path: str, bitrate: int, out_dir: str, loss_pattern: str, suffix: str) -> str:
    """Decode ``lyra_path``. ``loss_pattern`` is a Lyra fixed-loss flag value or ''."""
    _encoder, decoder, model = resolve_tools()
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        decoder,
        f"--encoded_path={lyra_path}",
        f"--output_dir={out_dir}",
        f"--bitrate={bitrate}",
        "--sample_rate_hz=16000",
        "--packet_loss_rate=0",
        "--average_burst_length=1",
        f"--output_suffix={suffix}",
        f"--model_path={model}",
    ]
    if loss_pattern:
        cmd.append(f"--fixed_packet_loss_pattern={loss_pattern}")
    _run(cmd)
    stem = os.path.splitext(os.path.basename(lyra_path))[0]
    wav_path = os.path.join(out_dir, f"{stem}{suffix}.wav")
    if not os.path.isfile(wav_path):
        raise RuntimeError(f"decoder did not write {wav_path}")
    return wav_path


def assert_packet_count(lyra_path: str, bitrate: int, n_frames: int) -> None:
    size = os.path.getsize(lyra_path)
    packet = PACKET_BYTES[bitrate]
    if size != n_frames * packet:
        raise RuntimeError(
            f"{lyra_path} is {size} bytes, expected {n_frames} x {packet} "
            "(DTX must stay off so each 20 ms frame is one packet)"
        )
