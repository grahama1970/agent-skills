#!/usr/bin/env python3
"""ElevenLabs SFX gap-fill generation for Orpheus native emotion tags.

This module belongs to Watch because Watch owns the search/annotation workflow
for finding movie-derived emotion evidence. ElevenLabs generation is a gap-fill
path: it creates clearly marked synthetic candidates when local movie evidence
is sparse or missing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Literal

import httpx

ORPHEUS_TAGS = (
    "laugh",
    "chuckle",
    "sigh",
    "cough",
    "sniffle",
    "groan",
    "yawn",
    "gasp",
)

STYLE_REFERENCE = (
    "young adult female voice, low-key natural delivery, slightly husky texture, "
    "dry close-mic, breath-led, understated"
)
NEGATIVE_CONSTRAINTS = (
    "no words, no celebrity names, no imitation claim, no music, no ambience, "
    "no crowd, no reverb, no dialogue"
)
PROMPT_REVIEW_SCHEMA = "voice_segment_selector.orpheus_elevenlabs_prompt_review_bundle.v1"
MANIFEST_SCHEMA = "voice_segment_selector.orpheus_elevenlabs_sfx_manifest.v1"
GenerationMode = Literal["sound-generation", "voice-tts", "voice-tts-context"]
PromptProfile = Literal["default", "second-pass", "third-pass"]

CONTEXT_CARRIERS: dict[str, str] = {
    "laugh": "What do you mean?!",
    "chuckle": "Yeah, sure...",
    "sigh": "Not again...",
    "cough": "I can't stop coughing...",
    "sniffle": "I've got a bad cold...",
    "groan": "Not again...",
    "yawn": "I'm so tired...",
    "gasp": "Wait...",
}


PROMPT_VARIANTS: dict[str, tuple[str, ...]] = {
    "laugh": (
        "short dry natural laugh, low intensity, one quick laugh burst",
        "awkward breath-led laugh, restrained and realistic, slight rasp",
        "soft private laugh under the breath, warm but understated",
        "brief surprised laugh, natural close-mic vocal only",
    ),
    "chuckle": (
        "low quiet chuckle, subtle and dry, one short nonverbal reaction",
        "small nervous chuckle, brief and slightly breathy",
        "deadpan single chuckle, restrained and close-mic",
        "soft amused chuckle, intimate and not theatrical",
    ),
    "sigh": (
        "tired sigh, soft inhale then audible relaxed exhale",
        "quiet frustrated sigh, understated and realistic",
        "soft relieved sigh with gentle breath release",
        "small disappointed sigh, close and breath-led",
    ),
    "cough": (
        "single light dry cough, realistic throat sound",
        "muted small cough, controlled and close-mic",
        "brief throat-clearing cough, natural and nonverbal",
        "soft restrained cough, one isolated vocal event",
    ),
    "sniffle": (
        "single soft sniffle, realistic nasal inhale",
        "quiet sad sniffle, subtle breath through nose",
        "small cold sniffle, clean isolated nasal sound",
        "brief held-back sniffle, intimate close-mic",
    ),
    "groan": (
        "quiet tired groan, low nonverbal vocal strain",
        "soft annoyed groan, restrained and realistic",
        "small discomfort groan, breath-led and not dramatic",
        "low reluctant groan, short isolated vocal sound",
    ),
    "yawn": (
        "single soft sleepy yawn, gentle inhale into relaxed open-mouth exhale",
        "brief restrained breathy yawn, intimate and realistic",
        "small tired yawn as if trying to stay awake, no speech",
        "quiet covered yawn, soft and close, minimal volume",
    ),
    "gasp": (
        "small startled gasp, quick inhale, realistic and restrained",
        "soft surprised gasp, close-mic breath only",
        "quiet worried gasp, short inhale and no words",
        "brief sharp gasp, understated and natural",
    ),
}

VOICE_TTS_TAG_VARIANTS: dict[str, tuple[str, ...]] = {
    # Eleven v3 rejects pure bracket tags as empty text. Keep a short
    # nonlexical carrier outside the tag so validation passes while preserving
    # the target event for review. Reviewers must reject lexical speech.
    "laugh": (
        "Ha! [laughs deeply]",
        "Hah! [full amused laugh]",
        "Ha. [short dark laugh]",
        "Hah. [controlled but louder laugh]",
        "Ha! [low booming laugh]",
        "Hah. [laughs with disbelief]",
        "Ha! [brief victorious laugh]",
        "Hah. [grim laugh]",
    ),
    "chuckle": ("Heh. [chuckles]", "Hm. [quiet chuckle]", "Hnh. [dry chuckle]", "Mm. [small nervous chuckle]"),
    "sigh": ("Hmm. [sighs]", "Ah. [exhales]", "Mm. [tired sigh]", "Hh. [frustrated sigh]"),
    "cough": ("Ahem. [coughs]", "Hm. [light cough]", "Ahem. [clears throat]", "Hh. [dry cough]"),
    "sniffle": (
        "I've got a bad cold.. [sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]",
        "I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]",
        "Mm. [sniffles]",
        "Hh. [soft sniffle]",
        "Mm. [sad sniffle]",
        "Hn. [nasal sniffle]",
    ),
    "groan": ("Mmm. [groans]", "Ngh. [tired groan]", "Ugh. [annoyed groan]", "Mm. [low groan]"),
    "yawn": (
        "I'm so tired... [yawn!!!!!!]",
        "Ahh. [yawns]",
        "Hah. [sleepy yawn]",
        "Ah. [quiet yawn]",
        "Mm. [covered yawn]",
    ),
    "gasp": ("Ah. [gasps]", "Hh. [small gasp]", "Oh. [surprised gasp]", "Hah. [sharp inhale]"),
}


VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    # Prompt-reviewer gate requires synthetic gap-fill batches to be isolated
    # nonverbal vocalizations. Keep provider prompts bracketed and keep
    # training text canonical so no dialogue leaks into emotion-only examples.
    "laugh": (
        ("[1.4 second sustained open-mouth laugh with four voiced pulses; no speech; not a chuckle or giggle]", "<laugh>"),
        ("[1.2 second full belly laugh with three clear pulses; no speech; not a chuckle]", "<laugh>"),
        ("[1.6 second deep amused laugh with repeated voiced pulses; no speech; not a short laugh]", "<laugh>"),
        ("[1.3 second strong cackling laugh with multiple pulses; no speech; not a giggle]", "<laugh>"),
        ("[1.5 second booming laugh with open throat and second breath; no speech; not a chuckle]", "<laugh>"),
        ("[1.2 second uncontrolled laugh with sustained voicing; no speech; not restrained]", "<laugh>"),
        ("[1.4 second dark full laugh with three pulse groups; no speech; not polite or small]", "<laugh>"),
        ("[1.3 second victorious open-mouth laugh with repeated pulses; no speech; not a chuckle]", "<laugh>"),
    ),
    "chuckle": (
        ("[0.45 second dry low chuckle, one short voiced burst; no speech; not a sustained laugh]", "<chuckle>"),
        ("[0.5 second restrained amused chuckle, two small pulses; no speech; not a belly laugh]", "<chuckle>"),
        ("[0.4 second grim quiet chuckle, brief closed-mouth reaction; no speech; not a laugh]", "<chuckle>"),
        ("[0.55 second disbelieving chuckle under the breath; no speech; not sustained]", "<chuckle>"),
    ),
    "sigh": (
        ("[1.0 second tired downward exhale sigh; no speech; not a gasp or yawn]", "<sigh>"),
        ("[0.9 second frustrated audible exhale sigh, falling pitch; no speech; not a yawn]", "<sigh>"),
        ("[1.2 second weary breath-out sigh with relaxed throat; no speech; not a gasp]", "<sigh>"),
        ("[0.8 second disappointed controlled exhale sigh; no speech; not a sniffle]", "<sigh>"),
    ),
    "cough": (
        ("[0.5 second light dry cough, single throat burst; no speech; not throat clearing]", "<cough>"),
        ("[0.7 second controlled throat-clearing cough, two short bursts; no speech; not a sigh]", "<cough>"),
        ("[0.45 second dry cough with sharp onset; no speech; not a laugh]", "<cough>"),
        ("[0.6 second restrained cough close-mic; no speech; not a sniffle]", "<cough>"),
    ),
    "sniffle": (
        ("I've got a bad cold.. [sniffle!!!!!!]", "I've got a bad cold.. <sniffle>"),
        ("I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]", "I've got a bad cold.. <sniffle>"),
        ("I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]", "I've got a bad cold.. <sniffle>"),
        ("[0.5 second soft nasal sniffle inhale; no speech; not a cough]", "<sniffle>"),
        ("[0.6 second sad held-back sniffle through nose; no speech; not a sigh]", "<sniffle>"),
        ("[0.45 second quiet nasal sniffle with quick inhale; no speech; not a gasp]", "<sniffle>"),
        ("[0.7 second vulnerable two-part sniffle; no speech; not throat clearing]", "<sniffle>"),
    ),
    "groan": (
        ("[0.9 second low tired groan with voiced strain; no speech; not a sigh]", "<groan>"),
        ("[0.8 second annoyed groan, low pitch and rough texture; no speech; not a yawn]", "<groan>"),
        ("[1.0 second weary groan with sustained voiced tone; no speech; not a cough]", "<groan>"),
        ("[0.9 second reluctant deep groan, closed-mouth resonance; no speech; not a laugh]", "<groan>"),
    ),
    "yawn": (
        ("I'm so tired... [yawn!!!!!!]", "I'm so tired... <yawn>"),
        ("[1.4 second sleepy open-mouth yawn with rounded inhale then relaxed exhale; no speech; not a sigh]", "<yawn>"),
        ("[1.6 second long tired yawn, open mouth and rising inhale; no speech; not a gasp]", "<yawn>"),
        ("[1.2 second covered yawn with muffled open-mouth inhale and exhale; no speech; not a sigh]", "<yawn>"),
        ("[1.5 second slow exhausted yawn with wide mouth shape; no speech; not a groan]", "<yawn>"),
    ),
    "gasp": (
        ("[0.35 second sharp surprised inhale gasp through open mouth; no speech; not a sigh]", "<gasp>"),
        ("[0.4 second startled quick inhale gasp with abrupt onset; no speech; not a yawn]", "<gasp>"),
        ("[0.45 second shocked breath-in gasp, short and bright; no speech; not a laugh]", "<gasp>"),
        ("[0.35 second sudden breathy inhale gasp; no speech; not a sniffle]", "<gasp>"),
    ),
}


EMBRY_VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "laugh": (
        ("[1.4 second sustained open-mouth laugh with four voiced pulses; warm husky female voice; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.2 second full belly laugh with three clear pulses; intimate light rasp; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.6 second genuine laugh with repeated breathy pulses; grounded female voice; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.3 second uncontrolled laugh with open voice and multiple pulses; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.5 second amused laugh with second breath and sustained voicing; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.2 second surprised full laugh, bright but husky, three pulses; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.4 second sustained laugh with clear pulse train and warm rasp; no speech; not a chuckle; not a giggle]", "<laugh>"),
        ("[1.3 second open-mouth laugh with repeated voiced peaks; no speech; not a chuckle; not a giggle]", "<laugh>"),
    ),
    "chuckle": (
        ("[0.45 second small husky chuckle, one short voiced burst; no speech; not a sustained laugh]", "<chuckle>"),
        ("[0.5 second dry little chuckle with two tiny pulses; no speech; not a belly laugh]", "<chuckle>"),
        ("[0.45 second quiet amused giggle, short and breathy; no speech; not a full laugh]", "<chuckle>"),
        ("[0.5 second nervous giggle, brief and restrained; no speech; not sustained]", "<chuckle>"),
        ("[0.4 second soft private chuckle under the breath; no speech; not a laugh]", "<chuckle>"),
        ("[0.55 second understated amused chuckle, low-key and close-mic; no speech; not a laugh]", "<chuckle>"),
        ("[0.5 second breathy embarrassed giggle, short; no speech; not a full laugh]", "<chuckle>"),
        ("[0.45 second low playful chuckle, one quick reaction; no speech; not sustained]", "<chuckle>"),
    ),
    "sigh": (
        ("[1.0 second soft tired downward exhale sigh; warm airy voice; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[0.9 second quiet relieved exhale sigh with falling pitch; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[0.85 second small frustrated breath-out sigh; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[1.2 second long breathy exhale sigh, relaxed throat; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[0.9 second gentle disappointed exhale sigh with downward fall; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[1.0 second calming audible exhale sigh, soft and controlled; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[1.1 second worn-out exhale sigh with slow falling pitch; no speech; not a gasp; not a yawn]", "<sigh>"),
        ("[0.9 second soft resigned exhale sigh; no speech; not a gasp; not a yawn]", "<sigh>"),
    ),
    "cough": (
        ("[0.5 second light dry cough, single throat burst; no speech; not a sniffle]", "<cough>"),
        ("[0.6 second small dry cough, controlled and close-mic; no speech; not a sigh]", "<cough>"),
        ("[0.45 second quiet cough with dry onset; no speech; not a laugh]", "<cough>"),
        ("[0.55 second restrained cough, one compact burst; no speech; not a groan]", "<cough>"),
        ("[0.7 second soft clearing throat cough, two short bursts; no speech; not a sniffle]", "<cough>"),
        ("[0.45 second brief dry cough; no speech; not a sigh]", "<cough>"),
        ("[0.5 second muted cough, husky and controlled; no speech; not a sniffle]", "<cough>"),
        ("[0.55 second controlled cough with sharp throat texture; no speech; not a gasp]", "<cough>"),
    ),
    "sniffle": (
        ("I've got a bad cold.. [sniffle!!!!!!]", "I've got a bad cold.. <sniffle>"),
        ("I've got a bad cold.. [sniffle sniffle sniffle!!!!!!]", "I've got a bad cold.. <sniffle>"),
        ("I've got a bad cold.. [sniffle!!!!! sniffle! sniffle]", "I've got a bad cold.. <sniffle>"),
        ("[0.5 second soft nasal sniffle inhale; no speech; not a cough]", "<sniffle>"),
        ("[0.45 second quiet nasal sniffle, quick inhale through nose; no speech; not a gasp]", "<sniffle>"),
        ("[0.65 second held-back sniffle with two nasal inhales; no speech; not a sigh]", "<sniffle>"),
        ("[0.55 second small sad sniffle, soft nose inhale; no speech; not crying]", "<sniffle>"),
        ("[0.5 second breathy sniffle through nose; no speech; not a cough]", "<sniffle>"),
        ("[0.45 second subtle cold sniffle, nasal and close-mic; no speech; not a cough]", "<sniffle>"),
        ("[0.5 second gentle sniffle, single nasal inhale; no speech; not a gasp]", "<sniffle>"),
        ("[0.6 second quiet vulnerable sniffle, two light nasal pulls; no speech; not a sigh]", "<sniffle>"),
    ),
    "groan": (
        ("[0.8 second soft annoyed groan with low voiced strain; no speech; not a sigh]", "<groan>"),
        ("[0.9 second quiet tired groan, sustained low tone; no speech; not a yawn]", "<groan>"),
        ("[0.75 second small reluctant groan, closed-mouth resonance; no speech; not a cough]", "<groan>"),
        ("[0.8 second breathy discomfort groan with voiced strain; no speech; not a sigh]", "<groan>"),
        ("[0.9 second low frustrated groan, rough husky tone; no speech; not a laugh]", "<groan>"),
        ("[0.75 second understated groan, short low vocalization; no speech; not a sigh]", "<groan>"),
        ("[0.9 second exhausted little groan with falling pitch; no speech; not a yawn]", "<groan>"),
        ("[0.8 second muted irritated groan, low and close-mic; no speech; not a cough]", "<groan>"),
    ),
    "yawn": (
        ("I'm so tired... [yawn!!!!!!]", "I'm so tired... <yawn>"),
        ("[1.4 second soft sleepy open-mouth yawn with rounded inhale then relaxed exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.2 second covered tired yawn, muffled open-mouth inhale and exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.5 second long gentle yawn with wide mouth shape, slow inhale, and slow exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.2 second small breathy yawn, open mouth with audible inhale then open-mouth exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.1 second quiet restrained yawn, covered mouth, rounded inhale and soft exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.4 second sleepy open-mouth yawn, rising inhale then relaxed exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.6 second slow exhausted yawn with full mouth opening, drawn inhale, and relaxed exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
        ("[1.2 second subtle tired yawn, small open mouth with soft inhale and soft exhale; no speech; not a sigh; not a gasp]", "<yawn>"),
    ),
    "gasp": (
        ("[0.35 second small startled inhale gasp through open mouth; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.4 second sharp surprised gasp with abrupt inhale; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.45 second breathy shocked inhale gasp, short and bright; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.4 second quiet worried gasp, quick inward breath inhale; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.35 second sudden soft gasp, open-mouth inhale; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.4 second little frightened gasp with sharp inhale onset; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.35 second quick inhale gasp, bright and brief; no speech; not a sigh; not a yawn]", "<gasp>"),
        ("[0.45 second soft astonished gasp, breath-in inhale only; no speech; not a sigh; not a yawn]", "<gasp>"),
    ),
}

SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "laugh": (
        ("WHAT DO YOU MEAN?!!!!! [full belly laugh, not a chuckle]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
        ("WHAT DO YOU MEAN?!!!!! [big open-mouth laugh with repeated HA pulses, not a chuckle]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
        ("WHAT DO YOU MEAN?!!!!! [loud sustained amused laugh with multiple peaks, not a short laugh]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
        ("WHAT DO YOU MEAN?!!!!! [cackles loudly for over one second, not a giggle]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
        ("WHAT DO YOU MEAN?!!!!! [deep repeated laugh, full voiced pulses, not restrained]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
        ("WHAT DO YOU MEAN?!!!!! [uncontrolled full laugh with several voiced bursts, not a chuckle]", "WHAT DO YOU MEAN?!!!!! <laugh>"),
    ),
    "chuckle": (
        ("Yeah, sure... [short dry chuckle]", "Yeah, sure... <chuckle>"),
        ("Yeah, sure... [brief low chuckle, one small burst]", "Yeah, sure... <chuckle>"),
        ("Yeah, sure... [tiny amused chuckle under the breath]", "Yeah, sure... <chuckle>"),
        ("Yeah, sure... [restrained half-second chuckle, not a laugh]", "Yeah, sure... <chuckle>"),
    ),
    "sigh": (
        ("Not again... [long smooth exhale sigh, no pulses]", "Not again... <sigh>"),
        ("Not again... [slow tired breath-out sigh, one continuous sound]", "Not again... <sigh>"),
        ("Not again... [soft resigned sigh, smooth falling exhale]", "Not again... <sigh>"),
        ("Not again... [weary single exhale sigh, not a gasp]", "Not again... <sigh>"),
    ),
    "gasp": (
        ("Oh! [tiny sharp inhale gasp!]", "Oh! <gasp>"),
        ("Ah! [quick breath-in gasp!]", "Ah! <gasp>"),
        ("Hh! [single startled gasp!]", "Hh! <gasp>"),
        ("Oh! [short shocked inhale!]", "Oh! <gasp>"),
        ("Ah! [small sudden open-mouth gasp!]", "Ah! <gasp>"),
        ("Hh! [brief frightened inward breath!]", "Hh! <gasp>"),
    ),
}

EMBRY_SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "laugh": (
        ("Wait, really?!!!!! [full belly laugh, not a chuckle]", "Wait, really?!!!!! <laugh>"),
        ("Wait, really?!!!!! [sustained open laugh with repeated HA pulses, not a giggle]", "Wait, really?!!!!! <laugh>"),
        ("Wait, really?!!!!! [big warm laugh with multiple voiced peaks, not a chuckle]", "Wait, really?!!!!! <laugh>"),
        ("Wait, really?!!!!! [uncontrolled amused laugh for over one second, not restrained]", "Wait, really?!!!!! <laugh>"),
    ),
    "sigh": (
        ("Not again... [long soft exhale sigh, one smooth breath]", "Not again... <sigh>"),
        ("Not again... [slow tired sigh with no pulses, just breath out]", "Not again... <sigh>"),
        ("Not again... [gentle resigned sigh, smooth falling exhale]", "Not again... <sigh>"),
        ("Not again... [quiet weary sigh, one continuous sound]", "Not again... <sigh>"),
    ),
    "gasp": (
        ("Oh! [tiny sharp inhale gasp!]", "Oh! <gasp>"),
        ("Ah! [quick breath-in gasp!]", "Ah! <gasp>"),
        ("Hh! [single startled gasp!]", "Hh! <gasp>"),
        ("Oh! [short shocked inhale!]", "Oh! <gasp>"),
        ("Ah! [small sudden open-mouth gasp!]", "Ah! <gasp>"),
        ("Hh! [brief frightened inward breath!]", "Hh! <gasp>"),
    ),
}

THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "chuckle": (
        ("Hmph. [short low dry chuckle, one brief pulse, not a laugh]", "Hmph. <chuckle>"),
        ("Heh. [quiet restrained chuckle, short amused exhale, not a laugh]", "Heh. <chuckle>"),
        ("Mm. [brief dark chuckle, one or two low pulses, no full laugh]", "Mm. <chuckle>"),
        ("Yes. [small grim chuckle, short and controlled, not sustained]", "Yes. <chuckle>"),
    ),
    "gasp": (
        ("Hah! [sharp startled inhale gasp!!!!!! very short]", "Hah! <gasp>"),
        ("What?! [brief hard gasp!!!!!! startled intake]", "What?! <gasp>"),
        ("No. [tiny sharp fear gasp!!!!!! one quick intake]", "No. <gasp>"),
    ),
}

EMBRY_THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS: dict[str, tuple[tuple[str, str], ...]] = {
    "sigh": (
        ("Okay... [long breathy exhale sigh!!!!!! one smooth breath]", "Okay... <sigh>"),
        ("Okay... [soft sigh!!!!!! one slow exhale]", "Okay... <sigh>"),
        ("I know... [quiet sigh!!!!!! smooth breath out]", "I know... <sigh>"),
    ),
}

LEARNED_PROVIDER_TRIGGER_EVIDENCE: dict[str, tuple[dict[str, str], ...]] = {
    "Hah! [sharp startled inhale gasp!!!!!! very short]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/horus-gasp-thirdpass-24",
            "source_ids": "horus_gasp_0005, horus_gasp_0009, horus_gasp_0013",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
    ),
    "What?! [brief hard gasp!!!!!! startled intake]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/horus-gasp-thirdpass-24",
            "source_ids": "horus_gasp_0003, horus_gasp_0007, horus_gasp_0011, horus_gasp_0019, horus_gasp_0023",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
    ),
    "No. [tiny sharp fear gasp!!!!!! one quick intake]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/horus-gasp-thirdpass-24",
            "source_ids": "horus_gasp_0008, horus_gasp_0020, horus_gasp_0024",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
    ),
    "Okay... [long breathy exhale sigh!!!!!! one smooth breath]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/embry-sigh-thirdpass-12",
            "source_ids": "embry_sigh_0009",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-fourth-pass-20260621/embry-sigh-fourthpass-12",
            "source_ids": "embry_sigh_0001, embry_sigh_0004, embry_sigh_0007, embry_sigh_0010",
            "evidence_type": "provider_rejects_bracket_only_input_text_empty",
        },
    ),
    "Okay... [soft sigh!!!!!! one slow exhale]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/embry-sigh-thirdpass-12",
            "source_ids": "embry_sigh_0006",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-fourth-pass-20260621/embry-sigh-fourthpass-12",
            "source_ids": "embry_sigh_0002, embry_sigh_0005, embry_sigh_0008, embry_sigh_0011",
            "evidence_type": "provider_rejects_bracket_only_input_text_empty",
        },
    ),
    "I know... [quiet sigh!!!!!! smooth breath out]": (
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-third-pass-20260621/embry-sigh-thirdpass-12",
            "source_ids": "embry_sigh_0003, embry_sigh_0011",
            "evidence_type": "classifier_accept_after_context_event_waveform_gate",
        },
        {
            "source_job": "/mnt/storage12tb/skills/voice-segment-selector/jobs/orpheus-gapfill-fourth-pass-20260621/embry-sigh-fourthpass-12",
            "source_ids": "embry_sigh_0003, embry_sigh_0006, embry_sigh_0009, embry_sigh_0012",
            "evidence_type": "provider_rejects_bracket_only_input_text_empty",
        },
    ),
}


def context_variants_for_speaker(speaker: str, tag: str, *, prompt_profile: PromptProfile = "default") -> tuple[tuple[str, str], ...]:
    is_embry = speaker.strip().lower() in {"embry", "embry-lawson", "embry_lawson"}
    if prompt_profile == "second-pass":
        if is_embry:
            if tag in EMBRY_SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS:
                return EMBRY_SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
            return EMBRY_VOICE_TTS_CONTEXT_VARIANTS[tag]
        if tag in SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS:
            return SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
        return VOICE_TTS_CONTEXT_VARIANTS[tag]
    if prompt_profile == "third-pass":
        if is_embry:
            if tag in EMBRY_THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS:
                return EMBRY_THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
            if tag in EMBRY_SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS:
                return EMBRY_SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
            return EMBRY_VOICE_TTS_CONTEXT_VARIANTS[tag]
        if tag in THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS:
            return THIRD_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
        if tag in SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS:
            return SECOND_PASS_VOICE_TTS_CONTEXT_VARIANTS[tag]
        return VOICE_TTS_CONTEXT_VARIANTS[tag]
    if is_embry:
        return EMBRY_VOICE_TTS_CONTEXT_VARIANTS[tag]
    return VOICE_TTS_CONTEXT_VARIANTS[tag]


@dataclass(frozen=True)
class PromptSpec:
    tag: str
    variant_index: int
    variant: str
    prompt: str
    duration_seconds: float
    tts_text: str | None = None


def normalize_tag(tag: str) -> str:
    clean = tag.strip().lower().removeprefix("<").removesuffix(">")
    if clean not in ORPHEUS_TAGS:
        raise ValueError(f"Unsupported Orpheus tag: {tag}. Expected one of {', '.join(ORPHEUS_TAGS)}")
    return clean


def render_prompt(variant: str, *, style_reference: str = STYLE_REFERENCE, negative_constraints: str = NEGATIVE_CONSTRAINTS) -> str:
    prompt = f"{variant}. Voice style: {style_reference}. Constraints: {negative_constraints}."
    if len(prompt) > 450:
        prompt = f"{variant}. Style: {style_reference}. Constraints: no words, no celebrity names, no music, no ambience."
    return prompt


def render_voice_context_prompt(tag: str, variant: str, tts_text: str, *, allow_isolated: bool = False) -> tuple[str, str]:
    """Render an Eleven v3 context prompt without inventing unreviewed carrier text."""
    if not allow_isolated and variant.strip().startswith("[") and tts_text.strip() == f"<{tag}>":
        carrier = CONTEXT_CARRIERS[tag]
        return f"{carrier} {variant}", f"{carrier} <{tag}>"
    return variant, tts_text


def learned_provider_trigger_evidence(prompt: str) -> tuple[dict[str, str], ...]:
    return LEARNED_PROVIDER_TRIGGER_EVIDENCE.get(prompt, ())


def build_prompt_specs(
    *,
    speaker: str = "",
    tags: Iterable[str] = ORPHEUS_TAGS,
    samples_per_tag: int = 4,
    duration_seconds: float = 1.4,
    generation_mode: GenerationMode = "sound-generation",
    prompt_profile: PromptProfile = "default",
) -> list[PromptSpec]:
    if prompt_profile not in {"default", "second-pass", "third-pass"}:
        raise ValueError("prompt_profile must be 'default', 'second-pass', or 'third-pass'")
    specs: list[PromptSpec] = []
    for raw_tag in tags:
        tag = normalize_tag(raw_tag)
        if generation_mode == "voice-tts":
            variants = VOICE_TTS_TAG_VARIANTS[tag]
        elif generation_mode == "voice-tts-context":
            context_variants = context_variants_for_speaker(speaker, tag, prompt_profile=prompt_profile)
        else:
            variants = PROMPT_VARIANTS[tag]
        for i in range(samples_per_tag):
            tts_text: str | None = None
            if generation_mode == "voice-tts-context":
                variant, tts_text = context_variants[i % len(context_variants)]
                allow_isolated = (
                    prompt_profile == "third-pass"
                    and speaker.strip().lower() in {"embry", "embry-lawson", "embry_lawson"}
                    and tag == "sigh"
                )
                prompt, tts_text = render_voice_context_prompt(tag, variant, tts_text, allow_isolated=allow_isolated)
            else:
                variant = variants[i % len(variants)]
                prompt = variant if generation_mode == "voice-tts" else render_prompt(variant)
            specs.append(
                PromptSpec(
                    tag=tag,
                    variant_index=i + 1,
                    variant=variant,
                    prompt=prompt,
                    duration_seconds=duration_seconds,
                    tts_text=tts_text,
                )
            )
    return specs


def build_prompt_review_bundle(
    specs: list[PromptSpec],
    *,
    speaker: str,
    purpose: str,
    generation_mode: GenerationMode,
    voice_id: str | None = None,
    voice_name: str | None = None,
    prompt_profile: PromptProfile = "default",
) -> dict:
    prompts = [
        {
            "id": f"{speaker}_{spec.tag}_{spec.variant_index:02d}",
            "orpheus_tag": f"<{spec.tag}>",
            "prompt": spec.prompt,
            "tts_text": spec.tts_text or f"<{spec.tag}>",
            "duration_seconds": spec.duration_seconds,
            "learned_provider_trigger_evidence": list(learned_provider_trigger_evidence(spec.prompt)),
            "acceptance_gate": (
                "Accept only if this asks for one isolated nonverbal vocalization "
                "matching the Orpheus tag and does not request celebrity imitation. "
                "For voice-tts mode, the prompt must be an Eleven v3 bracketed audio tag "
                "or a short bracketed vocal direction, with no spoken words. "
                "For voice-tts-context mode in synthetic gap-fill, prefer a single bracketed "
                "nonverbal audio direction. A minimal carrier sentence is allowed only when "
                "it is a learned provider trigger for the target vocalization; then tts_text "
                "must preserve the same spoken words and replace the provider audio tag with "
                "the canonical Orpheus tag."
            ),
        }
        for spec in specs
    ]
    return {
        "schema": PROMPT_REVIEW_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "speaker": speaker,
        "purpose": purpose,
        "generation_mode": generation_mode,
        "prompt_profile": prompt_profile,
        "voice": {
            "voice_id": voice_id,
            "voice_name": voice_name,
            "required_for_mode": generation_mode in {"voice-tts", "voice-tts-context"},
        },
        "reviewer": {
            "intended_subagent": "prompt-reviewer",
            "skill_loop": "review prompts before generation; revise rejected prompts; then generate",
            "sampling_policy": (
                "If samples_per_tag exceeds the number of unique prompt variants, repeated "
                "provider prompts are intentional stochastic samples. Each repeated prompt "
                "must still pass the same no-dialogue and tag-separability gates."
            ),
            "expected_response_schema": {
                "verdict": "PASS | REVISE | REJECT",
                "rejected_prompt_ids": ["string"],
                "required_edits": [{"prompt_id": "string", "reason": "string", "replacement_prompt": "string"}],
                "notes": "string",
            },
        },
        "policy": {
            "source_role": "synthetic_gap_fill",
            "forbidden": ["celebrity name", "voice clone claim", "unproved carrier/dialogue words", "music", "ambience"],
            "must_preserve_provenance": True,
            "voice_tts_requires_eleven_v3_audio_tags": True,
            "context_mode_maps_provider_prompt_to_training_tts_text": True,
            "synthetic_context_mode_prefers_isolated_nonverbal_prompt": True,
            "minimal_carrier_sentence_allowed_when_learned_provider_trigger": True,
        },
        "prompts": prompts,
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def prompt_review_receipt_status(review_dir: Path, review_path: Path) -> dict:
    receipt_path = review_dir / "prompt-reviewer-receipt.json"
    if not receipt_path.exists():
        return {"ok": False, "receipt_path": str(receipt_path), "reason": "prompt_review_receipt_missing"}
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "receipt_path": str(receipt_path),
            "reason": "prompt_review_receipt_invalid_json",
            "error": str(exc),
        }
    verdict = str(receipt.get("verdict") or receipt.get("status") or "").upper()
    if verdict != "PASS":
        return {
            "ok": False,
            "receipt_path": str(receipt_path),
            "reason": "prompt_review_not_pass",
            "verdict": verdict or None,
        }
    reviewed_bundle = receipt.get("reviewed_bundle_path") or receipt.get("prompt_review_bundle") or receipt.get("bundle_path")
    if reviewed_bundle and Path(str(reviewed_bundle)).expanduser().resolve() != review_path.resolve():
        return {
            "ok": False,
            "receipt_path": str(receipt_path),
            "reason": "prompt_review_receipt_for_different_bundle",
            "reviewed_bundle_path": str(reviewed_bundle),
            "expected_bundle_path": str(review_path),
        }
    return {"ok": True, "receipt_path": str(receipt_path), "verdict": verdict}


def elevenlabs_generate(
    *,
    prompt: str,
    duration_seconds: float,
    api_key: str,
    output_path: Path,
    timeout_seconds: float = 60.0,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "text": prompt,
        "duration_seconds": duration_seconds,
        "prompt_influence": 0.3,
    }
    with httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=10.0)) as client:
        resp = client.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=request,
        )
    if resp.status_code != 200:
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error": resp.text[:1000],
            "request": request,
        }
    output_path.write_bytes(resp.content)
    return {
        "status": "ok",
        "status_code": resp.status_code,
        "bytes": output_path.stat().st_size,
        "endpoint": "sound-generation",
        "request": request,
    }


def elevenlabs_generate_voice_tts(
    *,
    text: str,
    voice_id: str,
    api_key: str,
    output_path: Path,
    model_id: str = "eleven_v3",
    timeout_seconds: float = 60.0,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "model_id": model_id,
        "text": text,
        "voice_settings": {
            "stability": 0.3,
            "similarity_boost": 0.7,
            "style": 0.4,
            "use_speaker_boost": True,
        },
    }
    with httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=10.0)) as client:
        resp = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json=request,
        )
    if resp.status_code != 200:
        return {
            "status": "error",
            "status_code": resp.status_code,
            "error": resp.text[:1000],
            "endpoint": "text-to-speech",
            "voice_id": voice_id,
            "request": request,
        }
    output_path.write_bytes(resp.content)
    return {
        "status": "ok",
        "status_code": resp.status_code,
        "bytes": output_path.stat().st_size,
        "endpoint": "text-to-speech",
        "voice_id": voice_id,
        "request": request,
    }


def convert_to_wav24k(mp3_path: Path, wav_path: Path) -> dict:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(mp3_path),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        return {"status": "error", "cmd": cmd, "stderr": result.stderr[:1000]}
    return {"status": "ok", "bytes": wav_path.stat().st_size}


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80] or "sample"


def write_voice_segment_candidates(records: list[dict], path: Path, *, speaker: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            if record.get("status") != "ok" or not record.get("wav_path"):
                continue
            tag = record["orpheus_tag"]
            source_type = record.get("source_type", "elevenlabs_sfx")
            source = record.get("source", "elevenlabs_sound_generation")
            row = {
                "id": record["id"],
                "source_type": source_type,
                "source": source,
                "speaker": speaker,
                "emotion_tags": [tag],
                "tts_text": record.get("tts_text") or tag,
                "transcript": record.get("tts_text") or tag,
                "transcript_final": record.get("tts_text") or tag,
                "clip": record["wav_path"],
                "audio_path": record["wav_path"],
                "duration_sec": record["duration_seconds"],
                "status": "pending_review",
                "review_status": "pending_review",
                "provenance": {
                    "synthetic": True,
                    "provider": "elevenlabs",
                    "generation_mode": record.get("generation_mode"),
                    "voice_id": record.get("voice_id"),
                    "voice_name": record.get("voice_name"),
                    "model_id": record.get("model_id"),
                    "prompt": record["prompt"],
                    "provider_prompt": record["prompt"],
                    "tts_text": record.get("tts_text") or tag,
                    "prompt_review_bundle": record.get("prompt_review_bundle"),
                },
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_review_candidates(records: list[dict], out_dir: Path, *, speaker: str) -> tuple[Path, int]:
    """Write generated SFX candidates in both historical and review-server locations."""
    generated_path = out_dir / "voice_segment_selector_candidates.jsonl"
    count = write_voice_segment_candidates(records, generated_path, speaker=speaker)
    review_path = out_dir / "candidates.jsonl"
    if generated_path != review_path:
        review_path.write_text(generated_path.read_text(encoding="utf-8"), encoding="utf-8")
    return generated_path, count


def generate_orpheus_sfx(
    *,
    speaker: str,
    out_dir: Path,
    tags: Iterable[str] = ORPHEUS_TAGS,
    samples_per_tag: int = 4,
    duration_seconds: float = 1.4,
    dry_run: bool = False,
    write_candidates: bool = True,
    api_key: str | None = None,
    generation_mode: GenerationMode = "sound-generation",
    voice_id: str | None = None,
    voice_name: str | None = None,
    model_id: str = "eleven_v3",
    prompt_profile: PromptProfile = "default",
) -> dict:
    if generation_mode not in {"sound-generation", "voice-tts", "voice-tts-context"}:
        raise ValueError("generation_mode must be 'sound-generation', 'voice-tts', or 'voice-tts-context'")
    if generation_mode in {"voice-tts", "voice-tts-context"} and not voice_id:
        raise ValueError("--voice-id is required when generation_mode is a voice TTS mode")
    source_type = (
        "elevenlabs_voice_context"
        if generation_mode == "voice-tts-context"
        else "elevenlabs_voice_sfx"
        if generation_mode == "voice-tts"
        else "elevenlabs_sfx"
    )
    out_dir = out_dir.expanduser().resolve()
    raw_dir = out_dir / "raw_mp3"
    wav_dir = out_dir / "wav24k"
    review_dir = out_dir / "prompt-review"
    specs = build_prompt_specs(
        speaker=speaker,
        tags=tags,
        samples_per_tag=samples_per_tag,
        duration_seconds=duration_seconds,
        generation_mode=generation_mode,
        prompt_profile=prompt_profile,
    )
    purpose = "Generate synthetic gap-fill samples for Orpheus emotion tags while movie-curated clips remain preferred evidence."
    review_bundle = build_prompt_review_bundle(
        specs,
        speaker=speaker,
        purpose=purpose,
        generation_mode=generation_mode,
        voice_id=voice_id,
        voice_name=voice_name,
        prompt_profile=prompt_profile,
    )
    review_path = review_dir / "prompt_review_bundle.json"
    write_json(review_path, review_bundle)

    records: list[dict] = []
    existing_records_by_id: dict[str, dict] = {}
    manifest_path = out_dir / "elevenlabs_orpheus_sfx_manifest.json"
    if not dry_run and manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for existing_record in existing_manifest.get("records", []):
                sample_id = str(existing_record.get("id") or "")
                wav_path = existing_record.get("wav_path")
                if (
                    sample_id
                    and existing_record.get("status") == "ok"
                    and wav_path
                    and Path(wav_path).exists()
                ):
                    existing_records_by_id[sample_id] = existing_record
        except (OSError, json.JSONDecodeError):
            existing_records_by_id = {}
    missing_specs: list[PromptSpec] = []
    for spec in specs:
        sample_id = f"{speaker}_{spec.tag}_{spec.variant_index:04d}"
        if sample_id not in existing_records_by_id:
            missing_specs.append(spec)
    prompt_review_status = prompt_review_receipt_status(review_dir, review_path) if not dry_run and missing_specs else None
    if prompt_review_status and not prompt_review_status.get("ok"):
        raise RuntimeError(
            "BLOCKED: prompt_review_required "
            f"{prompt_review_status.get('reason')} "
            f"receipt={prompt_review_status.get('receipt_path')}"
        )
    if dry_run:
        for spec in specs:
            sample_id = f"{speaker}_{spec.tag}_{spec.variant_index:04d}"
            records.append(
                {
                    "id": sample_id,
                    "status": "planned",
                    "orpheus_tag": f"<{spec.tag}>",
                    "prompt": spec.prompt,
                    "tts_text": spec.tts_text or f"<{spec.tag}>",
                    "duration_seconds": spec.duration_seconds,
                    "prompt_review_bundle": str(review_path),
                    "generation_mode": generation_mode,
                    "source_type": source_type,
                    "source": "elevenlabs_text_to_speech_context_tags"
                    if generation_mode == "voice-tts-context"
                    else "elevenlabs_text_to_speech_audio_tags"
                    if generation_mode == "voice-tts"
                    else "elevenlabs_sound_generation",
                    "voice_id": voice_id,
                    "voice_name": voice_name,
                    "model_id": model_id if generation_mode in {"voice-tts", "voice-tts-context"} else "eleven_text_to_sound_v2",
                }
            )
    else:
        key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY is required unless --dry-run is used")
        for spec in specs:
            sample_id = f"{speaker}_{spec.tag}_{spec.variant_index:04d}"
            if sample_id in existing_records_by_id:
                records.append(existing_records_by_id[sample_id])
                continue
            mp3_path = raw_dir / f"{sample_id}.mp3"
            wav_path = wav_dir / f"{sample_id}.wav"
            if generation_mode in {"voice-tts", "voice-tts-context"}:
                gen = elevenlabs_generate_voice_tts(
                    text=spec.prompt,
                    voice_id=voice_id or "",
                    api_key=key,
                    output_path=mp3_path,
                    model_id=model_id,
                )
                source_type = "elevenlabs_voice_context" if generation_mode == "voice-tts-context" else "elevenlabs_voice_sfx"
                source = (
                    "elevenlabs_text_to_speech_context_tags"
                    if generation_mode == "voice-tts-context"
                    else "elevenlabs_text_to_speech_audio_tags"
                )
            else:
                gen = elevenlabs_generate(
                    prompt=spec.prompt,
                    duration_seconds=spec.duration_seconds,
                    api_key=key,
                    output_path=mp3_path,
                )
                source_type = "elevenlabs_sfx"
                source = "elevenlabs_sound_generation"
            record = {
                "id": sample_id,
                "status": gen["status"],
                "orpheus_tag": f"<{spec.tag}>",
                "prompt": spec.prompt,
                "tts_text": spec.tts_text or f"<{spec.tag}>",
                "duration_seconds": spec.duration_seconds,
                "generation_mode": generation_mode,
                "source_type": source_type,
                "source": source,
                "voice_id": voice_id,
                "voice_name": voice_name,
                "model_id": model_id if generation_mode in {"voice-tts", "voice-tts-context"} else "eleven_text_to_sound_v2",
                "mp3_path": str(mp3_path) if mp3_path.exists() else None,
                "wav_path": None,
                "prompt_review_bundle": str(review_path),
                "generation": gen,
            }
            if gen["status"] == "ok":
                converted = convert_to_wav24k(mp3_path, wav_path)
                record["conversion"] = converted
                if converted["status"] == "ok":
                    record["wav_path"] = str(wav_path)
                else:
                    record["status"] = "conversion_error"
            records.append(record)

    counts: dict[str, int] = {}
    for record in records:
        if record.get("status") in {"ok", "planned"}:
            counts[record["orpheus_tag"]] = counts.get(record["orpheus_tag"], 0) + 1

    candidates_path = out_dir / "voice_segment_selector_candidates.jsonl"
    candidate_count = 0
    if write_candidates:
        candidates_path, candidate_count = write_review_candidates(records, out_dir, speaker=speaker)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "speaker": speaker,
        "source_type": source_type,
        "generation_mode": generation_mode,
        "prompt_profile": prompt_profile,
        "role": "synthetic_gap_fill",
        "movie_curated_role": "preferred_authenticity_layer",
        "prompt_review_bundle": str(review_path),
        "prompt_review_status": prompt_review_status,
        "dry_run": dry_run,
        "requested": {
            "tags": [f"<{normalize_tag(tag)}>" for tag in tags],
            "samples_per_tag": samples_per_tag,
            "duration_seconds": duration_seconds,
            "planned_count": len(specs),
            "voice_id": voice_id,
            "voice_name": voice_name,
            "model_id": model_id if generation_mode in {"voice-tts", "voice-tts-context"} else "eleven_text_to_sound_v2",
        },
        "counts_by_tag": counts,
        "records": records,
        "voice_segment_selector_candidates": {
            "path": str(candidates_path) if write_candidates else None,
            "review_path": str(out_dir / "candidates.jsonl") if write_candidates else None,
            "count": candidate_count,
        },
    }
    write_json(manifest_path, manifest)
    write_json(
        out_dir / "manifest.json",
        {
            "schema": "voice_segment_selector.synthetic_job_manifest.v1",
            "created_at": manifest["created_at"],
            "job_dir": str(out_dir),
            "speaker": speaker,
            "source_type": source_type,
            "generation_mode": generation_mode,
            "prompt_profile": prompt_profile,
            "candidate_count": candidate_count,
            "candidates_path": str(out_dir / "candidates.jsonl") if write_candidates else None,
            "sfx_manifest_path": str(manifest_path),
            "prompt_review_bundle": str(review_path),
            "counts_by_tag": counts,
            "dry_run": dry_run,
        },
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest
