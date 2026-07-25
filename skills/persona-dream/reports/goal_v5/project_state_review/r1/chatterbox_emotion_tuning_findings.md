# How persona-dream can (and cannot) tune chatterbox emotion — MEASURED 2026-07-25

Concrete question: does any persona-dream lever actually force/tune the *acoustic*
emotion of the chatterbox voice? Tested live on the deployed Turbo /synthesize
(port 8018), same line, varied knobs, measured WAVs (ffprobe duration + ffmpeg
mean_volume).

## Measured: the current knobs do NOT tune emotion on Turbo
| setting            | dur   | mean_vol |
|--------------------|-------|----------|
| baseline           | 3.88s | -29.2 dB |
| tone=firm_boundary | 3.40s | -29.8 dB |
| tone=warm_open     | 3.56s | -29.9 dB |
| delivery=weary     | 3.52s | -28.1 dB |
| temperature 0.4    | 3.56s | -29.1 dB |
| temperature 0.9    | 4.16s | -29.8 dB |

firm_boundary vs warm_open are acoustically the same (-29.8 vs -29.9 dB). So
`tone`/`delivery_stage` are NOT working affect knobs; temperature only jitters
sampling. Combined with the verified /presets fact that Turbo IGNORES
`exaggeration` and `cfg_weight` and does not interpret tags, the deployed engine
has NO validated acoustic-emotion knob. The persona-dream 5-row ToM->tone table
and the arc-voice text channel change WHAT is said, not HOW it sounds.

## The only real levers to actually force/tune emotion
1. **Reference-clip conditioning (ref_audio).** Turbo transfers the reference
   clip's vocal register. BUT: passing a host filesystem path as `ref_audio`
   returns HTTP 404 (the service resolved the default clip mounted at boot;
   arbitrary host paths are not resolvable). To use this you must MOUNT a
   per-emotion clip bank into the container and select the clip by the persona's
   affect. This is the highest-ROI path that keeps Turbo (Kimi's panel position).
2. **Switch to base Chatterbox (non-Turbo)**, where `exaggeration`/`cfg_weight`
   are the actual expressiveness controls; drive `exaggeration` from the
   persona's affect intensity (webgpt/Claude panel position, cleaner but costlier).

## Bottom line
persona-dream currently tunes emotion only in TEXT (word choice), verified. To
tune the VOICE's emotion acoustically requires either a mounted emotional
ref-clip bank + affect->clip selection, or a base-Chatterbox engine driving
exaggeration from affect. No amount of tone/delivery/temperature tuning will do
it on Turbo.
