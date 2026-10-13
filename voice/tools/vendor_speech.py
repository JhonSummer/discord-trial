#!/usr/bin/env python3
"""Regenerate the vendored clean-speech fixtures (one-time, needs network).

This is the provenance-of-record for ``voice/assets/speech/*.wav``. It pulls three LibriSpeech
dev-clean excerpts from the ``librosa`` example registry (CC BY 4.0, public-domain LibriVox
source; see the sibling ``ATTRIBUTION.md``), trims ~4.8 s of continuous narration, downmixes
to mono 16 kHz and peak-normalizes. The gate itself never runs this — it reads the committed
WAVs — so the test suite stays offline.

    python voice/tools/vendor_speech.py
"""

from __future__ import annotations

import os

import numpy as np

_OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "speech")
_SOURCES = {
    "sample1": "libri1",  # 5703-47212-0000
    "sample2": "libri2",  # 3436-172162-0000
    "sample3": "libri3",  # 198-209-0000
}
_START_S, _END_S = 0.35, 5.15


def main() -> None:
    import librosa  # noqa: WPS433 - optional, only for regeneration
    import soundfile as sf

    os.makedirs(_OUT, exist_ok=True)
    for name, key in _SOURCES.items():
        y, sr = librosa.load(librosa.example(key), sr=16000, mono=True)
        seg = y[int(_START_S * sr):int(_END_S * sr)]
        seg = seg / (np.max(np.abs(seg)) + 1e-9) * 0.9
        out = os.path.join(_OUT, f"{name}.wav")
        sf.write(out, seg.astype(np.float32), sr, subtype="PCM_16")
        print(f"wrote {out}  ({len(seg) / sr:.2f}s)")


if __name__ == "__main__":
    main()
