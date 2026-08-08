"""base_emotion_proof - emotion_proof.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json, torch, torchaudio, torchaudio.functional as AF
from chatterbox.tts import ChatterboxTTS
TEXT = "I already told you where I stand. Do not ask me again."
CONDS = [
    ("calm",       dict(exaggeration=0.3, cfg_weight=0.5)),
    ("default",    dict(exaggeration=0.5, cfg_weight=0.5)),
    ("expressive", dict(exaggeration=0.8, cfg_weight=0.3)),
    ("intense",    dict(exaggeration=1.2, cfg_weight=0.3)),
]
m = ChatterboxTTS.from_pretrained(device="cpu")
sr = m.sr
def measure(wav):
    w = wav.squeeze()
    dur = w.numel() / sr
    rms = float(w.pow(2).mean().sqrt())
    # F0 over voiced frames
    f0 = AF.detect_pitch_frequency(w.unsqueeze(0), sr).squeeze()
    voiced = f0[(f0 > 60) & (f0 < 400)]
    f0_mean = float(voiced.mean()) if voiced.numel() else 0.0
    f0_std  = float(voiced.std())  if voiced.numel() > 1 else 0.0
    f0_rng  = float(voiced.max()-voiced.min()) if voiced.numel() else 0.0
    return dict(dur_s=round(dur,3), rms=round(rms,5),
                rms_dbfs=round(20*torch.log10(torch.tensor(rms+1e-9)).item(),2),
                f0_mean_hz=round(f0_mean,1), f0_std_hz=round(f0_std,1), f0_range_hz=round(f0_rng,1))
rows=[]
for name,kw in CONDS:
    torch.manual_seed(1234)  # fix sampling so exaggeration/cfg is the ONLY variable
    wav = m.generate(TEXT, **kw)
    torchaudio.save(f"/tmp/emo_{name}.wav", wav, sr)
    r = measure(wav); r.update(cond=name, **kw)
    rows.append(r); print("done", name, flush=True)
print("RESULT_JSON " + json.dumps({"text":TEXT,"sr":sr,"seed":1234,"rows":rows}))
