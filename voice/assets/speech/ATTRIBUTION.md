# Speech fixtures — provenance & license

The clips in this directory are short excerpts used as the *clean reference* for the Lyra
voice-quality gate. They are committed so the gate runs fully offline and reproducibly on
natural human speech (the neural MOS predictors are trained on real speech and are not
meaningful on synthesized tones).

| file          | source excerpt            | speaker/chapter/utt |
|---------------|---------------------------|---------------------|
| `sample1.wav` | `5703-47212-0000`         | LibriSpeech dev-clean |
| `sample2.wav` | `3436-172162-0000`        | LibriSpeech dev-clean |
| `sample3.wav` | `198-209-0000`            | LibriSpeech dev-clean |

Each file is a ~4.8 s mono 16 kHz PCM segment, trimmed from the corresponding excerpt and
peak-normalized. No other processing was applied.

## License / credit

These excerpts are from the **LibriSpeech ASR corpus**, which is distributed under the
**Creative Commons Attribution 4.0 International (CC BY 4.0)** license. The underlying
audiobook recordings are **public-domain** readings from the **LibriVox** project.

> V. Panayotov, G. Chen, D. Povey, and S. Khudanpur, "LibriSpeech: an ASR corpus based on
> public domain audio books," ICASSP 2015. Corpus: https://www.openslr.org/12/ — © the
> LibriSpeech authors, CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

The specific excerpts were obtained via the `librosa` example registry
(https://librosa.org/data/audio/), which redistributes these LibriSpeech segments.

Redistribution here is under the same CC BY 4.0 terms; this file provides the required
attribution. No modification was made beyond trimming, downmixing to mono, 16 kHz resampling,
and peak normalization.
