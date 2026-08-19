# Style extraction

`inspect` accepts SVG files or directories and reports:

- viewBox frequencies;
- hexadecimal color frequencies;
- declared font-family stacks;
- stroke-width frequencies;
- rounded-corner radius frequencies;
- CSS keyframe names and animation durations.

The extractor uses safe XML parsing and `tinycss2`; it does not execute SVG content. The
report is evidence for authoring a theme, not an automatic claim that every discovered
value should be copied. Curate the resulting tokens into a named theme and preserve source
provenance.
