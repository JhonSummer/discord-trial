"""Clean 16 kHz speech fixture used as the Lyra reference.

The committed WAV is 12.0 seconds (600 Lyra frames, 192000 samples) of mono
16-bit PCM. It was spoken by espeak-ng 1.51 (en-US, speed 132, pitch 42, word
gap 6) from public-domain Harvard sentences, resampled to 16 kHz, and trimmed
to an exact frame multiple. espeak-ng is formant synthesis, not a cloned voice.

Replacing the fixture changes every score. Update ``results/`` and
``thresholds.json`` in the same change.
"""

from __future__ import annotations

import hashlib
import os
import wave

SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20 ms at 16 kHz
N_FRAMES = 600
N_SAMPLES = N_FRAMES * FRAME_SAMPLES  # 12.0 s
FIXTURE_SHA256 = "79637370974199ba3055bbe7bda7b7dc67a7f5fc311d8d2ad37df71431914679"

HARVARD_SENTENCES = (
    "The birch canoe slid on the smooth planks. "
    "Glue the sheet to the dark blue background. "
    "It is easy to tell the depth of a well. "
    "These days a chicken leg is a rare dish. "
    "Rice is often served in round bowls. "
    "The juice of lemons makes fine punch. "
    "The box was thrown beside the parked truck. "
    "The hogs were fed chopped corn and garbage. "
    "Four hours of steady work faced us. "
    "A large size in stockings is hard to sell."
)

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "clean_speech_16k.wav")


def fixture_path() -> str:
    return _FIXTURE


def load_pcm16() -> bytes:
    """Return the fixture payload as little-endian int16 bytes."""
    digest = hashlib.sha256()
    with open(_FIXTURE, "rb") as fh:
        blob = fh.read()
    digest.update(blob)
    got = digest.hexdigest()
    if got != FIXTURE_SHA256:
        raise RuntimeError(
            f"clean speech fixture sha256 is {got}, expected {FIXTURE_SHA256}. "
            "The quality tables are tied to this exact waveform."
        )
    with wave.open(_FIXTURE, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
            raise RuntimeError("clean speech fixture must be mono 16-bit 16 kHz PCM")
        if wav.getnframes() != N_SAMPLES:
            raise RuntimeError(
                f"clean speech fixture has {wav.getnframes()} samples, expected {N_SAMPLES}"
            )
        pcm = wav.readframes(N_SAMPLES)
    if len(pcm) != N_SAMPLES * 2:
        raise RuntimeError("clean speech fixture payload length does not match the header")
    return pcm
