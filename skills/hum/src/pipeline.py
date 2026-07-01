"""Humming pipeline: orchestrates download, stem, convert, cache."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from .cache import HumCache, HumTrack

console = Console()

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent  # .pi/skills/
STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"

# Python script run inside Docker to generate filelist + config.
# F0 files use .wav.npy naming (e.g. 0_0.wav.npy), not .npy.
_FILELIST_SCRIPT = """
import os, json
slug = '{slug}'
log_dir = f'/app/logs/{{slug}}'
gt = f'{{log_dir}}/0_gt_wavs'
feat = f'{{log_dir}}/3_feature768'
f0 = f'{{log_dir}}/2a_f0'
f0nsf = f'{{log_dir}}/2b-f0nsf'
names = sorted([n.replace('.wav','') for n in os.listdir(gt) if n.endswith('.wav')])
opt = []
for name in names:
    paths = [f'{{gt}}/{{name}}.wav', f'{{feat}}/{{name}}.npy',
             f'{{f0}}/{{name}}.wav.npy', f'{{f0nsf}}/{{name}}.wav.npy']
    if all(os.path.exists(p) for p in paths):
        opt.append('|'.join(paths) + '|0')
with open(f'{{log_dir}}/filelist.txt','w') as f: f.write('\\n'.join(opt))
config = {{'train':{{'log_interval':200,'seed':1234,'epochs':{epochs},'learning_rate':1e-4,
'betas':[0.8,0.99],'eps':1e-9,'batch_size':4,'fp16_run':True,'lr_decay':0.999875,
'segment_size':12800,'init_lr_ratio':1,'warmup_epochs':0,'c_mel':45,'c_kl':1.0}},
'data':{{'max_wav_value':32768.0,'sampling_rate':40000,'filter_length':2048,'hop_length':400,
'win_length':2048,'n_mel_channels':125,'mel_fmin':0.0,'mel_fmax':None,
'training_files':f'{{log_dir}}/filelist.txt'}},
'model':{{'inter_channels':192,'hidden_channels':192,'filter_channels':768,'n_heads':2,
'n_layers':6,'kernel_size':3,'p_dropout':0,'resblock':'1',
'resblock_kernel_sizes':[3,7,11],'resblock_dilation_sizes':[[1,3,5],[1,3,5],[1,3,5]],
'upsample_rates':[10,10,2,2],'upsample_initial_channel':512,
'upsample_kernel_sizes':[16,16,4,4],'use_spectral_norm':False,
'gin_channels':256,'spk_embed_dim':109}},
's2_ckpt_dir':f'{{log_dir}}','save_every_epoch':25,'name':slug,
'version':'v2','sample_rate':'40k','if_f0':1}}
with open(f'{{log_dir}}/config.json','w') as f: json.dump(config,f,indent=2)
print(f'Filelist: {{len(opt)}} entries, config written')
"""

# Python script run inside Docker to build FAISS index and export model.
_INDEX_EXPORT_SCRIPT = """
import os, glob, numpy as np, faiss, shutil
slug = '{slug}'
persona = '{persona}'
log_dir = f'/app/logs/{{slug}}'
feat_dir = f'{{log_dir}}/3_feature768'
features = []
for f in sorted(os.listdir(feat_dir)):
    if f.endswith('.npy'):
        features.append(np.load(os.path.join(feat_dir, f)))
if not features:
    print('No features'); exit(1)
big_npy = np.concatenate(features, axis=0).astype('float32')
n_ivf = min(int(16 * (big_npy.shape[0] ** 0.5)), big_npy.shape[0] // 39)
n_ivf = max(n_ivf, 1)
index = faiss.index_factory(768, f'IVF{{n_ivf}},Flat')
index.train(big_npy)
index.add(big_npy)
index_path = f'{{log_dir}}/added_index.index'
faiss.write_index(index, index_path)
# Export: find latest G_*.pth checkpoint
checkpoints = sorted(glob.glob(f'{{log_dir}}/G_*.pth'))
if not checkpoints:
    print('No checkpoints found'); exit(1)
latest = checkpoints[-1]
# Export to /app/logs export dir (host copies from rvc-webui/logs/ to rvc-models/)
export_dir = f'{{log_dir}}/export'
os.makedirs(export_dir, exist_ok=True)
shutil.copy2(latest, os.path.join(export_dir, f'{{slug}}.pth'))
shutil.copy2(index_path, os.path.join(export_dir, f'{{slug}}.index'))
print(f'EXPORT_DIR={{export_dir}}')
"""


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # Might be a bare video ID
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    raise ValueError(f"Cannot extract video ID from: {url}")


def _slugify(text: str) -> str:
    """Convert text to filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s-]+", "_", slug).strip("_")
    return slug


class HumPipeline:
    """Orchestrates the full humming pipeline using existing skills."""

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self.cache = HumCache(persona=persona)
        self.persona_samples_dir = STORAGE_ROOT / "personas" / persona / "tts_output"
        self.rvc_models_dir = STORAGE_ROOT / "music" / "rvc-models" / "voice" / persona

    def add(
        self,
        url: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        mood: Optional[list[str]] = None,
        bridges: Optional[list[str]] = None,
        persona_connection: str = "",
        pitch: int = 0,
        f0method: str = "rmvpe",
    ) -> dict:
        """Full pipeline: download → stem → convert → cache."""
        video_id = _extract_video_id(url)

        with tempfile.TemporaryDirectory(prefix="hum_") as tmpdir:
            tmpdir = Path(tmpdir)

            # ── Step 1: Download audio ──
            console.print("[bold cyan]Step 1/4:[/bold cyan] Downloading audio...")
            download_result = self._download_audio(url, tmpdir)
            if not download_result:
                return {"status": "error", "error": "Download failed"}

            audio_path, detected_title = download_result
            if not title:
                title = detected_title or video_id

            track_id = _slugify(title)
            console.print(f"  Downloaded: {audio_path.name} ({audio_path.stat().st_size // 1024}KB)")

            # ── Step 2: Stem separation ──
            console.print("[bold cyan]Step 2/4:[/bold cyan] Separating vocals...")
            vocals_path = self._separate_vocals(audio_path, tmpdir)
            if not vocals_path:
                return {"status": "error", "error": "Stem separation failed"}
            console.print(f"  Vocals: {vocals_path.name}")

            # ── Step 3: RVC voice conversion ──
            console.print("[bold cyan]Step 3/4:[/bold cyan] Converting to {}'s voice...".format(self.persona))
            if not self._has_rvc_model():
                return {
                    "status": "error",
                    "error": f"No RVC model for {self.persona}. Run: ./run.sh train --persona {self.persona}",
                }

            converted_path = tmpdir / f"{track_id}_converted.wav"
            ok = self._rvc_convert(vocals_path, converted_path, pitch, f0method)
            if not ok:
                return {"status": "error", "error": "RVC voice conversion failed"}
            console.print(f"  Converted: {converted_path.name}")

            # ── Step 4: Cache with metadata ──
            console.print("[bold cyan]Step 4/4:[/bold cyan] Caching...")

            # Get duration
            duration_s = self._get_duration(converted_path)

            track = HumTrack(
                id=track_id,
                title=title,
                artist=artist or "",
                source_url=url,
                source_video_id=video_id,
                bridge_attributes=bridges or [],
                mood=mood or [],
                persona_connection=persona_connection,
                duration_s=duration_s,
                pitch_shift=pitch,
                f0_method=f0method,
                created=datetime.now().isoformat(),
                forbidden=False,
            )

            cached_path = self.cache.add_track(track, converted_path)
            console.print(f"  Cached: {cached_path}")

        return {
            "status": "ok",
            "track_id": track_id,
            "audio_path": str(cached_path),
            "duration_s": duration_s,
        }

    def train_voice(self, epochs: int = 200) -> dict:
        """Train RVC voice model for persona using Docker RVC pipeline directly.

        Stages persona TTS samples into the RVC training directory, ensures the
        Docker container is running, then runs: preprocess → f0 → features →
        filelist → train → index → export.
        """
        if not self.persona_samples_dir.exists():
            return {
                "status": "error",
                "error": f"No TTS samples at {self.persona_samples_dir}",
            }

        samples = list(self.persona_samples_dir.glob("*.wav"))
        if not samples:
            return {
                "status": "error",
                "error": f"No WAV files in {self.persona_samples_dir}",
            }

        console.print(f"  Found {len(samples)} voice samples")

        # Stage samples into RVC training directory
        import shutil
        training_data = STORAGE_ROOT / "music" / "rvc-training" / self.persona / "vocals_all"
        training_data.mkdir(parents=True, exist_ok=True)

        staged = 0
        for wav in samples:
            dest = training_data / wav.name
            if not dest.exists():
                shutil.copy2(wav, dest)
                staged += 1
        console.print(f"  Staged {staged} new samples to {training_data}")

        # Ensure Docker container is running
        docker_name = "rvc-training"
        if not self._ensure_docker(docker_name):
            return {"status": "error", "error": "Failed to start RVC Docker container"}

        slug = self.persona
        datasets_path = f"/app/datasets/{slug}/vocals_all"
        logs_path = f"/app/logs/{slug}"

        def docker_exec(cmd: list[str], desc: str) -> subprocess.CompletedProcess:
            full = ["docker", "exec", docker_name] + cmd
            console.print(f"  [dim]{desc}...[/dim]")
            return subprocess.run(full, capture_output=True, text=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

        # Step 1: Create logs directory and preprocess
        console.print("[bold cyan]  Step 1/6:[/bold cyan] Preprocessing...")
        subprocess.run(["docker", "exec", docker_name, "mkdir", "-p", logs_path],
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        r = docker_exec(
            ["python", "/app/infer/modules/train/preprocess.py",
             datasets_path, "40000", "4", logs_path, "False", "3.7"],
            "Slicing audio into training segments",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"Preprocess failed: {r.stderr[:300]}"}

        # Step 2: Extract F0 (pitch)
        console.print("[bold cyan]  Step 2/6:[/bold cyan] Extracting pitch (F0)...",
             env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        r = docker_exec(
            ["python", "/app/infer/modules/train/extract/extract_f0_rmvpe.py",
             "1", "0", "0", logs_path, "True"],
            "RMVPE pitch extraction",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"F0 extraction failed: {r.stderr[:300]}"}

        # Step 3: Extract features (Hubert embeddings)
        console.print("[bold cyan]  Step 3/6:[/bold cyan] Extracting Hubert features...")
        r = docker_exec(
            ["python", "/app/infer/modules/train/extract_feature_print.py",
             "cuda:0", "1", "0", logs_path, "v2", "True"],
            "768-dim feature extraction",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"Feature extraction failed: {r.stderr[:300]}"}

        # Step 4: Generate filelist (with correct F0 .wav.npy naming)
        console.print("[bold cyan]  Step 4/6:[/bold cyan] Generating training filelist...")
        r = docker_exec(
            ["python3", "-c", _FILELIST_SCRIPT.format(slug=slug, epochs=epochs)],
            "Building filelist and config",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"Filelist generation failed: {r.stderr[:300]}"}

        # Step 5: Train
        console.print(f"[bold cyan]  Step 5/6:[/bold cyan] Training ({epochs} epochs)...")
        r = docker_exec(
            ["python", "/app/infer/modules/train/train.py",
             "-e", slug, "-sr", "40k", "-f0", "1", "-bs", "4",
             "-g", "0", "-te", str(epochs), "-se", "25",
             "-pg", "assets/pretrained_v2/f0G40k.pth",
             "-pd", "assets/pretrained_v2/f0D40k.pth",
             "-l", "0", "-c", "0", "-sw", "1", "-v", "v2"],
            f"RVC v2 training for {epochs} epochs",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"Training failed: {r.stderr[:300]}"}

        # Step 6: Build FAISS index and export model
        console.print("[bold cyan]  Step 6/6:[/bold cyan] Building index and exporting model...")
        r = docker_exec(
            ["python3", "-c", _INDEX_EXPORT_SCRIPT.format(
                slug=slug, persona=self.persona)],
            "FAISS index + model export",
        )
        if r.returncode != 0:
            return {"status": "error", "error": f"Index/export failed: {r.stderr[:300]}"}

        # Copy exported model from Docker volume mount to rvc-models directory
        import shutil as _shutil
        host_export = STORAGE_ROOT / "music" / "rvc-webui" / "logs" / slug / "export"
        self.rvc_models_dir.mkdir(parents=True, exist_ok=True)
        for ext in ("pth", "index"):
            src = host_export / f"{slug}.{ext}"
            dst = self.rvc_models_dir / f"{slug}.{ext}"
            if src.exists():
                _shutil.copy2(src, dst)
                console.print(f"  Exported: {dst}")

        # Check model was produced
        model_files = list(self.rvc_models_dir.glob("*.pth"))
        if model_files:
            return {
                "status": "ok",
                "model_path": str(model_files[0]),
                "sample_count": len(samples),
                "epochs": epochs,
            }
        return {"status": "error", "error": "Training completed but no model file found"}

    def _ensure_docker(self, container_name: str) -> bool:
        """Ensure the RVC Docker container is running."""
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if r.returncode == 0 and "true" in r.stdout:
            return True

        console.print("  Starting RVC Docker container...")
        r = subprocess.run(
            ["docker", "run", "-d", "--gpus", "all",
             "--name", container_name,
             "--shm-size=8g",
             "-v", f"{STORAGE_ROOT}/music/rvc-webui/logs:/app/logs",
             "-v", f"{STORAGE_ROOT}/music/rvc-training:/app/datasets",
             "cherrymint/rvc_webui:rvc_boss"],
            capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        return r.returncode == 0

    def _download_audio(self, url: str, out_dir: Path) -> Optional[tuple[Path, str]]:
        """Download audio from YouTube via ingest-youtube skill."""
        import sys as _sys

        _iy_dir = str(SKILLS_ROOT / "ingest-youtube")
        if _iy_dir not in _sys.path:
            _sys.path.insert(0, _iy_dir)

        from youtube_transcripts.downloader import download_audio, fetch_video_metadata

        video_id = _extract_video_id(url)
        audio_path, error = download_audio(video_id, out_dir)

        if error or audio_path is None:
            console.print(f"  [red]Download error:[/red] {error}")
            return None

        # Try to get the title from metadata
        meta = fetch_video_metadata(video_id)
        title = meta.get("title") if meta else None

        return audio_path, title

    def _separate_vocals(self, audio_path: Path, out_dir: Path) -> Optional[Path]:
        """Separate vocals using create-stems skill.

        create-stems cli.py takes options directly (no subcommand):
          uv run python cli.py --mix song.wav --out ./stems --instrument vocals
        """
        stems_skill_dir = SKILLS_ROOT / "create-stems"
        stems_out = out_dir / "stems"

        result = subprocess.run(
            [
                "uv", "run", "python", "cli.py",
                "--mix", str(audio_path),
                "--out", str(stems_out),
                "--instrument", "vocals",
            ],
            cwd=str(stems_skill_dir),
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

        if result.returncode != 0:
            console.print(f"  [red]Stem separation error:[/red] {result.stderr.strip()[:200]}")
            return None

        # Find vocals.wav in output
        for vocals in stems_out.rglob("vocals.wav"):
            return vocals

        console.print("  [red]No vocals.wav found in stems output[/red]")
        return None

    def _has_rvc_model(self) -> bool:
        """Check if persona has a trained RVC model."""
        if self.rvc_models_dir.exists():
            return bool(list(self.rvc_models_dir.glob("*.pth")))
        return False

    def _rvc_convert(
        self,
        input_path: Path,
        output_path: Path,
        pitch: int = 0,
        f0method: str = "rmvpe",
    ) -> bool:
        """Convert vocals to persona voice using create-music rvc-infer."""
        music_skill = SKILLS_ROOT / "create-music" / "run.sh"

        result = subprocess.run(
            [
                str(music_skill), "rvc-infer",
                "--model-name", self.persona,
                "--input", str(input_path),
                "--output", str(output_path),
                "--pitch", str(pitch),
                "--f0method", f0method,
            ],
            cwd=str(music_skill.parent),
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

        if result.returncode != 0:
            console.print(f"  [red]RVC error:[/red] {result.stderr.strip()[:200]}")
            return False

        return output_path.exists()

    def _get_duration(self, audio_path: Path) -> Optional[float]:
        """Get audio duration in seconds via ffprobe."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0 and result.stdout.strip():
            return round(float(result.stdout.strip()), 1)
        return None
