"""emotion_weight_to_voice - weight_proof.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

# Connective tissue: verdict -> emotion -> intensity WEIGHT -> (exaggeration, cfg_weight)
# -> base ChatterboxTTS render with the production Embry ref clip.
# Proves the persona-dream weighting model produces measurably different tone.
import json, torch, torchaudio, torchaudio.functional as AF
from chatterbox.tts import ChatterboxTTS
# Authorized Embry voice, promoted 2026-07-28 (#1070/#1080). Was
# persona_dream_voice_refs/embry_authorized_ref_30s_8s.wav; that clip is not the
# one live Chatterbox renders were ever conditioned on. See
# skills/persona-dream/scripts/embry_voice_reference.py. Receipts already written
# still name the old clip and are deliberately not rewritten.
REF="/data/embry_ref.wav"
TEXT="I already told you where I stand. Do not ask me again."

def weighted_emotion_to_knobs(valence, intensity):
    # intensity in [0,1] is the WEIGHT (operator model: intensity of success/failure weights the emotion).
    # It scales expressive exaggeration. valence in [-1,1]: negative=guarded (lower cfg), positive=open.
    exaggeration = round(0.3 + 0.9*intensity, 3)              # 0.3 muted .. 1.2 intense
    cfg_weight   = round(0.5 - 0.2*max(0.0, -valence), 3)     # guarded -> 0.3, open -> 0.5
    return exaggeration, cfg_weight

# verdict -> (emotion label, valence). intensity is supplied separately as the weight.
CASES = [
    ("success", "relieved_warm",  +0.6, 0.2),   # low-weight success
    ("success", "relieved_warm",  +0.6, 0.9),   # high-weight success
    ("failure", "firm_guarded",   -0.8, 0.2),   # low-weight failure
    ("failure", "firm_guarded",   -0.8, 0.9),   # high-weight failure
]
m = ChatterboxTTS.from_pretrained(device="cpu"); sr=m.sr
def meas(wav):
    w=wav.squeeze(); rms=float(w.pow(2).mean().sqrt())
    f0=AF.detect_pitch_frequency(w.unsqueeze(0),sr).squeeze(); v=f0[(f0>60)&(f0<400)]
    return dict(dur_s=round(w.numel()/sr,3),
                rms_dbfs=round(20*torch.log10(torch.tensor(rms+1e-9)).item(),2),
                f0_mean_hz=round(float(v.mean()),1) if v.numel() else 0.0)
rows=[]
for verdict, emotion, valence, intensity in CASES:
    ex,cfg = weighted_emotion_to_knobs(valence, intensity)
    torch.manual_seed(1234)
    wav=m.generate(TEXT, audio_prompt_path=REF, exaggeration=ex, cfg_weight=cfg)
    name=f"{verdict}_w{int(intensity*10):02d}"
    torchaudio.save(f"/tmp/ew_{name}.wav", wav, sr)
    r=meas(wav); r.update(verdict=verdict, emotion=emotion, valence=valence,
                          intensity_weight=intensity, exaggeration=ex, cfg_weight=cfg, name=name)
    rows.append(r); print("done",name,flush=True)
print("EW_JSON "+json.dumps({"ref":REF,"text":TEXT,"mapping":"exagg=0.3+0.9*intensity; cfg=0.5-0.2*max(0,-valence)","rows":rows}))
