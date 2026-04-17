Yep — I went ahead and turned your two uploaded notebooks into a **Linux local-first “v1” pipeline kit** (scripts + sanity checks + a small Typer CLI), so you can stop living in Colab cells and start wiring this into a `/create-music` skill.

[Download the local-first pipeline kit](sandbox:/mnt/data/music_pipeline_skill_v1.zip)

## What’s inside and how it maps to your notebooks

### 1) MusicGen “modeled track” generation (AudioCraft)

Your **`BILL_EVANS_GENERATOR_N&TC.ipynb`** does:

* uninstall/reinstall torch (Colab workaround) 
* `git clone facebookresearch/audiocraft` then `pip install -e .` 
* set `checkpoints_path` to a folder containing a fine-tune pair 
* `MusicGen.get_pretrained(checkpoints)` and `generate()` for N seconds 

In the kit, this becomes:

* `pipelines/musicgen_generate.py`
* `cli.py musicgen-generate --checkpoint-dir ... --prompt ... --seconds 30 --out ...`

AudioCraft’s MusicGen docs are here for deeper options (melody conditioning, style, etc.). ([GitHub][1])

---

### 2) Singing voice conversion (RVC inference)

Your **`SINGING_VOICE_CLONING_Training&Inference.ipynb`**:

* clones the RVC WebUI repo 
* downloads pretrained f0 files from HF URLs (lj1995 + Ov2Super32kfix) 
* installs `requirements.txt` 
* runs inference by calling `tools/cmd/infer_cli.py` with args like `--f0up_key`, `--index_path`, `--f0method`, `--opt_path`, `--model_name`, etc. 

In the kit, this becomes:

* `scripts/rvc_setup.sh` (clone + download the same pretrains + install requirements)  
* `scripts/rvc_infer.sh` (deterministic: picks newest `added*.index`, sets `index_root` / `weight_root`, runs `infer_cli.py`) 

For reference, RVC maintainers explicitly point people to `infer_cli.py` for CLI/script use. ([GitHub][2])

---

## What you get immediately (local-first)

### A) Mix → stems (real audio stems, not MIDI)

This kit provides a practical baseline:

* **Demucs** 4-stem (vocals/drums/bass/other)
* Optional **python-audio-separator** (UVR model zoo) to add alternate candidates

Demucs’ “two-stems vocals” mode is documented (useful for quick vocal/instrumental splits). ([GitHub][3])
python-audio-separator is documented as a CLI/package for UVR-style models. ([GitHub][4])

### B) Sanity checks (non-negotiable)

Included:

* `sanity/check_env.sh` (ffmpeg + torch + imports)
* `sanity/check_alignment.py` (all stems same SR + same frames)
* `sanity/check_reconstruction.py` (mix ≈ sum(stems); fails if error too high)

### C) A small Typer CLI (so this becomes a skill later)

* `python cli.py separate-mix ...`
* `python cli.py qc-select ...`
* `python cli.py ingest-raw ...`
* `python cli.py musicgen-generate ...`

---

## How to run it (minimal commands)

```bash
unzip music_pipeline_skill_v1.zip
cd music_pipeline_skill_v1
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-core.txt
bash sanity/check_env.sh
```

**Stem extraction:**

```bash
python cli.py separate-mix --mix inputs/mix.wav --out work/ensemble --model htdemucs --with-audio-separator
python cli.py qc-select --mix inputs/mix.wav --candidates work/ensemble --out work/selected
python sanity/check_reconstruction.py --mix inputs/mix.wav --stems work/selected/stems
```

**RVC inference (voice conversion):**

```bash
bash scripts/rvc_setup.sh
bash scripts/rvc_infer.sh --model-name nico-500 --input inputs/guide_vocal.wav --output work/converted.wav --pitch 0 --f0method harvest
```

**MusicGen generate:**

```bash
pip install -r requirements-musicgen.txt
python cli.py musicgen-generate --checkpoint-dir /path/to/checkpoint_folder --prompt "intimate jazz trio" --seconds 30 --out work/musicgen.wav
```

---

## One important fix vs the notebook (brittleness removed)

Your RVC notebook’s “Create Training Files” cell incorrectly sets `file_path = dataset_folder` (a directory) and then calls `AudioSegment.from_file(file_path)` which is not a valid audio file path. 
It also redirects preprocess output to `/dev/null`, making its “check preprocess.log for success” unreliable. 
So: notebook is fine for a demo, but scripts need deterministic IO + real logs (the kit is set up that way).

---

## Next step (so this becomes your `/create-music` skill)

Once you run this successfully on 2–3 songs locally, the next concrete upgrade is:

1. Add a “music spec sheet” YAML emitter (like your KSML flow)
2. Make `cli.py` accept `--spec specs/foo.yml`
3. Emit `report.json` + artifacts into a stable folder structure so your orchestrator can quality-gate it

If you want, paste the skeleton of your `/create-movie` skill wrapper (run.sh + CLI calling convention), and I’ll adapt this kit to match your exact skill ergonomics (same command surface, same sanity gate style, same artifact layout).

[1]: https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md?utm_source=chatgpt.com "audiocraft/docs/MUSICGEN.md at main"
[2]: https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/issues/487?utm_source=chatgpt.com "Possible to use API or script? · Issue #487 · RVC-Project/ ..."
[3]: https://github.com/facebookresearch/demucs?utm_source=chatgpt.com "facebookresearch/demucs: Code for the paper Hybrid ..."
[4]: https://github.com/nomadkaraoke/python-audio-separator?utm_source=chatgpt.com "nomadkaraoke/python-audio-separator"
