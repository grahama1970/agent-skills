Yes—**real screenplays + (when you can get them) storyboards / “art of” books** are some of the best “ground truth” training material you can feed Horus. The screenplay gives you _intent + structure_, and storyboards / production art give you _composition + coverage logic_.

### Pre-existing resources that are actually useful

- **Script PDF aggregators (great for acclaimed films / awards seasons):** ([Script Slug][1])
- **Writers Guild Foundation’s hub of script-finding resources** (good “how to find” index + library context): ([The Writers Guild Foundation][2])
- **Margaret Herrick Library** (huge script collection incl. things like cutting continuities; on-site access): ([Oscars][3])
- **Storyboard / production art books** (“Art of…”, “Art and Soul…”, etc.) are often the most reliable way to get storyboard-like visuals legally: ([Amazon][4])

> Reminder: scripts/storyboards are usually copyrighted. For “learn-by-example,” it’s safest to store **links + metadata + short excerpts** (or derived features) rather than full text dumps.

---

## A starter corpus (15 films) optimized for “script + visual reference”

These skew toward films where (a) **screenplays are commonly findable online via awards/FYC aggregators**, and (b) there’s **strong published visual material** (storyboards, concept art, production design books), which helps Horus learn camera/lighting “by example.”

### 1) Parasite

- **Why:** Rare case with an **official storyboard book** that’s basically end-to-end boards. ([Amazon][4])
- **Use:** Train shot sequencing + blocking + “board → final frame” alignment.

### 2) Blade Runner 2049

- **Why:** Strong script availability + **official “Art and Soul”** reference with storyboards/concept material. ([Alcon Entertainment][5])
- **Use:** Lighting mood control, lens language, environment-as-character.

### 3) Mad Max: Fury Road

- **Why:** Official art book explicitly spans concept → storyboards → production material. ([PenguinRandomhouse.com][6])
- **Use:** Kinetic coverage grammar (action readability, rhythm).

### 4) Dune

- **Why:** “Art and Soul” style references commonly describe including storyboards / key visuals. ([Half Price Books][7])
- **Use:** Large-scale blocking, motivated lighting, visual motifs.

### 5) Dune: Part Two

- **Why:** Companion “Art and Soul” volumes exist for the sequel as well. ([Transfer Orbit][8])
- **Use:** Continuity of visual language across films.

### 6) Oppenheimer

- **Why:** High likelihood of awards-season screenplay circulation (great for structure). ([Script Slug][9])
- **Use:** Dialogue-driven tension + controlled coverage.

### 7) Barbie

- **Why:** Awards-season screenplay availability + clear stylization (helpful for preset learning). ([Script Slug][9])
- **Use:** Color/production design cues mapped into presets.

### 8) Everything Everywhere All at Once

- **Why:** Frequently appears in awards script lists. ([Script Slug][10])
- **Use:** Rapid tonal shifts; how scripts cue camera/energy changes.

### 9) TÁR

- **Why:** Often in awards screenplay collections. ([Script Slug][10])
- **Use:** Long-scene tension, blocking, restraint.

### 10) The Banshees of Inisherin

- **Why:** Awards screenplay availability; clean scene construction. ([Script Slug][10])
- **Use:** Subtext and pacing.

### 11) The Fabelmans

- **Why:** Awards script lists; good “cinema-about-cinema” learning. ([Script Slug][10])
- **Use:** Metafilmic cues; motivated camera.

### 12) Top Gun: Maverick

- **Why:** Awards screenplay lists + action/coverage readability. ([Script Slug][10])
- **Use:** Clear action beats and spatial clarity.

### 13) Women Talking

- **Why:** Awards screenplay lists; dialogue ensemble staging. ([Script Slug][10])
- **Use:** Group blocking + conversational camera grammar.

### 14) The Power of the Dog

- **Why:** Awards screenplay lists. ([Script Slug][11])
- **Use:** Subtle dread, negative space, quiet tension.

### 15) Dune (optional “contrast study”)

- **Why:** Useful as a comparative adaptation study (how different choices manifest).
- **Use:** “Same world, different cinematic language” → helps presets/generalization.

---

## How to turn this into training signals for your preset system

To keep it plug-and-play and avoid brittleness:

1. **Start with 3 “flagship sets”** you care about (e.g., `set_dream_logic_v1`, `set_noir_classic_v1`, `set_doc_calm_v1`).
2. For each film, pick **2–3 short sequences** (2–5 minutes each).
3. Store edges in ArangoDB like you planned (`preset_refs`) that point to:
   - the film/sequence asset
   - timecodes (`tc_in_s`, `tc_out_s`)
   - a short justification note (“why this exemplifies ‘lowkey_noir’”)

4. Only later expand to full-film ingestion.

If you want, I can pick the **best 10 sequences** across the list above that are maximally “teachable” for camera + lighting + emotion control, and map each one to the exact preset categories you’ve already defined.

[1]: https://www.scriptslug.com/?utm_source=chatgpt.com "Script Slug"
[2]: https://www.wgfoundation.org/web-resources-where-to-find-scripts-online?utm_source=chatgpt.com "Where to Read Film and TV Scripts Online"
[3]: https://www.oscars.org/margaret-herrick-library/collections/scripts?utm_source=chatgpt.com "Scripts | Oscars.org | Academy of Motion Picture Arts and ..."
[4]: https://www.amazon.com/Parasite-Storyboards-Bong-Joon-Ho/dp/1538753251?utm_source=chatgpt.com "Parasite: A Graphic Novel in Storyboards: Joon Ho, Bong"
[5]: https://www.alconent.com/publishing/the-art-and-soul-of-blade-runner-2049?utm_source=chatgpt.com "The Art and Soul of Blade Runner 2049"
[6]: https://www.penguinrandomhouse.com/books/251825/the-art-of-mad-max-fury-road-by-abbie-bernstein/?utm_source=chatgpt.com "The Art of Mad Max: Fury Road by Abbie Bernstein"
[7]: https://www.hpb.com/the-art-and-soul-of-dune/M-7865345-T.html?srsltid=AfmBOopmGDJ6ole5ujtMQj8Cqdk36XlrIIxW7JpoV71OFCdChv4esyYA&utm_source=chatgpt.com "The Art and Soul of Dune"
[8]: https://www.andrewliptak.com/dune-the-storyboards-denis-villeneuve-concept-art-kickstarter/?utm_source=chatgpt.com "The art of desert warfare - Andrew Liptak"
[9]: https://www.scriptslug.com/feature/2024-oscars?utm_source=chatgpt.com "2024 Academy Awards"
[10]: https://www.scriptslug.com/feature/2023-oscars?utm_source=chatgpt.com "2023 Oscar Scripts"
[11]: https://www.scriptslug.com/feature/2022-oscars?utm_source=chatgpt.com "2022 Academy Awards"
