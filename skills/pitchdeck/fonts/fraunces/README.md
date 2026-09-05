# Fraunces for PDF rendering

These static Regular (400) and Bold (700) TTFs were generated from the existing
`site/public/fonts/fraunces-site-subset.woff2` (SHA256
`7a22f1bd886f4083201ee9dcc2d2fccbf9b084d54691184b3c4f5cf5c264186d`).
They retain that subset's glyph coverage, not the full upstream family.
Copyright 2018 The Fraunces Project Authors. Distributed under SIL OFL 1.1;
full license in `OFL.txt`, retrieved from
https://raw.githubusercontent.com/google/fonts/main/ofl/fraunces/OFL.txt.

Reproduction requires build-time `fonttools[woff]`, not a runtime dependency:
load the WOFF2 with `fontTools.ttLib.TTFont`, set `flavor=None`, and call
`fontTools.varLib.instancer.instantiateVariableFont` for each weight with
`{'wght': 400 or 700, 'opsz': 9, 'SOFT': 0, 'WONK': 1}`, `inplace=True`.
Set name IDs 1/16 to `Fraunces`, 2/17 to `Regular` or `Bold`, 4 to
`Fraunces Regular` or `Fraunces Bold`, and 6 to `Fraunces-Regular` or
`Fraunces-Bold`, for the existing name-table platform/encoding/language records;
save each as TTF. The supplied instances were converted before this recovery.

The renderer adds this directory only to the LibreOffice process's Fontconfig,
retaining the default or caller-configured fonts. The browser keeps its original
variable WOFF2. PDF embeds/subsets the used glyphs; editable PPTX only requests
Fraunces, so recipients may need these TTFs installed. Optical sizing and pixels
are not claimed identical across applications.
