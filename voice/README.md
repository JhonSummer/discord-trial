# `voice/` — the Lyra voice-quality harness & committed gate

This package renders **real audio** through the mesh voice path and scores it with objective and
neural voice-quality metrics, turning "the voice path sounds fine" into a reproducible, committed
test-suite gate. It is the audio counterpart to [`sim/`](../sim): `sim` answers *"does a call fit
on the BLE mesh?"* in discrete-event time; `voice` answers *"how good does it actually sound after
the mesh has had its way with it?"*.

```
clean speech → encode (low-bitrate parametric codec @ 3.2/6/9.2 kbps)
             → mesh channel (packet loss · jitter · multi-hop · reorder)
             → jitter buffer (fixed baseline | adaptive)
             → [optional 1-frame FEC]
             → packet-loss concealment (silence baseline | parametric)
             → phase-continuous synthesizer → recovered audio
             → STOI · PESQ · ViSQOL · DNSMOS · PLCMOS
```

## Run it

```bash
pip install -r requirements.txt            # pystoi, pesq, speechmos (DNSMOS+PLCMOS), soundfile, ...
# pesq builds a C extension: on Debian/Ubuntu `sudo apt-get install -y python3.12-dev` first.

python3 -m pytest voice/tests -m voicegate # the committed quality gate (hard requirement)
python3 -m voiceq.bench                     # full before/after matrix -> voice/results/benchmark.{md,csv}
python3 -m voiceq.bench --bitrates 9.2k --conditions moderate heavy --configs baseline optimized
```

Everything runs **offline**: the neural-MOS model weights ship inside the `speechmos` wheel
(verified by running the whole thing behind a dead HTTP proxy), and the clean reference is either
synthesized in-process or read from the vendored clips in [`assets/speech`](assets/speech).

## The metrics (and why there are two families)

| metric | type | scale | backend |
| --- | --- | --- | --- |
| **STOI / ESTOI** | full-reference intelligibility | 0–1 | `pystoi` (pure Python) |
| **PESQ** (wideband) | full-reference MOS-LQO | ~1–4.64 | `pesq` (ITU-T P.862.2) |
| **ViSQOL\*** | full-reference NSIM | 1–5 | **in-repo proxy** (see below) |
| **DNSMOS** (ovrl/sig/bak/p808) | **no-reference neural MOS** | 1–5 | `speechmos` (ITU-T P.835, ONNX) |
| **PLCMOS** | **no-reference neural MOS** | 1–5 | `speechmos` (INTERSPEECH 2023, ONNX) |

* **Full-reference** metrics compare the recovered waveform to a clean reference. We report them
  against **two** references:
  * *absolute* (`abs_*`) — vs the clean **uncoded** speech: the true end-to-end quality, **bounded
    by the codec**.
  * *robustness* (`rob_*`) — vs the clean-channel **coded** speech: isolates what the mesh + jitter
    buffer + PLC do, independent of codec fidelity. This is what the optimization moves.
* **No-reference neural MOS** (DNSMOS, PLCMOS) judge the recovered audio directly. **PLCMOS** is
  trained specifically on packet-loss-concealed speech — the most on-target predictor for a mesh
  voice path.

## Honest scope — what is real here, and what stands in

This harness is **real**: real audio, real DSP, real published metrics running offline. Two pieces
are deliberate, clearly-labeled stand-ins because the originals cannot be built in this sandbox
(no Bazel/TF toolchain), and both are **pluggable** so the real thing drops in unchanged:

1. **The codec is a classical parametric coder, not neural Lyra.** Lyra is a *generative neural*
   codec needing a Bazel/TFLite build + trained weights. `voiceq.codec.ParametricCodec` is a
   harmonic + noise coder at Lyra's exact operating points (3.2/6/9.2 kbps, 20 ms frames) that,
   like Lyra, transmits a compact per-frame parameterization — so bitrate genuinely trades against
   quality and lost frames are concealable by parameter extrapolation. It satisfies the
   `voiceq.codec.Codec` Protocol; a real Lyra binding with the same 20 ms framing makes the whole
   harness apply unchanged. **Consequence:** the `abs_*` numbers are bounded by this stand-in
   (real Lyra would score higher); the gate's strong bars are therefore on `rob_*` and the neural
   MOS, which measure the mesh/PLC work the user asked to optimize.
2. **ViSQOL is an in-repo NSIM proxy, not the official binary.** Official ViSQOL is a Bazel/C++
   build. `voiceq.metrics.visqol` computes ViSQOL's documented core — a neurogram-similarity
   (NSIM) comparison of mel/log spectrograms — mapped monotonically onto MOS. It is discriminative
   and tracks degradation the way ViSQOL does, but it is **not** calibrated ViSQOL MOS-LQO (hence
   the `*`). Set `VISQOL_BIN=/path/to/visqol` to use the real tool instead.

The clean reference defaults to short **real-speech** clips (LibriSpeech/CC-BY, see
[`assets/speech/ATTRIBUTION.md`](assets/speech/ATTRIBUTION.md)) because the neural MOS predictors
are trained on natural speech; a fully-synthetic fallback lives in `voiceq.reference`.

## The optimization: before → after

The naive **baseline** is a small fixed jitter buffer with silence concealment. The **optimized**
path adds an adaptive (percentile-tracking) jitter buffer and parametric PLC; **optimized+fec**
adds one-frame in-band redundancy (+3.2 kbps). Averaged over the vendored clips and seeds at
**9.2 kbps** (full matrix in [`results/benchmark.md`](results/benchmark.md)):

| condition (loss) | config | STOI (vs coded) | ViSQOL\* (vs coded) | DNSMOS | PLCMOS |
| --- | --- | --- | --- | --- | --- |
| moderate (12%) | baseline | 0.62 | 3.03 | 1.38 | 1.32 |
| moderate (12%) | **optimized** | **0.87** | **4.01** | **2.48** | **1.80** |
| moderate (12%) | optimized+fec | 0.91 | 4.16 | 2.52 | 1.97 |
| heavy (25%) | baseline | 0.32 | 2.38 | 1.31 | 1.16 |
| heavy (25%) | **optimized** | **0.76** | **3.64** | **2.35** | **1.62** |
| heavy (25%) | optimized+fec | 0.82 | 3.81 | 2.31 | 1.79 |

The optimized path recovers intelligibility from the 0.3–0.6 range back to 0.76–0.87 and lifts
neural MOS by ~1 point, recovering to **near the codec's clean ceiling** — i.e. the mesh path
stops being the bottleneck.

## The gate (hard requirement)

[`tests/test_voice_quality_gate.py`](tests/test_voice_quality_gate.py) enforces
[`voiceq/thresholds.py`](voiceq/thresholds.py): the optimized path must clear strong STOI / PESQ /
ViSQOL / DNSMOS / PLCMOS floors per condition and **at every bitrate**, and must beat the baseline
by a margin (so a PLC/jitter-buffer regression fails the build). Thresholds are set below the
measured optimized scores (with margin) and above the baseline. The neural backends are
**required**, not optional — a missing backend fails the gate rather than skipping it.

## Layout

| file | role |
| --- | --- |
| `voiceq/reference.py` | deterministic in-process speech synth (fallback reference) |
| `voiceq/corpus.py` | vendored real-speech clips (primary reference) |
| `voiceq/codec.py` | parametric harmonic+noise codec + phase-continuous synthesizer (Lyra stand-in) |
| `voiceq/dsp.py` | YIN pitch, LPC/cepstral spectral envelope, mel grid |
| `voiceq/channel.py` | mesh loss (Gilbert-Elliott) / jitter / multi-hop → delivery trace |
| `voiceq/jitterbuffer.py` | fixed vs adaptive playout buffers |
| `voiceq/plc.py` | silence vs parametric packet-loss concealment |
| `voiceq/pipeline.py` | end-to-end path + baseline/optimized presets |
| `voiceq/metrics/` | STOI, PESQ, DNSMOS, PLCMOS, ViSQOL-proxy adapters |
| `voiceq/bench.py` | benchmark runner → `results/benchmark.{md,csv}` |
| `voiceq/thresholds.py` | committed quality targets |
