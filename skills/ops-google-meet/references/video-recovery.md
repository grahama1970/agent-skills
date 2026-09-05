# Video blur recovery contract

Research-backed procedure, not an implemented recovery command. Sources were
found with `$brave-search` and read with `$fetcher`; no user incident was diagnosed.

1. Identify direction: local preview, outgoing camera, incoming participant or
   presentation. A sharp self-view does not prove sharp outgoing video.
2. Through `$surf`, inspect Meet's native **Troubleshooting & help** and selected
   camera/send/receive settings. Do not assume a generic Chrome stream is Meet.
3. Compose `$ops-workstation` network and load diagnostics. Do not automatically
   run a bandwidth-saturating speed test during a meeting.
4. Apply one evidence-supported change, with permission when disruptive:
   - Network pressure: reduce competing traffic or propose Ethernet.
   - CPU/device pressure: reduce expensive effects/nonessential work.
   - Low configured resolution: adjust the affected direction within actual
     device/account support. Lowering resolution trades detail for stability.
   - Soft local preview: inspect camera choice, focus and lighting. Teleprompter
     optics are a hypothesis to test, not an automatic diagnosis.
   - One remote feed affected: report possible sender-side limitation rather
     than restart the local browser blindly.
5. Read back the same view/direction and available metrics after the change.
   Browser `qualityLimitationReason`, where supported, describes outbound-video
   encoding limits (`none`, `cpu`, `bandwidth`, `other`), not all video failures.
6. Reload the affected Meet surface only with interruption permission. Chrome
   restart is a last resort. Never silently disable VPN/firewall/security policy
   or close unrelated work. Preserve evidence before restarting.

Sources:
- Google Meet troubleshooting: https://support.google.com/meet/answer/10620583?hl=en
- Send/receive resolution and effects: https://support.google.com/meet/answer/7294914?hl=en
- Outbound quality limitation metric: https://developer.mozilla.org/en-US/docs/Web/API/RTCOutboundRtpStreamStats/qualityLimitationReason
