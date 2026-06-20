from pathlib import Path

from src.score_omr import score_to_midi


MINIMAL_MUSICXML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Melody</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration><type>quarter</type>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>1</duration><type>quarter</type>
      </note>
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>1</duration><type>quarter</type>
      </note>
      <note>
        <rest/><duration>1</duration><type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_score_to_midi_converts_musicxml_fixture(tmp_path: Path):
    score = tmp_path / "phrase.musicxml"
    score.write_text(MINIMAL_MUSICXML, encoding="utf-8")

    result = score_to_midi(score, tmp_path / "out", backend="musicxml")

    assert result.status == "ok"
    assert result.midi_path is not None
    assert Path(result.midi_path).exists()
    assert Path(result.midi_path).stat().st_size > 0
    assert Path(result.manifest_json).exists()
