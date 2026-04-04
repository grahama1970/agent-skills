#!/usr/bin/env python3
"""
Seed V1 Preset Catalog into ArangoDB.
Implements the curated V1 library: 15 Sets, Components (Writer, Intent, Camera, etc.), and Evidence.
"""

import os
import sys
from arango import ArangoClient
from rich.console import Console

console = Console()

# --- Configuration ---
ARANGO_URL = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
ARANGO_DB = os.getenv("ARANGO_DB", "memory")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASS = os.getenv("ARANGO_PASS", "")

# --- V1 Catalog Data ---

# A) Writer Presets
WRITER_PRESETS = [
    {"_key": "writer_taut_minimal_v1", "type": "writer", "title": "Taut Minimal", "tags": ["minimal", "subtext", "tight-dialogue"], "params": {"sentence_length": "short", "subtext": "high", "adjectives": "sparse"}},
    {"_key": "writer_lyrical_mythic_v1", "type": "writer", "title": "Lyrical Mythic", "tags": ["poetic", "mythic", "symbolic"], "params": {"metaphor": "high", "description": "high", "ambiguity": "medium"}},
    {"_key": "writer_comedic_deadpan_v1", "type": "writer", "title": "Comedic Deadpan", "tags": ["dry", "deadpan", "understated"], "params": {"setup_length": "short", "affect": "flat", "punchline_spacing": "timed"}},
    {"_key": "writer_sharp_banter_v1", "type": "writer", "title": "Sharp Banter", "tags": ["banter", "pacey", "witty"], "params": {"dialogue_density": "high", "interruptions": "allowed", "pacing": "fast"}},
    {"_key": "writer_horror_dread_v1", "type": "writer", "title": "Horror Dread", "tags": ["dread", "sensory", "uncanny"], "params": {"sensory_detail": "medium", "ambiguity": "high", "pacing": "slow_to_burst"}},
    {"_key": "writer_noir_hardboiled_v1", "type": "writer", "title": "Noir Hardboiled", "tags": ["noir", "hardboiled", "cynical"], "params": {"voiceover_ready": True, "cynicism": "high", "metaphor": "medium"}},
    {"_key": "writer_warm_human_v1", "type": "writer", "title": "Warm Human", "tags": ["warm", "empathetic", "character"], "params": {"humor": "gentle", "introspection": "medium", "clarity": "high"}},
    {"_key": "writer_epic_grand_v1", "type": "writer", "title": "Epic Grand", "tags": ["epic", "formal", "scale"], "params": {"sentence_length": "long", "diction": "elevated", "framing": "high_stakes"}},
    {"_key": "writer_documentary_plain_v1", "type": "writer", "title": "Documentary Plain", "tags": ["plain", "informational", "clear"], "params": {"clarity": "max", "jargon": "minimized", "pacing": "normal"}},
    {"_key": "writer_surreal_fragment_v1", "type": "writer", "title": "Surreal Fragment", "tags": ["surreal", "fragmented", "nonlinear"], "params": {"scene_logic": "dreamlike", "motifs": "repetitive", "ambiguity": "max"}},
]

# B) Intent Presets
INTENT_PRESETS = [
    {"_key": "intent_calm_explainer_v1", "type": "intent", "title": "Calm Explainer", "tags": ["calm", "clear"], "params": {"mood": "grounded", "energy": "low"}},
    {"_key": "intent_tense_interrogation_v1", "type": "intent", "title": "Tense Interrogation", "tags": ["pressure", "control"], "params": {"mood": "tense", "restraint": "high"}},
    {"_key": "intent_paranoia_spiral_v1", "type": "intent", "title": "Paranoia Spiral", "tags": ["uncertainty", "threat"], "params": {"mood": "paranoid", "gaze": "surveillance"}},
    {"_key": "intent_romantic_longing_v1", "type": "intent", "title": "Romantic Longing", "tags": ["softness", "yearning"], "params": {"mood": "romantic", "intimacy": "high"}},
    {"_key": "intent_triumph_rise_v1", "type": "intent", "title": "Triumph Rise", "tags": ["momentum", "uplift"], "params": {"mood": "triumphant", "energy": "rising"}},
    {"_key": "intent_grief_hollow_v1", "type": "intent", "title": "Grief Hollow", "tags": ["quiet", "weight"], "params": {"mood": "grief", "spaciousness": "high"}},
    {"_key": "intent_anger_controlled_v1", "type": "intent", "title": "Anger Controlled", "tags": ["cold", "anger"], "params": {"mood": "angry", "expression": "controlled"}},
    {"_key": "intent_joy_bright_v1", "type": "intent", "title": "Joy Bright", "tags": ["energy", "brightness"], "params": {"mood": "joyful", "energy": "high"}},
    {"_key": "intent_mystery_unfold_v1", "type": "intent", "title": "Mystery Unfold", "tags": ["curiosity", "revelation"], "params": {"mood": "mysterious", "pacing": "unfolding"}},
    {"_key": "intent_horror_dread_v1", "type": "intent", "title": "Horror Dread", "tags": ["dread", "shock"], "params": {"mood": "dread", "rhythm": "punctuated"}},
    {"_key": "intent_absurd_comedy_v1", "type": "intent", "title": "Absurd Comedy", "tags": ["awkward", "escalation"], "params": {"mood": "absurd", "timing": "deadpan"}},
    {"_key": "intent_dream_logic_v1", "type": "intent", "title": "Dream Logic", "tags": ["symbolic", "nonlinear"], "params": {"mood": "dreamlike", "causality": "nonlinear"}},
]

# C) Camera Presets
CAMERA_PRESETS = [
    {"_key": "camera_locked_observational_v1", "type": "camera", "title": "Locked Observational", "tags": ["tripod", "patient"], "params": {"movement": "static", "vibe": "observational"}},
    {"_key": "camera_locked_symmetry_v1", "type": "camera", "title": "Locked Symmetry", "tags": ["center", "deliberate"], "params": {"movement": "static", "composition": "center_symmetrical"}},
    {"_key": "camera_handheld_doc_v1", "type": "camera", "title": "Handheld Doc", "tags": ["jitter", "responsive"], "params": {"movement": "handheld", "stability": "low"}},
    {"_key": "camera_handheld_urgent_v1", "type": "camera", "title": "Handheld Urgent", "tags": ["energy", "chase"], "params": {"movement": "handheld", "energy": "high"}},
    {"_key": "camera_dolly_push_slow_v1", "type": "camera", "title": "Dolly Push Slow", "tags": ["push", "intimacy"], "params": {"movement": "dolly_in", "speed": "slow"}},
    {"_key": "camera_dolly_pull_reveal_v1", "type": "camera", "title": "Dolly Pull Reveal", "tags": ["pull", "reveal"], "params": {"movement": "dolly_out", "context": "reveal"}},
    {"_key": "camera_steady_float_v1", "type": "camera", "title": "Steady Float", "tags": ["stabilized", "drift"], "params": {"movement": "steadicam", "feel": "floating"}},
    {"_key": "camera_orbit_subject_v1", "type": "camera", "title": "Orbit Subject", "tags": ["orbit", "unease"], "params": {"movement": "orbit", "focus": "subject"}},
    {"_key": "camera_whip_pan_energy_v1", "type": "camera", "title": "Whip Pan Energy", "tags": ["pan", "chaos"], "params": {"movement": "whip_pan", "energy": "chaotic"}},
    {"_key": "camera_static_tableau_v1", "type": "camera", "title": "Static Tableau", "tags": ["staged", "composition"], "params": {"movement": "static", "composition": "tableau"}},
    {"_key": "camera_close_intimate_v1", "type": "camera", "title": "Close Intimate", "tags": ["face", "minimal"], "params": {"framing": "close_up", "movement": "minimal"}},
    {"_key": "camera_wide_establish_scale_v1", "type": "camera", "title": "Wide Establish Scale", "tags": ["environment", "scale"], "params": {"framing": "extreme_wide", "subject": "environment"}},
]

# D) Lens Presets
LENS_PRESETS = [
    {"_key": "lens_wide_24ish_v1", "type": "lens", "title": "Wide 24mm", "tags": ["distortion", "presence"], "params": {"focal_length": "24mm", "feel": "immersive"}},
    {"_key": "lens_mid_35ish_v1", "type": "lens", "title": "Mid 35mm", "tags": ["natural", "intent"], "params": {"focal_length": "35mm", "feel": "natural"}},
    {"_key": "lens_normal_50ish_v1", "type": "lens", "title": "Normal 50mm", "tags": ["human", "pov"], "params": {"focal_length": "50mm", "feel": "human_eye"}},
    {"_key": "lens_tele_85ish_v1", "type": "lens", "title": "Tele 85mm", "tags": ["compression", "intimate"], "params": {"focal_length": "85mm", "compression": "medium"}},
    {"_key": "lens_tele_135ish_v1", "type": "lens", "title": "Tele 135mm", "tags": ["voyeur", "flatten"], "params": {"focal_length": "135mm", "compression": "high"}},
    {"_key": "lens_anamorphic_style_v1", "type": "lens", "title": "Anamorphic Style", "tags": ["widescreen", "flares"], "params": {"style": "anamorphic", "aspect_ratio": "2.39:1"}},
    {"_key": "lens_deep_focus_v1", "type": "lens", "title": "Deep Focus", "tags": ["sharp", "context"], "params": {"dof": "deep", "focus": "all"}},
    {"_key": "lens_shallow_focus_v1", "type": "lens", "title": "Shallow Focus", "tags": ["isolation", "bokeh"], "params": {"dof": "shallow", "focus": "subject"}},
    {"_key": "lens_macro_detail_v1", "type": "lens", "title": "Macro Detail", "tags": ["texture", "close"], "params": {"type": "macro", "focus": "texture"}},
    {"_key": "lens_zoom_doc_v1", "type": "lens", "title": "Zoom Doc", "tags": ["reactive", "reframing"], "params": {"zoom": "active", "style": "documentary"}},
    {"_key": "lens_wide_symmetry_v1", "type": "lens", "title": "Wide Symmetry", "tags": ["geometric", "centered"], "params": {"focal_length": "wide", "composition": "symmetrical"}},
    {"_key": "lens_long_lens_surveillance_v1", "type": "lens", "title": "Long Lens Surveillance", "tags": ["voyeur", "distance"], "params": {"focal_length": "very_long", "feel": "spying"}},
]

# E) Lighting Presets
LIGHTING_PRESETS = [
    {"_key": "lighting_soft_key_interview_v1", "type": "lighting", "title": "Soft Key Interview", "tags": ["friendly", "flattering"], "params": {"quality": "soft", "contrast": "medium"}},
    {"_key": "lighting_practicals_only_v1", "type": "lighting", "title": "Practicals Only", "tags": ["realism", "available"], "params": {"source": "practicals", "gaps": "natural"}},
    {"_key": "lighting_lowkey_noir_v1", "type": "lighting", "title": "Lowkey Noir", "tags": ["shadow", "hard"], "params": {"key": "low", "contrast": "high", "shadows": "deep"}},
    {"_key": "lighting_toplight_harsh_v1", "type": "lighting", "title": "Toplight Harsh", "tags": ["unease", "sculpted"], "params": {"direction": "top", "quality": "hard"}},
    {"_key": "lighting_side_key_drama_v1", "type": "lighting", "title": "Side Key Drama", "tags": ["chiaroscuro", "drama"], "params": {"direction": "side", "contrast": "high"}},
    {"_key": "lighting_backlight_silhouette_v1", "type": "lighting", "title": "Backlight Silhouette", "tags": ["mystery", "shape"], "params": {"direction": "back", "subject_fill": "none"}},
    {"_key": "lighting_neon_night_mix_v1", "type": "lighting", "title": "Neon Night Mix", "tags": ["colored", "wet"], "params": {"sources": ["neon", "street"], "colors": "mixed"}},
    {"_key": "lighting_fluorescent_flat_v1", "type": "lighting", "title": "Fluorescent Flat", "tags": ["clinical", "harsh"], "params": {"quality": "flat", "color_temp": "cool_green"}},
    {"_key": "lighting_highkey_comedy_v1", "type": "lighting", "title": "Highkey Comedy", "tags": ["bright", "even"], "params": {"key": "high", "shadows": "minimal"}},
    {"_key": "lighting_window_motivated_day_v1", "type": "lighting", "title": "Window Motivated", "tags": ["natural", "daylight"], "params": {"source": "window", "quality": "soft_directional"}},
    {"_key": "lighting_firelight_flicker_v1", "type": "lighting", "title": "Firelight Flicker", "tags": ["warm", "unstable"], "params": {"source": "fire", "dynamics": "flicker"}},
    {"_key": "lighting_sterile_scifi_v1", "type": "lighting", "title": "Sterile Sci-Fi", "tags": ["clean", "cool"], "params": {"quality": "controlled", "color_temp": "cool_blue"}},
    {"_key": "lighting_concert_spot_v1", "type": "lighting", "title": "Concert Spot", "tags": ["beam", "contrast"], "params": {"type": "spotlight", "beams": "visible"}},
    {"_key": "lighting_rim_separation_v1", "type": "lighting", "title": "Rim Separation", "tags": ["pop", "edge"], "params": {"rim_light": "strong", "separation": "high"}},
    {"_key": "lighting_negative_fill_v1", "type": "lighting", "title": "Negative Fill", "tags": ["subtraction", "shape"], "params": {"fill": "negative", "contrast": "enhanced"}},
    {"_key": "lighting_fog_haze_beams_v1", "type": "lighting", "title": "Fog Haze Beams", "tags": ["atmospheric", "shafts"], "params": {"atmosphere": "haze", "beams": "visible"}},
]

# F) Audio Presets
AUDIO_PRESETS = [
    {"_key": "audio_boom_close_clean_v1", "type": "audio", "title": "Boom Close Clean", "tags": ["dialogue", "dry"], "params": {"mic": "boom", "room": "minimal"}},
    {"_key": "audio_lav_backup_v1", "type": "audio", "title": "Lav Backup", "tags": ["safety", "close"], "params": {"mic": "lav", "perspective": "chest"}},
    {"_key": "audio_roomy_realism_v1", "type": "audio", "title": "Roomy Realism", "tags": ["space", "ambience"], "params": {"room_tone": "present", "reverb": "natural"}},
    {"_key": "audio_asrm_intimate_v1", "type": "audio", "title": "ASMR Intimate", "tags": ["whisper", "proximate"], "params": {"proximity": "extreme", "details": "heightened"}},
    {"_key": "audio_music_forward_v1", "type": "audio", "title": "Music Forward", "tags": ["score", "lead"], "params": {"mix": "music_lead", "dialogue": "secondary"}},
    {"_key": "audio_diegetic_focus_v1", "type": "audio", "title": "Diegetic Focus", "tags": ["world", "immersive"], "params": {"focus": "sound_effects", "source": "in_scene"}},
    {"_key": "audio_radio_lofi_v1", "type": "audio", "title": "Radio Lo-Fi", "tags": ["bandwidth", "processed"], "params": {"processing": "bandpass", "quality": "lofi"}},
    {"_key": "audio_silence_tension_v1", "type": "audio", "title": "Silence Tension", "tags": ["space", "sparse"], "params": {"density": "sparse", "silence": "heavy"}},
]

# G) Grade Presets
GRADE_PRESETS = [
    {"_key": "grade_neutral_rec709_v1", "type": "grade", "title": "Neutral Rec709", "tags": ["standard", "accurate"], "params": {"gamma": "2.4", "gamut": "rec709"}},
    {"_key": "grade_high_contrast_bw_v1", "type": "grade", "title": "High Contrast BW", "tags": ["bw", "dramatic"], "params": {"saturation": "0", "contrast": "high"}},
    {"_key": "grade_bleach_bypass_style_v1", "type": "grade", "title": "Bleach Bypass", "tags": ["silver", "retain"], "params": {"saturation": "low", "contrast": "harsh"}},
    {"_key": "grade_warm_amber_v1", "type": "grade", "title": "Warm Amber", "tags": ["golden", "nostalgic"], "params": {"tint": "amber", "temp": "warm"}},
    {"_key": "grade_cool_steel_v1", "type": "grade", "title": "Cool Steel", "tags": ["blue", "industrial"], "params": {"tint": "cyan", "temp": "cool"}},
    {"_key": "grade_teal_orange_modern_v1", "type": "grade", "title": "Teal Orange", "tags": ["blockbuster", "complementary"], "params": {"shadows": "teal", "highlights": "orange"}},
    {"_key": "grade_pastel_soft_v1", "type": "grade", "title": "Pastel Soft", "tags": ["dreamy", "light"], "params": {"saturation": "pastel", "contrast": "low"}},
    {"_key": "grade_neon_saturated_night_v1", "type": "grade", "title": "Neon Saturated", "tags": ["vibrant", "night"], "params": {"saturation": "high", "colors": "neon"}},
    {"_key": "grade_film_grain_subtle_v1", "type": "grade", "title": "Film Grain Subtle", "tags": ["organic", "texture"], "params": {"grain": "subtle", "look": "analog"}},
    {"_key": "grade_desaturated_bleak_v1", "type": "grade", "title": "Desaturated Bleak", "tags": ["hopeless", "faded"], "params": {"saturation": "very_low", "mood": "bleak"}},
]

# H) Gear Presets
GEAR_PRESETS = [
    {"_key": "gear_home_studio_v1", "type": "gear", "title": "Home Studio", "tags": ["stable", "resources"], "params": {"constraints": "none", "resources": "high"}},
    {"_key": "gear_practicals_only_v1", "type": "gear", "title": "Practicals Only", "tags": ["limited", "natural"], "params": {"lighting_constraint": "practicals"}},
    {"_key": "gear_run_and_gun_v1", "type": "gear", "title": "Run & Gun", "tags": ["mobile", "fast"], "params": {"setup_time": "minimal", "mobility": "high"}},
    {"_key": "gear_high_fidelity_render_v1", "type": "gear", "title": "High Fidelity", "tags": ["quality", "slow"], "params": {"render_quality": "max", "patience": "high"}},
    {"_key": "gear_low_latency_discord_v1", "type": "gear", "title": "Low Latency Discord", "tags": ["fast", "streaming"], "params": {"latency": "low", "format": "optimized"}},
]

ALL_COMPONENTS = (
    WRITER_PRESETS + INTENT_PRESETS + CAMERA_PRESETS + LENS_PRESETS +
    LIGHTING_PRESETS + AUDIO_PRESETS + GRADE_PRESETS + GEAR_PRESETS
)

# --- V1 Preset Sets ---

PRESET_SETS = [
    {
        "_key": "set_doc_calm_v1", "type": "set", "title": "Documentary Calm",
        "description": "Calm, clear, grounded explainer style.",
        "preset_ids": [
            "writer_documentary_plain_v1", "intent_calm_explainer_v1", "camera_locked_observational_v1",
            "lens_normal_50ish_v1", "lighting_soft_key_interview_v1", "audio_boom_close_clean_v1",
            "grade_neutral_rec709_v1", "gear_low_latency_discord_v1"
        ]
    },
    {
        "_key": "set_doc_urgent_v1", "type": "set", "title": "Documentary Urgent",
        "description": "Unfolding mystery, handheld urgency.",
        "preset_ids": [
            "writer_documentary_plain_v1", "intent_mystery_unfold_v1", "camera_handheld_doc_v1",
            "lens_zoom_doc_v1", "lighting_practicals_only_v1", "audio_roomy_realism_v1",
            "grade_desaturated_bleak_v1", "gear_run_and_gun_v1"
        ]
    },
    {
        "_key": "set_noir_classic_v1", "type": "set", "title": "Noir Classic",
        "description": "Hardboiled, high contrast, paranoia.",
        "preset_ids": [
            "writer_noir_hardboiled_v1", "intent_paranoia_spiral_v1", "camera_locked_observational_v1",
            "lens_mid_35ish_v1", "lighting_lowkey_noir_v1", "audio_diegetic_focus_v1",
            "grade_high_contrast_bw_v1", "gear_home_studio_v1"
        ]
    },
    {
        "_key": "set_thriller_interrogation_v1", "type": "set", "title": "Thriller Interrogation",
        "description": "Taut, controlled, negative fill.",
        "preset_ids": [
            "writer_taut_minimal_v1", "intent_tense_interrogation_v1", "camera_dolly_push_slow_v1",
            "lens_tele_85ish_v1", "lighting_negative_fill_v1", "audio_silence_tension_v1",
            "grade_cool_steel_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_horror_dread_v1", "type": "set", "title": "Horror Dread",
        "description": "Slow dread, surveillance, silhouette.",
        "preset_ids": [
            "writer_horror_dread_v1", "intent_horror_dread_v1", "camera_steady_float_v1",
            "lens_long_lens_surveillance_v1", "lighting_backlight_silhouette_v1", "audio_silence_tension_v1",
            "grade_desaturated_bleak_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_horror_clinical_v1", "type": "set", "title": "Horror Clinical",
        "description": "Paranoia, flat lighting, deep focus.",
        "preset_ids": [
            "writer_horror_dread_v1", "intent_paranoia_spiral_v1", "camera_static_tableau_v1",
            "lens_deep_focus_v1", "lighting_fluorescent_flat_v1", "audio_roomy_realism_v1",
            "grade_cool_steel_v1", "gear_home_studio_v1"
        ]
    },
    {
        "_key": "set_dream_logic_v1", "type": "set", "title": "Dream Logic",
        "description": "Surreal, nonlinear, pastel haze.",
        "preset_ids": [
            "writer_surreal_fragment_v1", "intent_dream_logic_v1", "camera_steady_float_v1",
            "lens_anamorphic_style_v1", "lighting_fog_haze_beams_v1", "audio_music_forward_v1",
            "grade_pastel_soft_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_surreal_noir_v1", "type": "set", "title": "Surreal Noir",
        "description": "Fragmented, neon night, orbiting.",
        "preset_ids": [
            "writer_surreal_fragment_v1", "intent_paranoia_spiral_v1", "camera_orbit_subject_v1",
            "lens_wide_24ish_v1", "lighting_neon_night_mix_v1", "audio_diegetic_focus_v1",
            "grade_neon_saturated_night_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_comedy_deadpan_v1", "type": "set", "title": "Comedy Deadpan",
        "description": "Dry, static, high-key.",
        "preset_ids": [
            "writer_comedic_deadpan_v1", "intent_absurd_comedy_v1", "camera_locked_observational_v1",
            "lens_normal_50ish_v1", "lighting_highkey_comedy_v1", "audio_boom_close_clean_v1",
            "grade_neutral_rec709_v1", "gear_low_latency_discord_v1"
        ]
    },
    {
        "_key": "set_comedy_chaos_v1", "type": "set", "title": "Comedy Chaos",
        "description": "Banter, whip-pans, grain.",
        "preset_ids": [
            "writer_sharp_banter_v1", "intent_absurd_comedy_v1", "camera_whip_pan_energy_v1",
            "lens_zoom_doc_v1", "lighting_highkey_comedy_v1", "audio_diegetic_focus_v1",
            "grade_film_grain_subtle_v1", "gear_run_and_gun_v1"
        ]
    },
    {
        "_key": "set_romance_longing_v1", "type": "set", "title": "Romance Longing",
        "description": "Warm, intimate, shallow focus.",
        "preset_ids": [
            "writer_warm_human_v1", "intent_romantic_longing_v1", "camera_close_intimate_v1",
            "lens_shallow_focus_v1", "lighting_window_motivated_day_v1", "audio_asrm_intimate_v1",
            "grade_warm_amber_v1", "gear_home_studio_v1"
        ]
    },
    {
        "_key": "set_epic_triumph_v1", "type": "set", "title": "Epic Triumph",
        "description": "Grand scale, rim light, teal/orange.",
        "preset_ids": [
            "writer_epic_grand_v1", "intent_triumph_rise_v1", "camera_dolly_pull_reveal_v1",
            "lens_wide_24ish_v1", "lighting_rim_separation_v1", "audio_music_forward_v1",
            "grade_teal_orange_modern_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_scifi_sterile_v1", "type": "set", "title": "Sci-Fi Sterile",
        "description": "Minimal, static, cool steel.",
        "preset_ids": [
            "writer_taut_minimal_v1", "intent_mystery_unfold_v1", "camera_static_tableau_v1",
            "lens_deep_focus_v1", "lighting_sterile_scifi_v1", "audio_radio_lofi_v1",
            "grade_cool_steel_v1", "gear_home_studio_v1"
        ]
    },
    # Persona / Director Style Bundles (Aliases)
    {
        "_key": "set_symmetry_wide_still_v1", "type": "set", "set_type": "partial", "title": "Symmetry Wide Still",
        "description": "Kubrick-ish distinct symmetry and stasis.",
        "preset_ids": [
            "writer_taut_minimal_v1", "camera_locked_symmetry_v1", "lens_wide_symmetry_v1",
            "lighting_fluorescent_flat_v1", "grade_desaturated_bleak_v1", "gear_high_fidelity_render_v1"
        ]
    },
    {
        "_key": "set_neon_night_rain_v1", "type": "set", "set_type": "partial", "title": "Neon Night Rain",
        "description": "Noir-future neon vibe.",
        "preset_ids": [
             "lens_anamorphic_style_v1", "lighting_neon_night_mix_v1", "grade_neon_saturated_night_v1",
             "audio_diegetic_focus_v1", "gear_high_fidelity_render_v1"
        ]
    }
]

# --- Seed Execution ---

def seed_db():
    client = ArangoClient(hosts=ARANGO_URL)
    db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASS)
    
    # 1. Ensure Collections
    if not db.has_collection("presets"):
        db.create_collection("presets")
    if not db.has_collection("preset_sets"):
        db.create_collection("preset_sets")
    
    presets_coll = db.collection("presets")
    sets_coll = db.collection("preset_sets")
    
    console.print("[bold]Seeding V1 Components...[/bold]")
    for p in ALL_COMPONENTS:
        p["_key"] = p["_key"] # Ensure key is set
        presets_coll.insert(p, overwrite=True)
    console.print(f"✓ Inserted {len(ALL_COMPONENTS)} component presets.")
    
    console.print("[bold]Seeding V1 Sets...[/bold]")
    for s in PRESET_SETS:
        # Default to complete if not specified
        if "set_type" not in s:
            s["set_type"] = "complete"
        sets_coll.insert(s, overwrite=True)
    console.print(f"✓ Inserted {len(PRESET_SETS)} preset sets.")
    
    # Optional: Seed a few evidence refs if collections exist
    if db.has_collection("preset_refs") and db.has_collection("horus_lore_docs"):
        refs_coll = db.collection("preset_refs")
        # Placeholder for a couple of known examples if we had IDs
        # For now, just ensuring structure is ready
        pass

if __name__ == "__main__":
    try:
        seed_db()
        console.print("[bold green]V1 Catalog Seeding Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Seeding Failed: {e}[/bold red]")
        sys.exit(1)
