"""Template-based metadata generation for SFX files."""


def generate_metadata(features: dict, categories: list[str], filename: str) -> dict:
    """Generate descriptive metadata using template-based approach.
    
    Args:
        features: Audio features dictionary
        categories: List of category labels
        filename: Original filename
        
    Returns:
        Dictionary with description, keywords, and use_cases
    """
    duration = features.get("duration", 0)
    envelope_type = features.get("envelope", {}).get("type", "sustained")
    centroid = features.get("frequency_profile", {}).get("spectral_centroid", 0)
    
    # Build description from templates
    desc_parts = []
    
    # Duration descriptor
    if duration < 1.0:
        desc_parts.append("short")
    elif duration < 5.0:
        desc_parts.append("medium-length")
    else:
        desc_parts.append("long")
    
    # Frequency descriptor
    if centroid < 500:
        desc_parts.append("low-frequency")
    elif centroid < 2000:
        desc_parts.append("mid-range")
    else:
        desc_parts.append("high-frequency")
    
    # Category-based descriptor
    if "impact" in categories:
        desc_parts.append("impact sound")
    elif "ambient" in categories:
        desc_parts.append("ambient sound")
    elif "foley" in categories:
        desc_parts.append("foley effect")
    elif "transition" in categories:
        desc_parts.append("transition effect")
    else:
        desc_parts.append("sound effect")
    
    # Envelope descriptor
    if envelope_type == "impact":
        desc_parts.append("with sharp attack")
    elif envelope_type == "sustained":
        desc_parts.append("with sustained character")
    
    description = " ".join(desc_parts).capitalize()
    
    # Generate keywords
    keywords = []
    keywords.extend(categories)
    keywords.append(envelope_type)
    
    # Add duration keywords
    if duration < 1.0:
        keywords.append("quick")
    elif duration > 5.0:
        keywords.append("extended")
    
    # Add frequency keywords
    if centroid < 500:
        keywords.extend(["bass", "rumble", "low"])
    elif centroid > 4000:
        keywords.extend(["bright", "high", "treble"])
    
    # Extract words from filename
    name_words = filename.replace(".mp3", "").replace("_", " ").replace("-", " ").split()
    keywords.extend([w.lower() for w in name_words if len(w) > 2])
    
    # Remove duplicates
    keywords = list(dict.fromkeys(keywords))
    
    # Generate use cases
    use_cases = []
    if "impact" in categories:
        use_cases.extend(["action sequences", "collisions", "hits"])
    if "ambient" in categories:
        use_cases.extend(["background atmosphere", "scene setting", "mood"])
    if "foley" in categories:
        use_cases.extend(["character movement", "object interaction"])
    if "transition" in categories:
        use_cases.extend(["scene transitions", "cuts", "reveals"])
    
    if not use_cases:
        use_cases = ["general sound effects"]
    
    return {
        "description": description,
        "keywords": ", ".join(keywords),
        "use_cases": use_cases
    }
