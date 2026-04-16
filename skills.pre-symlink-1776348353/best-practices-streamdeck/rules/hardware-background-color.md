---
title: Never Set Background Color to White
impact: HIGH
impactDescription: White background causes white squares with transparent or dark icons
tags: hardware, icons, config
---

## Never Set Background Color to White

Buttons configured through the streamdeck-ui GUI often get `background_color: '#ffffff'`. This causes white squares when the icon has any transparency or dark theme.

**Incorrect:**
```json
{
    "background_color": "#ffffff",
    "icon": "icon/my_dark_icon.png"
}
```

**Correct:**
```json
{
    "background_color": "",
    "icon": "icon/my_dark_icon.png"
}
```

### Notes
- To fix a live button showing white: use socket `set_icon` to push the correct icon
- Never write config to fix it — widget services will clobber the change
- NVIS icons use `C_BG = (8, 10, 12)` background; white backgrounds destroy readability
- When creating templates, always set `background_color` to `""` (empty string)
