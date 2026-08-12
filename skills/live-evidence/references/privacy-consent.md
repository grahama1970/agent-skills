# Privacy and Consent

Live Evidence can capture microphone and system/meeting audio. Recording and
transcription rules vary by jurisdiction, employer, customer, and meeting.
Obtain all required consent and follow the applicable policy before starting a
live listener.

The CLI requires `--consent-confirmed` for microphone, PipeWire, and dual live
modes. This is an explicit operator acknowledgement, not legal advice or proof
that consent is sufficient.

Default privacy properties:

- raw audio is processed in memory and not persisted;
- transcripts and evidence cards stay on the local host;
- external search is manual and receives only the typed query entered or
  explicitly approved by the operator;
- repository roots are allowlisted;
- evidence cards should not surface private/ITAR material into a context where
  disclosure is unauthorized;
- session deletion is a filesystem operation under the configured data root.
