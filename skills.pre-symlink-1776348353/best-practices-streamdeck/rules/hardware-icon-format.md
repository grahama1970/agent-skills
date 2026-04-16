---
title: Icons Must Be 72x72 RGB PNG
impact: CRITICAL
impactDescription: Wrong format causes white squares, crashes, or invisible buttons on hardware
tags: hardware, icons, format
---

## Icons Must Be 72x72 RGB PNG

Stream Deck XL has 96x96 native button resolution but streamdeck-ui renders at 72x72. All icons must be exactly 72x72 pixels in RGB mode (no alpha channel).

**Incorrect:**
```python
# RGBA — has alpha channel, will show artifacts
img = Image.new("RGBA", (72, 72), (0, 0, 0, 255))

# Wrong size — will be stretched/cropped unpredictably
img = Image.new("RGB", (96, 96), (0, 0, 0))

# LA mode — grayscale with alpha, unsupported
img = Image.open("icon.png")  # might be LA or P mode
```

**Correct:**
```python
# Always RGB, always 72x72
img = Image.new("RGB", (72, 72), (8, 10, 12))

# Convert any loaded image to RGB
img = Image.open("icon.png").convert("RGB").resize((72, 72))

# Verify before saving
assert img.size == (72, 72), f"Wrong size: {img.size}"
assert img.mode == "RGB", f"Wrong mode: {img.mode}"
img.save("icon/my_button.png")
```

### Notes
- Alpha channels cause white squares when `background_color='#ffffff'` is set in config
- Pillow's `Image.new("RGB", ...)` is the canonical constructor
- Use `nvis_base.new_icon()` for widget renderers — guarantees correct format
- Test with: `python -c "from PIL import Image; img=Image.open('icon/foo.png'); print(img.size, img.mode)"`
