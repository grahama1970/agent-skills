# Project Knowledge: agent-skills

**Last updated:** 2026-06-20 13:39 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-06-19 /hum dynamic-humming research boundary: The product question is whether Embry can dynamically hum mm/oo/ng melodies from MIDI/F0/notes in her own voice, not merely whether static guide-audio clips can be converted. Static hum-cache production remains a fallback, not the primary research target.
- Approaches that did not satisfy the dynamic goal: Suno followed prompts inconsistently and added backing/harmony or missed melody; ACE-Step produced unusable low-noise output and did not prove independent target-voice conditioning; Seed-VC/Orpheus conversion produced broken/gibberish or artifacted outputs in tests; Kits/RVC voice conversion produced the best static artifacts so far but only re-skins an existing guide performance and does not teach Embry to hum arbitrary melodies.
- Kits evidence: trained model embry_orpheus_hum_feas_20260619 id 2313159 became isUsable=true; successful conversion jobs 51373634, 51373783, and 51373946 wrote local WAVs under /tmp/embry-kits-hum-feasibility/conversion/. Human listening found artifacts; Norwegian guide sounded better but preserved the wrong melody. These are staged feasibility artifacts only, not cache-ready hums.
- 2026-06-19 DiffSinger MVP status: cloned OpenVPI DiffSinger at /home/graham/workspace/experiments/diffsinger-mvp/DiffSinger commit 39fd90b; created and structurally validated DS fixture /home/graham/workspace/experiments/diffsinger-mvp/mvp/outputs/hawaiian_war_chant_mu_8s.ds (sha256 4672460c3cf57caafa29c52fdc879dc3e97e5ab10e0d72355f7ab3d76962242d, 1 segment, 28 phones, 15 notes, 7.35s, 1470 F0 frames). This proves only score-format mechanics, not audio generation or real Hawaiian War Chant melody.
- DiffSinger MVP blocker: inference preflight command python3 scripts/infer.py acoustic /home/graham/workspace/experiments/diffsinger-mvp/mvp/outputs/hawaiian_war_chant_mu_8s.ds --exp mvp_missing --mel failed with ModuleNotFoundError: No module named 'click' before model loading. The clone also contains no acoustic voice checkpoint beyond checkpoints/.gitkeep, and a vocoder checkpoint must be acquired separately. Report: /home/graham/workspace/experiments/diffsinger-mvp/mvp/docs/MVP_REPORT.md.
- Embry data preflight for DiffSinger: immediately available Orpheus/Embry candidate WAVs measured 10 files totaling 65.392s (1.09 min), mostly 24 kHz mono speech/reference. This is not enough for credible DiffSinger Embry singing/humming training and lacks required singing/humming labels; it can support only a dataset-skeleton preflight.
- 2026-06-19 DiffSinger POC update: public Nishiren Diffsinger v2.0 voicebank downloaded to /home/graham/workspace/experiments/diffsinger-mvp/assets/nishiren/Nishiren.Diffsinger.v2.0.zip (938980498 bytes, sha256 5caadbb526b4cc5800f39e42952708ff24320b8f70e835c70319ed73f92dc99b). Package contains dsmain/acoustic.onnx and bundled dsvocoder/gda_pc-hifigan.onnx; phoneme inventory includes en/mm, en/nn, en/ng, and en/uw.
- DiffSinger direct ONNX generic smoke succeeded: /home/graham/workspace/experiments/diffsinger-mvp/mvp/scripts/render_nishiren_direct_onnx.py rendered /home/graham/workspace/experiments/diffsinger-mvp/mvp/outputs/nishiren_nn_hawaiian_phrase_direct_onnx.wav using repeated en/nn carrier, explicit F0 notes, Nishiren Standard speaker embedding, acoustic ONNX, and bundled vocoder. Exit code 0; WAV 44.1 kHz mono 7.430385s, sha256 04cd03fd357a8b79f966f1da8287750a5f247ca15ad987c2a8622a9f3da85c24; non-silent and unclipped by numeric checks. Human listening and verified Hawaiian War Chant melody remain missing.
- Correction after human listening gate: /home/graham/workspace/experiments/diffsinger-mvp/mvp/outputs/nishiren_nn_hawaiian_phrase_direct_onnx.wav is rejected as unusable for the product goal. Human review described it as junk/gibberish MIDI-autotuned. Numeric non-silence/unclipped checks are insufficient evidence for musical usability. Treat the DiffSinger direct-ONNX result as model-execution proof only, not a viable hum direction.
- 2026-06-20 /hum added deterministic articulated PSOLA diagnostic renderer from /home/graham/Downloads/hawaiian_war_chant_articulated_psola_v1.py as src/articulated_psola_renderer.py with ./run.sh render-articulated-psola. It writes a MIDI+articulation-sample review bundle and preserves local QA failure as non-approval; it is not an Embry dynamic humming solution or cache publication path.
- 2026-06-20 correction: /hum now includes the missing ElevenLabs articulation inventory generation step. ./run.sh generate-elevenlabs-articulations calls ElevenLabs TTS for the 12 required non-lexical PSOLA tokens, stores raw API audio, converts samples/*.wav, writes request receipts/manifests, and feeds ./run.sh render-articulated-psola via --samples. This remains diagnostic and requires listening review.
- 2026-06-20 correction: ElevenLabs articulation inventory generation now uses Sound Effects /v1/sound-generation, not Text-to-Speech. The command no longer requires a voice ID; it sends phonetic texture prompts with duration_seconds and prompt_influence, converts returned MP3s to samples/*.wav, and keeps Speech-to-Speech/native audio as a separate imported-guide path for cadence/phoneme transfer.
- 2026-06-20 live Sound Effects artifact: ./run.sh generate-elevenlabs-articulations --output-dir /tmp/hwc_articulations_sfx --duration-seconds 1.2 --prompt-influence 0.72 --json succeeded. It wrote 12 raw MP3s and 12 converted 44.1 kHz 1.2s WAV samples under /tmp/hwc_articulations_sfx, with manifest and receipts. This is artifact proof only; listening review remains required.
- 2026-06-20 live STS guide artifact: downloaded YouTube video nLpxOuFX4nM to /tmp/hwc_sts_guide/source/nLpxOuFX4nM.wav, separated vocals with create-stems/Demucs to /tmp/hwc_sts_guide/stems/htdemucs_6s/nLpxOuFX4nM/vocals.wav, selected an automatic 20s high-RMS vocal candidate at 36.0s, and generated ElevenLabs Speech-to-Speech guide /tmp/hwc_sts_guide/elevenlabs_sts/lily_velvety_actress_api_available_guide.wav using API-available Lily voice. Requested library voice Vnqlgu3fdiFwisAye1qH returned paid_plan_required. Listening and rights review remain required.
- 2026-06-20 STS voice retry after ElevenLabs Starter activation: provided voice IDs Vnqlgu3fdiFwisAye1qH and oVXQ3H21hRI9OtM4YH5K now both succeeded via /v1/speech-to-speech. Generated WAV guides: /tmp/hwc_sts_guide/elevenlabs_sts/provided_voice_1_Vnqlgu3fdiFwisAye1qH_guide.wav and /tmp/hwc_sts_guide/elevenlabs_sts/provided_voice_2_oVXQ3H21hRI9OtM4YH5K_guide.wav. Both are 44.1 kHz and 20.016s; listening review remains required.
- 2026-06-20 /hum ElevenLabs STS listening lesson: Hawaiian Eye refined winner is S3 raw-guide controlled: hawaiian_eye_1959_wistful_female_pop__light_rasp__0p85x__controlled__s0p50__sty0p15.wav. Settings: Light Rasp voice, raw 0.85x Demucs vocal guide, stability 0.50, similarity_boost 0.84, style 0.15. Human selected it because it is most stable and does not distort during vocal glissando. Why it works: raw guide preserves smooth glissando shape; low style reduces expressive over-amplification; moderate stability controls wobble without flattening; higher similarity keeps voice identity locked. What does not work as well: higher style can exaggerate glides into artifacts; pitch-corrected guide can improve pitch center but may disturb continuous vocal-slide feel. Prior Hawaiian War Chant winner remains Light Rasp 0.85x at /tmp/watch-audio-merge/elevenlabs_final_light_rasp_0p85_hwc_sts.wav, with 0.90x too fast and 0.80x slower/ceremonial.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-19 | Initialize project knowledge | Enable shared human/agent context |
| 2026-06-19 | Pivot dynamic research to DiffSinger/OpenVPI MVP | OpenVPI DiffSinger is an actual singing voice synthesis stack with pitch/melody controllability and dataset tooling, while Kits/RVC are guide-audio conversion and sampled libraries are static/offline rendering fallbacks. First MVP must prove note/F0-to-nonlexical-vocal generation before any Embry training or cloud upload. |
| 2026-06-19 | Reject DiffSinger direct-ONNX shortcut as product evidence | The direct ONNX renderer produced a non-silent WAV but failed the human listening gate; future work must not present numeric audio checks as proof of usable humming. Any further DiffSinger work must use a proper OpenUTAU/render workflow or be explicitly bounded to one final experiment before pivoting. |
| 2026-06-20 | Use raw-guide controlled S3 as Hawaiian Eye refined winner | Human listening found Light Rasp 0.85x controlled settings (stability 0.50, similarity_boost 0.84, style 0.15) most stable and not distorting through vocal glissando; preserve prior Hawaiian War Chant winner as Light Rasp 0.85x. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?
- [ ] Can OpenVPI DiffSinger represent mm/oo/ng carriers and synthesize one 8-10s Hawaiian War Chant phrase from explicit notes/F0 before any Embry data is used?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
