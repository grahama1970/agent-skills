---
title: Use safe XML parsing for untrusted XML
impact: HIGH
impactDescription: prevents XML entity expansion and related attacks
tags: security, xml
---

## Use safe XML parsing for untrusted XML

**Incorrect:**
```py
import xml.etree.ElementTree as ET

ET.fromstring(xml_text)
```

**Correct:**
```py
from defusedxml import ElementTree as ET

ET.fromstring(xml_text)
```

### Notes
- Only parse XML if required; prefer JSON.
- If parsing untrusted XML, use defusedxml.
