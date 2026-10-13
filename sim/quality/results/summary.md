# Lyra mesh voice quality

Clean 12 s Harvard-sentence speech (espeak-ng, 16 kHz) encoded with Lyra v2
(google/lyra 1.3.2, `47698dad`) at 3.2 / 6 / 9.2 kbps. Each 20 ms frame is
passed through the mesh simulator. Frames whose fate is not `ok` — residual
packet error, congestion, or jitter-buffer late loss — are concealed by
Lyra's decoder. Arrival jitter inside the buffer does not time-warp audio.

Scores are ViSQOL speech-mode MOS-LQO (lattice mapper), DNSMOS P.835
(non-personalized OVRL / SIG / BAK), and STOI after aligning Lyra's delay.
ViSQOL and STOI compare against the clean fixture. DNSMOS does not use a
reference. The `reference` row is the fixture scored against itself.

`hold` rows are the usable-call cases (clean link, 2% residual loss, 3 hops).
`watch` rows are stress (5% loss, a jitter buffer shorter than the connection
interval, 5 hops, three calls on one classic-BLE relay). Both are gated.

## Scores

```
condition     role       bitrate  loss_fraction  sim_mte_p95_ms  visqol_mos  dnsmos_ovrl  stoi   passes_gate
------------  ---------  -------  -------------  --------------  ----------  -----------  -----  -----------
reference     reference  pcm      0.000                          4.527       2.746        1.000  yes        
clean         hold       3200     0.000          49.270          3.320       2.653        0.829  yes        
loss_2pct     hold       3200     0.020          49.270          3.322       2.686        0.825  yes        
loss_5pct     watch      3200     0.048          49.270          3.298       2.685        0.816  yes        
jitter_tight  watch      3200     0.333          44.270          2.737       2.321        0.759  yes        
hop3          hold       3200     0.007          79.270          3.297       2.636        0.827  yes        
hop5          watch      3200     0.015          109.270         3.334       2.628        0.825  yes        
relay_load    watch      3200     0.002          49.270          3.325       2.652        0.830  yes        
clean         hold       6000     0.000          50.760          3.776       2.680        0.877  yes        
loss_2pct     hold       6000     0.020          50.760          3.809       2.674        0.870  yes        
loss_5pct     watch      6000     0.048          50.760          3.713       2.682        0.861  yes        
jitter_tight  watch      6000     0.333          45.760          3.301       2.726        0.794  yes        
hop3          hold       6000     0.007          80.760          3.774       2.665        0.874  yes        
hop5          watch      6000     0.015          110.760         3.760       2.683        0.877  yes        
relay_load    watch      6000     0.002          52.280          3.781       2.681        0.877  yes        
clean         hold       9200     0.000          52.470          3.928       2.869        0.897  yes        
loss_2pct     hold       9200     0.020          52.470          3.907       2.825        0.890  yes        
loss_5pct     watch      9200     0.048          52.470          3.884       2.880        0.880  yes        
jitter_tight  watch      9200     0.333          47.470          3.522       2.570        0.814  yes        
hop3          hold       9200     0.007          82.470          3.928       2.837        0.895  yes        
hop5          watch      9200     0.015          112.470         3.893       2.813        0.896  yes        
relay_load    watch      9200     0.963          98.080          1.000       2.143        0.418  yes
```

## Gate

Floors are regression gates for the committed espeak-ng fixture and Lyra 1.3.2, about 0.15 MOS and 0.03 STOI under the measured scores and rounded down. Hold rows (clean, 2% residual loss, 3 hops) are the usable-call bar: ViSQOL 3.15 / 3.60 / 3.75 and STOI 0.80 / 0.84 / 0.86 at 3.2 / 6 / 9.2 kbps. DNSMOS P.835 OVRL is about 2.75 on the uncoded fixture because the speech is formant TTS, so its floor guards against a further drop rather than a studio-naturalness target. relay_load at 9.2 kbps is past the classic-BLE capacity cliff (about 96% of frames concealed); that cell's floor only checks that the collapsed scores still compute.

| condition | bitrate | min ViSQOL | min DNSMOS OVRL | min STOI |
| --- | --- | --- | --- | --- |
| reference | pcm | 4.4 | 2.6 | 0.99 |
| clean | 3200 | 3.15 | 2.45 | 0.8 |
| clean | 6000 | 3.6 | 2.5 | 0.84 |
| clean | 9200 | 3.75 | 2.65 | 0.86 |
| loss_2pct | 3200 | 3.15 | 2.45 | 0.8 |
| loss_2pct | 6000 | 3.6 | 2.5 | 0.84 |
| loss_2pct | 9200 | 3.75 | 2.65 | 0.86 |
| hop3 | 3200 | 3.15 | 2.45 | 0.8 |
| hop3 | 6000 | 3.6 | 2.5 | 0.84 |
| hop3 | 9200 | 3.75 | 2.65 | 0.86 |
| loss_5pct | 3200 | 3.1 | 2.5 | 0.78 |
| loss_5pct | 6000 | 3.55 | 2.5 | 0.83 |
| loss_5pct | 9200 | 3.7 | 2.7 | 0.85 |
| jitter_tight | 3200 | 2.55 | 2.15 | 0.72 |
| jitter_tight | 6000 | 3.1 | 2.55 | 0.76 |
| jitter_tight | 9200 | 3.35 | 2.4 | 0.78 |
| hop5 | 3200 | 3.15 | 2.45 | 0.8 |
| hop5 | 6000 | 3.6 | 2.5 | 0.84 |
| hop5 | 9200 | 3.75 | 2.65 | 0.86 |
| relay_load | 3200 | 3.15 | 2.45 | 0.8 |
| relay_load | 6000 | 3.6 | 2.5 | 0.84 |
| relay_load | 9200 | 1.0 | 1.9 | 0.35 |

Every gated cell meets its floor.

## Reproduce

```bash
cd sim
python3 -m venv .venv && .venv/bin/pip install -r requirements-quality.txt
bash quality/setup_lyra.sh          # once; needs gcc-11 and bazelisk
.venv/bin/python run_quality.py
.venv/bin/python run_quality.py --check
```
