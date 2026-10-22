# Live waveform smoothness — 30 Hz playout buffer

Date: 2026-10-18
Scope: Workbench ▸ Live waveform/spectrogram (not Replay).

## 1. Diagnosis (measured, not guessed)

Connected to **IU.PAB** through IRIS SeedLink and instrumented
`WaveformPanel.update_from_snapshot`:

| Metric | Measured |
|---|---|
| Refresh timer, actual | **30.78 Hz** (median frame 32.4 ms, p95 43.1 ms) |
| `update_from_snapshot` draw time | **0.24 ms** median / 0.31 ms p95 |
| Displayed data timestamp changes | **2 changes in 30 s** (8.7 s and 6.9 s) |
| SeedLink packets | **~13 s of data per packet** (BHZ 523 samples @40 Hz = 13.05 s) |

So the renderer was already at 30 Hz; the "卡顿" was the **data cadence**:
SeedLink delivered 13 s of samples at once, then the waveform stood still
until the next packet. Increasing FPS cannot fix missing samples.

Server probes (2026-06): IRIS `rtserve.iris.washington.edu` accepted IU.PAB; the
current EarthScope endpoint is `rtserve.earthscope.org:18000`;
EIDA IPGP/KNMI/INGV were unreachable, BGR rejected IU.PAB. No smaller-packet
endpoint was available.

## 2. Solution — prefill + playout cursor

```
SeedLink ─┐
          ├─ RingBuffer ── read_window(end_offset=12 s) ── Waveform 30 Hz
dataselect┘       ▲                                         (smooth cursor)
 (60 s history)   │
          detector / MMI use read_window() at latest (no delay)
```

* **History prefill**: after the first live packet, the controller fetches the
  previous 60 s from FDSN dataselect in a background thread and prepends it to
  the ring buffer. First packet only contains ~13 s, not enough to run a
  12 s-delayed window.
* **Playout cursor**: a monotonic `display_end` advances with wall time every
  refresh tick. The waveform reads `read_window(display_window,
  end_offset_s=latest - display_end)`, so each frame moves the trace by
  ~33 ms even when no new packet has arrived. The cursor holds at
  `latest - 0.2 s` if data is exhausted and resynchronises if the lag exceeds
  30 s.
* **Detection / MMI stay live**: STA/LTA and the MMI chip keep using the
  latest window, so alerts are not delayed by the visual buffer. The latency
  label now shows the age of the **displayed** waveform (includes the buffer).
* **Precise timer**: `Qt.PreciseTimer` avoids CoarseTimer jitter.

New buffer API (tested):

* `RingBuffer.read_window(seconds, end_offset_s=...)`
* `RingBuffer.prepend_history(...)`
* GSN `BH1`/`BH2` mapped to N/E in the prefill converter (the live SeedLink
  source already did this; dataselect returned BH1/BH2).

## 3. Result

Same IU.PAB session, after prefill:

| Metric | Before | After |
|---|---|---|
| Update rate | 30.78 Hz | **29.8 Hz** (p95 35.2 ms) |
| Displayed time changes | 2 / 641 frames | **655 / 676 frames** (97 %) |
| Draw time | 0.24 ms | **0.26 ms** |
| Three channels in view | Z/N/E uneven | **Z/N/E full 30 s** |
| Waveform motion between frames 200 ms apart | static | **20 358 changed pixels** in waveform area |

Screenshots: `23_workbench_smooth_a.png` / `24_workbench_smooth_b.png`
(two frames 200 ms apart; waveform + spectrogram both moved).

## 3b. Toggle

The Workbench sidebar now exposes **Smooth display** (checked by default).
Unchecking it switches to Realtime immediately (no playout delay); checking it
again resets the cursor to `latest - 12 s` when history is available.

## 4. Trade-offs / limits

* **Visual latency ≈ 12–15 s** on IRIS stations. This is the unavoidable cost
  of turning 13 s bursts into continuous motion; the status bar shows a
  one-time "Smooth display buffer +12 s" hint and the latency label reflects
  the displayed data. The MMI chip and STA/LTA remain current.
* **Prefill requires FDSN dataselect**. LAN Raspberry Shake stations (AM) or
  networks without a public dataselect history fall back to the original
  jump-on-packet behaviour; no fake samples are inserted.
* **Prefill failure is silent** (debug log only): the app keeps working, just
  without smoothing. The connection itself is unchanged (~13 s to first
  packet due to SeedLink grace + IRIS batching).
* If the source stops for >30 s, the cursor resynchronises once rather than
  accumulating minutes of delay.
