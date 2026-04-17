"""
Extended trick definitions: requirements extraction and math noise patterns.
"""

REQUIREMENTS_TRICKS = {
    "shall-variations": {
        "description": "SHALL/MUST/WILL in various formats and contexts",
        "content": """1. FORMAL REQUIREMENTS

REQ-001: The system shall provide user authentication.
REQ-002: The system MUST log all access attempts.
REQ-003: The system will maintain audit trails.

2. INLINE REQUIREMENTS

The device shall operate at temperatures between -40°C and +85°C.
Memory usage must not exceed 512MB during normal operation.
The API will respond within 100ms for 99% of requests.

3. CONDITIONAL REQUIREMENTS

If the battery level falls below 10%, the system shall enter low-power mode.
When network connectivity is lost, the device must cache data locally.
Unless explicitly disabled, the system shall encrypt all transmissions.""",
    },
    "mixed-numbering": {
        "description": "Various requirement ID formats and numbering schemes",
        "content": """REQUIREMENT SPECIFICATIONS

REQ-001: Basic sequential numbering requirement.
REQ-SYS-002: Prefixed category numbering.
R.1.2.3: Decimal hierarchical numbering.
§4.5.6: Section symbol numbering (legal style).
1.2.3.4: Pure decimal (no prefix).
[REQ-007]: Bracketed requirement ID.
REQ_UNDERSCORE_008: Underscore separator.
SRS-FUNC-009: Multi-prefix requirement.

HIERARCHICAL REQUIREMENTS

1. System Requirements
   1.1 The system shall boot within 30 seconds.
   1.2 Performance Requirements
       1.2.1 CPU usage shall not exceed 80%.
       1.2.2 Memory Requirements
             1.2.2.1 Heap allocation shall be limited to 1GB.""",
    },
    "table-requirements": {
        "description": "Requirements embedded in table cells",
        "type": "table",
        "columns": ["Req ID", "Description", "Priority", "Verification"],
        "rows": [
            ["REQ-T-001", "The system shall authenticate users via OAuth 2.0", "High", "Test"],
            ["REQ-T-002", "Sessions must timeout after 30 minutes of inactivity", "High", "Test"],
            ["REQ-T-003", "Password complexity will enforce 12+ characters", "Medium", "Inspection"],
            ["REQ-T-004", "Failed login attempts shall trigger lockout after 5 tries", "High", "Test"],
        ],
    },
    "traceability-matrix": {
        "description": "Requirement traceability/cross-reference matrix",
        "type": "table",
        "columns": ["Requirement", "Design Ref", "Test Case", "Status"],
        "rows": [
            ["REQ-001", "DD-3.1", "TC-001, TC-002", "Verified"],
            ["REQ-002", "DD-3.2, DD-3.3", "TC-003", "Partial"],
            ["REQ-003", "DD-4.1", "TC-004, TC-005, TC-006", "Verified"],
            ["REQ-004", "DD-4.2", "Pending", "Not Verified"],
        ],
    },
    "conditional-requirements": {
        "description": "IF/WHEN/UNLESS conditional requirement clauses",
        "content": """CONDITIONAL REQUIREMENT SPECIFICATIONS

WHEN-CLAUSE FORMAT:
When the system is in maintenance mode: The system shall disable user logins.
When battery level < 20%: The device must reduce screen brightness by 50%.
When external power is connected: The system shall enter fast-charge mode.

IF-THEN FORMAT:
If the temperature exceeds 85°C, the processor shall throttle to 50% speed.
If no heartbeat is received for 60 seconds, the watchdog must trigger reset.
If the user cancels the operation, all temporary files will be deleted.

UNLESS FORMAT:
Unless explicitly authorized, the system shall reject administrative commands.
Unless in debug mode, stack traces must not be exposed to users.

PROVIDED THAT:
The system shall allow concurrent users provided that total memory usage stays below 4GB.
Encryption may be disabled provided that the connection is over a trusted network.

EXCEPTION CLAUSES:
The system shall log all errors, except for rate-limited duplicate entries.
All data must be encrypted at rest, except for public configuration files.""",
    },
    "false-positive-shall": {
        "description": "Text with 'shall' that is NOT a requirement (false positive test)",
        "content": """MEETING NOTES - 2024 Annual Planning

We shall meet again next Tuesday to discuss the project timeline.
The team shall consider several options before making a decision.
"We shall overcome" - Martin Luther King Jr.
I shall return! (General MacArthur)

This meeting shall be followed by a lunch reception.
The parties shall endeavor to resolve disputes amicably.
The document shall serve as a record of our discussion.

SHAKESPEARE QUOTES:
"Shall I compare thee to a summer's day?"
"We shall not see his like again."

LEGAL BOILERPLATE (not actionable requirements):
The licensee shall be bound by the terms herein.
Nothing in this agreement shall be construed as...
This warranty shall not apply to normal wear and tear.""",
    },
    "nested-requirements": {
        "description": "Parent/child hierarchical requirements",
        "content": """HIERARCHICAL REQUIREMENT STRUCTURE

REQ-PARENT-001: User Authentication System
  REQ-CHILD-001.1: The system shall support username/password authentication.
  REQ-CHILD-001.2: The system shall support multi-factor authentication.
    REQ-CHILD-001.2.1: MFA shall support TOTP tokens.
    REQ-CHILD-001.2.2: MFA shall support SMS verification.
    REQ-CHILD-001.2.3: MFA shall support hardware keys (FIDO2).
  REQ-CHILD-001.3: The system shall log authentication events.

REQ-PARENT-002: Data Encryption
  REQ-CHILD-002.1: Data at rest shall be encrypted using AES-256.
  REQ-CHILD-002.2: Data in transit shall be encrypted using TLS 1.3.
    REQ-CHILD-002.2.1: Certificate pinning shall be enforced for mobile clients.

INDENTED BLOCK FORMAT:

1. Performance Requirements
   1.1 Response Time
       - The API shall respond within 100ms (P50)
       - The API shall respond within 500ms (P99)
       - Timeout shall be set to 30 seconds maximum
   1.2 Throughput
       - The system shall handle 1000 requests/second
       - Peak load shall not exceed 5000 requests/second""",
    },
    "domain-specific-shall": {
        "description": "Domain-specific requirement patterns (aerospace, medical, automotive)",
        "content": """AEROSPACE REQUIREMENTS (DO-178C Style)

[HIGH] REQ-SW-001: The flight control software shall compute attitude within 10ms.
[HIGH] REQ-SW-002: Loss of GPS signal shall trigger fallback to INS navigation.
[MEDIUM] REQ-SW-003: Telemetry data shall be logged at 100Hz minimum.

MEDICAL DEVICE (IEC 62304 Style)

REQ-MED-001 (Class C): The infusion pump shall stop within 100ms upon occlusion detection.
REQ-MED-002 (Class B): Alarm volume must be adjustable between 45dB and 85dB.
REQ-MED-003 (Class A): Device status shall be displayed on the LCD.

AUTOMOTIVE (ISO 26262 Style)

REQ-ASIL-D-001: The braking system shall achieve full stop within 3 seconds.
REQ-ASIL-B-002: Dashboard warning lights must illuminate within 200ms of fault detection.
REQ-QM-003: Infotainment system should support Bluetooth 5.0.

MILITARY (MIL-STD Style)

3.1.1 The system SHALL withstand electromagnetic pulse (EMP) per MIL-STD-461G.
3.1.2 Operating temperature range SHALL be -40°C to +71°C (MIL-STD-810H).
3.1.3 The equipment SHALL survive drops from 1.2 meters onto concrete.""",
    },
    "ambiguous-modal": {
        "description": "SHOULD/MAY/MIGHT - ambiguous modal verbs (not strict requirements)",
        "content": """RECOMMENDATIONS AND SUGGESTIONS

The system should implement caching for frequently accessed data.
Users may choose to enable two-factor authentication.
The interface might display a confirmation dialog before deletion.

NICE-TO-HAVE FEATURES:

3.1 The application should support dark mode theme.
3.2 Export functionality may include PDF and CSV formats.
3.3 Search results could be paginated for performance.

OPTIONAL CONSIDERATIONS:

The team should consider implementing rate limiting.
Documentation may be provided in multiple languages.
Future versions might include voice commands.""",
    },
}

MATH_NOISE_TRICKS = {
    "false-positive-equations": {
        "description": "Short numeric lines (1), [10] that mimic equation numbering",
        "content": """(1)
        [10]
        {5}
        <2>
        
        This is text with equation-like numbering interspersed.
        
        (a)
        (iv)
        [i]
        
        1.2
        3.4.5
        """,
    },
    "text-heavy-centered": {
        "description": "Centered text that is clearly not math (e.g. Page numbers, CONFIDENTIAL)",
        "content": """               CONFIDENTIAL              
        
             Page 1 of 10             
        
           SECTION 5 - OVERVIEW           
        
              DO NOT DISTRIBUTE           
        """,
    },
    "inline-vs-display": {
        "description": "Mix of inline math $x$ and display math $$x$$ to test segmentation",
        "content": """Let $x$ be a variable.
        
        $$ x = y + 2 $$
        
        If we take $y$ to be 5, then:
        
        $$ x = 7 $$
        
        Therefore $x > y$ holds true.
        """,
    },
}

