# Where to report WiiM bugs (routing table)

WiiM has NO official GitHub issue tracker. Official firmware / WiiM Home app /
hardware / HDMI / streaming issues go to the WiiM Community Forum, not GitHub:
<https://forum.wiimhome.com/>

Third-party trackers (only when the bug is in that layer, reproducible there):

| Layer | Repo / venue |
|---|---|
| Home Assistant WiiM integration (community) | <https://github.com/mjcumming/wiim/issues> |
| Home Assistant Core built-in behavior | <https://github.com/home-assistant/core/issues> |
| Music Assistant WiiM playback/provider | <https://github.com/music-assistant/support/issues> |
| pywiim client library | <https://github.com/mjcumming/pywiim> |
| Native firmware/app/device/HDMI behavior | WiiM forum + official support (no GitHub) |

High-signal report contents (this skill produces most of it):
- Model + firmware from `getStatusEx` (`project`, `firmware`, `Release`)
- `diagnose --json` output (vol/mute/EQ/source/output-mode snapshot)
- `monitor` NDJSON deltas while reproducing the fault
- Source-by-source differential result (streaming vs HDMI ARC vs Line In)
- What the API cannot observe (from the report's `not_observable` list) so the
  power-stage / TV-side question is framed correctly

Low-volume escalation path proven in the field (2026-09):
1. `diagnose` exonerates amp config (vol high, unmuted, EQ off).
2. A/B streaming vs TV at the same volume splits LG-TV path vs amp hardware.
3. TV-path-only → LG settings (Digital Sound Out=PCM, Auto Volume off, ARC cable).
4. Both-paths-quiet → speaker wiring, then WiiM forum/support with the
   diagnose + monitor artifacts attached.
