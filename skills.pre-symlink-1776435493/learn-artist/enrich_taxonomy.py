#!/usr/bin/env python3
"""
Enrich RVC voice model metadata.json with Federated Taxonomy fields.

Usage:
  python enrich_taxonomy.py --models-root /path/to/rvc-models
  python enrich_taxonomy.py --artist "Chelsea Wolfe" --category voice  # single artist lookup
"""

import json
import sys
from pathlib import Path
from typing import Optional
import typer

# Bridge-to-music-tags mapping from Federated Taxonomy (TAXONOMY.md)
BRIDGE_TO_TAGS = {
    "Precision": ["progressive metal", "math rock", "technical death metal", "djent",
                   "jazz fusion", "bebop", "classical", "baroque", "virtuoso"],
    "Resilience": ["epic metal", "power metal", "post-rock", "cinematic", "symphonic metal",
                    "hard rock", "classic rock", "blues rock"],
    "Fragility": ["dark folk", "acoustic", "slowcore", "sadcore", "singer-songwriter",
                   "folk", "dream pop", "ethereal", "chamber pop", "chanson", "bossa nova"],
    "Corruption": ["industrial", "doom metal", "sludge metal", "dark ambient", "noise",
                    "death metal", "black metal", "gothic metal", "gothic rock", "grindcore",
                    "stoner metal", "harsh noise"],
    "Loyalty": ["neofolk", "neoclassical", "world", "ritual ambient", "medieval",
                "traditional", "roots", "gospel", "sacred", "devotional", "anatolian rock"],
    "Stealth": ["drone", "dark ambient", "ambient", "minimalist", "atmospheric",
                "shoegaze", "post-punk", "coldwave", "synthwave", "electronica"],
}

# Artist database: known genre/style info for deterministic bridge assignment
# Each entry: (subcategory, voice_type/instrument_type, genres, bridge_tags, confidence)
ARTIST_DB = {
    # === VOICE ===
    "beth-gibbons": {
        "subcategory": "vocalist",
        "voice_type": "contralto",
        "genres": ["trip-hop", "art rock", "post-rock", "experimental"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.9,
    },
    "billie-marten": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["folk", "indie folk", "singer-songwriter"],
        "bridge_tags": ["Fragility"],
        "confidence": 0.9,
    },
    "brennen-leigh": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["country", "americana", "honky-tonk", "western swing"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.85,
    },
    "bryan-funck": {
        "subcategory": "vocalist",
        "voice_type": "harsh-vocals",
        "genres": ["sludge metal", "doom metal", "post-metal"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "catrin-vincent": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["folk", "celtic folk", "traditional"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.8,
    },
    "chelsea-wolfe": {
        "subcategory": "vocalist",
        "voice_type": "contralto",
        "genres": ["gothic rock", "doom metal", "dark folk", "neoclassical"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.95,
    },
    "coline-rio": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["jazz", "chanson", "folk"],
        "bridge_tags": ["Fragility", "Loyalty"],
        "confidence": 0.8,
    },
    "corpsegrinder": {
        "subcategory": "vocalist",
        "voice_type": "death-growl",
        "genres": ["death metal", "brutal death metal"],
        "bridge_tags": ["Corruption"],
        "confidence": 0.95,
    },
    "dixie-dave-collins": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["sludge metal", "stoner metal", "southern metal"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "elena-tonra": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["indie folk", "dream pop", "slowcore", "art pop"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.9,
    },
    "elizabeth-fraser": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["dream pop", "ethereal wave", "shoegaze", "art rock"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.95,
    },
    "emma-ruth-rundle": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["post-metal", "dark folk", "doom", "singer-songwriter"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.9,
    },
    "ethan-lee-mccarthy": {
        "subcategory": "vocalist",
        "voice_type": "harsh-vocals",
        "genres": ["doom metal", "sludge metal", "drone metal", "noise"],
        "bridge_tags": ["Corruption", "Stealth"],
        "confidence": 0.9,
    },
    "eva-cassidy": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["jazz", "folk", "blues", "pop standards"],
        "bridge_tags": ["Fragility", "Loyalty"],
        "confidence": 0.9,
    },
    "dorothy-dandridge": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["jazz", "swing", "pop standards", "film soundtrack"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.85,
    },
    "françoise-hardy": {
        "subcategory": "vocalist",
        "voice_type": "contralto",
        "genres": ["chanson", "ye-ye", "folk pop", "baroque pop"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.9,
    },
    "haley-heynderickx": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["indie folk", "folk", "singer-songwriter"],
        "bridge_tags": ["Fragility", "Precision"],
        "confidence": 0.85,
    },
    "howlin-wolf": {
        "subcategory": "vocalist",
        "voice_type": "bass-baritone",
        "genres": ["delta blues", "chicago blues", "electric blues"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "iiris-vesik": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["dream pop", "shoegaze", "ethereal", "indie"],
        "bridge_tags": ["Stealth", "Fragility"],
        "confidence": 0.85,
    },
    "jacqui-mcshee": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["folk", "folk rock", "british folk", "traditional"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.9,
    },
    "jakub-orliński": {
        "subcategory": "vocalist",
        "voice_type": "countertenor",
        "genres": ["baroque", "classical", "opera", "early music"],
        "bridge_tags": ["Precision", "Loyalty"],
        "confidence": 0.9,
    },
    "jireh": {
        "subcategory": "vocalist",
        "voice_type": "tenor",
        "genres": ["gospel", "worship", "contemporary christian"],
        "bridge_tags": ["Loyalty", "Resilience"],
        "confidence": 0.85,
    },
    "kassi-valazza": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["country", "americana", "folk", "honky-tonk"],
        "bridge_tags": ["Fragility", "Loyalty"],
        "confidence": 0.85,
    },
    "kc-stafford": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["sludge metal", "doom metal", "post-metal"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.85,
    },
    "lauren-hart": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["gothic metal", "doom metal", "symphonic metal"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.85,
    },
    "linda-perhacs": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["psychedelic folk", "folk", "dream pop", "experimental"],
        "bridge_tags": ["Stealth", "Fragility"],
        "confidence": 0.9,
    },
    "lucinda-williams": {
        "subcategory": "vocalist",
        "voice_type": "contralto",
        "genres": ["alt-country", "americana", "folk rock", "roots rock"],
        "bridge_tags": ["Fragility", "Resilience"],
        "confidence": 0.9,
    },
    "maddie-kerr": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["rock", "indie rock", "alternative"],
        "bridge_tags": ["Resilience", "Fragility"],
        "confidence": 0.75,
    },
    "mariska-veres": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["psychedelic rock", "rock", "pop rock", "beat"],
        "bridge_tags": ["Stealth", "Corruption"],
        "confidence": 0.85,
    },
    "peter-steele": {
        "subcategory": "vocalist",
        "voice_type": "bass-baritone",
        "genres": ["gothic metal", "doom metal", "gothic rock", "type o negative"],
        "bridge_tags": ["Corruption", "Stealth"],
        "confidence": 0.95,
    },
    "phil-lynott": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["hard rock", "classic rock", "celtic rock"],
        "bridge_tags": ["Resilience", "Loyalty"],
        "confidence": 0.9,
    },
    "rita-lukea": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["industrial", "synthwave", "electropunk", "darkwave"],
        "bridge_tags": ["Corruption", "Stealth"],
        "confidence": 0.85,
    },
    "sabine-mccalla": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["folk", "blues", "americana", "singer-songwriter"],
        "bridge_tags": ["Fragility", "Loyalty"],
        "confidence": 0.8,
    },
    "selda-bağcan": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["anatolian rock", "turkish folk", "protest music", "psychedelic folk"],
        "bridge_tags": ["Loyalty", "Resilience"],
        "confidence": 0.9,
    },
    "sibylle-baier": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["folk", "singer-songwriter", "minimal folk", "chamber folk"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.9,
    },
    "sierra-ferrell": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["country", "folk", "old-time", "americana", "jazz"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.9,
    },
    "tom-waits": {
        "subcategory": "vocalist",
        "voice_type": "bass-baritone",
        "genres": ["experimental", "blues", "jazz", "avant-garde", "spoken word"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.9,
    },
    # === INSTRUMENT ===
    "ben-parker": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["folk", "fingerstyle", "acoustic guitar"],
        "bridge_tags": ["Fragility", "Precision"],
        "confidence": 0.8,
    },
    "elmore-james": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["delta blues", "electric blues", "slide guitar"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "allan-holdsworth": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["jazz fusion", "progressive rock", "avant-garde jazz", "legato"],
        "bridge_tags": ["Precision", "Stealth"],
        "confidence": 0.95,
    },
    "gary-moore": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["blues rock", "hard rock", "celtic rock"],
        "bridge_tags": ["Resilience", "Fragility"],
        "confidence": 0.9,
    },
    "gene-krupa": {
        "subcategory": "drummer",
        "voice_type": None,
        "genres": ["big band", "swing", "jazz"],
        "bridge_tags": ["Precision", "Resilience"],
        "confidence": 0.9,
    },
    "jaco-pastorius": {
        "subcategory": "bassist",
        "voice_type": None,
        "genres": ["jazz fusion", "jazz", "progressive", "fretless bass"],
        "bridge_tags": ["Precision", "Fragility"],
        "confidence": 0.95,
    },
    "john-bonham": {
        "subcategory": "drummer",
        "voice_type": None,
        "genres": ["hard rock", "blues rock", "heavy metal"],
        "bridge_tags": ["Resilience", "Corruption"],
        "confidence": 0.9,
    },
    "keith-moon": {
        "subcategory": "drummer",
        "voice_type": None,
        "genres": ["hard rock", "rock", "mod"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "kevin-shields": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["shoegaze", "noise pop", "dream pop", "experimental"],
        "bridge_tags": ["Stealth", "Fragility"],
        "confidence": 0.95,
    },
    "miles-davis": {
        "subcategory": "trumpeter",
        "voice_type": None,
        "genres": ["jazz", "modal jazz", "jazz fusion", "cool jazz", "bebop"],
        "bridge_tags": ["Precision", "Stealth"],
        "confidence": 0.95,
    },
    "peter-hook": {
        "subcategory": "bassist",
        "voice_type": None,
        "genres": ["post-punk", "new wave", "alternative rock", "gothic rock"],
        "bridge_tags": ["Stealth", "Corruption"],
        "confidence": 0.9,
    },
    "robin-guthrie": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["dream pop", "ethereal wave", "shoegaze", "ambient"],
        "bridge_tags": ["Stealth", "Fragility"],
        "confidence": 0.95,
    },
    "slash": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["hard rock", "blues rock", "heavy metal"],
        "bridge_tags": ["Resilience", "Corruption"],
        "confidence": 0.9,
    },
    "yasamin-shahhosseini": {
        "subcategory": "oud-player",
        "voice_type": None,
        "genres": ["persian classical", "world music", "traditional", "oud"],
        "bridge_tags": ["Loyalty", "Precision"],
        "confidence": 0.9,
    },
    # === NEW INSTRUMENT ADDITIONS ===
    "nils-frahm": {
        "subcategory": "pianist",
        "voice_type": None,
        "genres": ["neo-classical", "ambient", "minimalist", "electronic"],
        "bridge_tags": ["Fragility", "Stealth"],
        "confidence": 0.95,
    },
    "john-coltrane": {
        "subcategory": "saxophonist",
        "voice_type": None,
        "genres": ["jazz", "modal jazz", "free jazz", "hard bop"],
        "bridge_tags": ["Precision", "Corruption"],
        "confidence": 0.95,
    },
    "hildur-gudnadottir": {
        "subcategory": "cellist",
        "voice_type": None,
        "genres": ["cinematic", "experimental", "drone", "dark ambient"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.95,
    },
    "djivan-gasparyan": {
        "subcategory": "duduk-player",
        "voice_type": None,
        "genres": ["armenian folk", "world music", "cinematic", "traditional"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.95,
    },
    "zakir-hussain": {
        "subcategory": "tabla-player",
        "voice_type": None,
        "genres": ["indian classical", "world music", "jazz fusion", "tabla"],
        "bridge_tags": ["Precision", "Loyalty"],
        "confidence": 0.95,
    },
    "hilary-hahn": {
        "subcategory": "violinist",
        "voice_type": None,
        "genres": ["classical", "baroque", "contemporary classical", "violin"],
        "bridge_tags": ["Precision", "Fragility"],
        "confidence": 0.95,
    },
    "booker-t-jones": {
        "subcategory": "organist",
        "voice_type": None,
        "genres": ["soul", "r&b", "blues", "funk", "hammond organ"],
        "bridge_tags": ["Resilience", "Loyalty"],
        "confidence": 0.9,
    },
    "hossein-alizadeh": {
        "subcategory": "tar-player",
        "voice_type": None,
        "genres": ["persian classical", "world music", "traditional", "tar"],
        "bridge_tags": ["Loyalty", "Precision"],
        "confidence": 0.95,
    },
    "tosin-abasi": {
        "subcategory": "guitarist",
        "voice_type": None,
        "genres": ["progressive metal", "djent", "jazz fusion", "8-string guitar"],
        "bridge_tags": ["Precision", "Stealth"],
        "confidence": 0.95,
    },
    "ian-anderson": {
        "subcategory": "flutist",
        "voice_type": None,
        "genres": ["progressive rock", "folk rock", "hard rock", "flute"],
        "bridge_tags": ["Resilience", "Precision"],
        "confidence": 0.9,
    },
    # === HORUS PERSONA PICKS ===
    "lisa-gerrard": {
        "subcategory": "vocalist",
        "voice_type": "contralto",
        "genres": ["world music", "neoclassical", "ethereal", "cinematic", "glossolalia"],
        "bridge_tags": ["Loyalty", "Resilience"],
        "confidence": 0.95,
    },
    "trent-reznor": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["industrial", "electronic", "noise", "film score"],
        "bridge_tags": ["Corruption", "Stealth"],
        "confidence": 0.95,
    },
    "einar-selvik": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["nordic folk", "ritual ambient", "neofolk", "traditional"],
        "bridge_tags": ["Loyalty", "Resilience"],
        "confidence": 0.95,
    },
    "lingua-ignota": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["industrial", "neoclassical", "noise", "experimental", "power electronics"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.95,
    },
    "diamanda-galas": {
        "subcategory": "vocalist",
        "voice_type": "soprano",
        "genres": ["avant-garde", "experimental", "gothic", "operatic", "free improvisation"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.95,
    },
    "danzig": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["horror punk", "doom metal", "heavy metal", "dark blues"],
        "bridge_tags": ["Corruption", "Resilience"],
        "confidence": 0.9,
    },
    "jarboe": {
        "subcategory": "vocalist",
        "voice_type": "mezzo-soprano",
        "genres": ["experimental", "industrial", "art rock", "dark ambient"],
        "bridge_tags": ["Corruption", "Fragility"],
        "confidence": 0.9,
    },
    "lustmord": {
        "subcategory": "synth-player",
        "voice_type": None,
        "genres": ["dark ambient", "drone", "ritual ambient", "cinematic"],
        "bridge_tags": ["Stealth", "Corruption"],
        "confidence": 0.95,
    },
    "batzorig-vaanchig": {
        "subcategory": "vocalist",
        "voice_type": "throat-singer",
        "genres": ["mongolian folk", "throat singing", "khoomei", "traditional"],
        "bridge_tags": ["Loyalty", "Corruption"],
        "confidence": 0.9,
    },
    "brendan-perry": {
        "subcategory": "vocalist",
        "voice_type": "baritone",
        "genres": ["neoclassical", "world music", "ethereal", "dark wave"],
        "bridge_tags": ["Loyalty", "Fragility"],
        "confidence": 0.95,
    },
}


def enrich_metadata(model_dir: Path, slug: str) -> dict:
    """Enrich a model's metadata.json with taxonomy fields."""
    meta_path = model_dir / "metadata.json"
    if not meta_path.exists():
        print(f"  SKIP: {slug} - no metadata.json")
        return {}

    with open(meta_path) as f:
        meta = json.load(f)

    artist_info = ARTIST_DB.get(slug)
    if not artist_info:
        print(f"  SKIP: {slug} - not in artist database")
        return meta

    # Add taxonomy fields
    meta["subcategory"] = artist_info["subcategory"]
    if artist_info["voice_type"]:
        meta["voice_type"] = artist_info["voice_type"]
    meta["genres"] = artist_info["genres"]
    meta["bridge_tags"] = artist_info["bridge_tags"]
    meta["confidence"] = artist_info["confidence"]

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)

    print(f"  OK: {slug} -> bridges={artist_info['bridge_tags']}, sub={artist_info['subcategory']}")
    return meta


def lookup_artist(artist_name: str) -> Optional[dict]:
    """Look up an artist's taxonomy info by name."""
    # Try direct slug match
    slug = artist_name.lower().replace(" ", "-").replace("'", "").replace('"', '')
    info = ARTIST_DB.get(slug)
    if info:
        return info

    # Try partial match
    for db_slug, db_info in ARTIST_DB.items():
        if slug in db_slug or db_slug in slug:
            return db_info

    return None


def main(
    models_root: Optional[str] = typer.Option(None, help="Root directory of RVC models"),
    artist: Optional[str] = typer.Option(None, help="Single artist lookup"),
    category: str = typer.Option("voice", help="Category for single lookup"),
):

    if artist:
        info = lookup_artist(artist)
        if info:
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print(f"Unknown artist: {artist}", file=sys.stderr)
            sys.exit(1)
        return

    if not models_root:
        print("Usage: enrich_taxonomy.py --models-root /path/to/rvc-models", file=sys.stderr)
        sys.exit(1)

    root = Path(models_root)
    enriched = 0
    skipped = 0

    for category_dir in ["voice", "instrument"]:
        cat_path = root / category_dir
        if not cat_path.exists():
            continue
        for model_dir in sorted(cat_path.iterdir()):
            if not model_dir.is_dir():
                continue
            slug = model_dir.name
            result = enrich_metadata(model_dir, slug)
            if result and "bridge_tags" in result:
                enriched += 1
            else:
                skipped += 1

    print(f"\nEnriched: {enriched}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
