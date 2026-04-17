# QRA Question Quality Examples by Persona

**Purpose**: One-shot examples for LLM prompts to teach good vs bad question patterns for corpus-grounded QRA generation, organized by questioner persona.

**Usage**: Include relevant persona examples in SPARTA QRA generation prompts to guide the LLM.

**SPARTA Personas**: Layperson, Project Manager, Compliance Officer, Cybersecurity Expert

---

## Layperson Questions (Simple - 5-10 words)

### ✅ Good Layperson Questions

**Example 1**: What does CM-0049 verify before installing firmware?
- **Why it's good**: Simple language, names entity, asks about basic function
- **Complexity**: Simple (8 words)
- **Persona**: Layperson needs basic understanding

**Example 2**: How does Firmware Update Verification protect against malware?
- **Why it's good**: Uses common term "malware", asks about protective function
- **Complexity**: Simple (9 words)
- **Persona**: Non-technical user understanding benefit

**Example 3**: What files does CM-0049 check during firmware updates?
- **Why it's good**: Concrete question about observable behavior
- **Complexity**: Simple (9 words)  
- **Persona**: User wants to know what happens

### ❌ Bad Layperson Questions

**Example 1**: Does CM-0049 work?
- **Why it's bad**: Yes/no question, too vague
- **Fixed**: What does CM-0049 check when updating firmware?

**Example 2**: Is it secure?
- **Why it's bad**: Pronoun usage, generic security query
- **Fixed**: How does Firmware Update Verification protect against unauthorized changes?

**Example 3**: What does this control do?
- **Why it's bad**: Uses pronoun "this", too generic
- **Fixed**: What does CM-0049 verify before allowing firmware installation?

---

## Project Manager Questions (Medium - 10-15 words)

### ✅ Good Project Manager Questions

**Example 1**: What are the key verification steps CM-0049 performs to prevent unauthorized firmware installation?
- **Why it's good**: Business-focused ("key steps"), risk-aware ("prevent unauthorized")
- **Complexity**: Medium (13 words)
- **Persona**: PM needs to explain process to stakeholders

**Example 2**: How does CM-0049 ensure firmware updates maintain system integrity during deployment cycles?
- **Why it's good**: Process-oriented ("deployment cycles"), outcome-focused ("maintain integrity")
- **Complexity**: Medium (12 words)
- **Persona**: PM concerned with operational impact

**Example 3**: What validation requirements must firmware packages meet before CM-0049 approves installation?
- **Why it's good**: Requirements-driven, approval process focus
- **Complexity**: Medium (12 words)
- **Persona**: PM needs to document process

**Example 4**: How does Firmware Update Verification impact the overall system update workflow timing?
- **Why it's good**: Workflow integration, timing concerns
- **Complexity**: Medium (12 words)
- **Persona**: PM planning deployment schedules

### ❌ Bad Project Manager Questions

**Example 1**: Does CM-0049 slow down updates?
- **Why it's bad**: Yes/no question, subjective "slow down"
- **Fixed**: What is the average verification time CM-0049 adds to the firmware update process?

**Example 2**: Is firmware verification part of our security framework?
- **Why it's bad**: Yes/no question, vague "security framework"
- **Fixed**: How does CM-0049's firmware verification integrate with the organization's security control framework?

**Example 3**: Can this be automated?
- **Why it's bad**: Yes/no, uses pronoun, vague "this"
- **Fixed**: What automation capabilities does CM-0049 provide for firmware verification workflows?

---

## Compliance Officer Questions (Medium-Complex - 12-18 words)

### ✅ Good Compliance Questions

**Example 1**: What specific NIST SP 800-53 control requirements does CM-0049 satisfy through its firmware verification mechanisms?
- **Why it's good**: Regulatory mapping, specific standard reference
- **Complexity**: Medium-Complex (15 words)
- **Persona**: Compliance needs audit trail

**Example 2**: How does CM-0049 maintain audit logs of firmware verification attempts including failed authentication events?
- **Why it's good**: Audit trail focus, compliance documentation
- **Complexity**: Medium-Complex (15 words)
- **Persona**: Compliance needs evidence trail

**Example 3**: What cryptographic algorithm standards does CM-0049 enforce to meet FIPS 140-2 requirements for firmware validation?
- **Why it's good**: Standards compliance, specific regulatory requirement
- **Complexity**: Medium-Complex (16 words)
- **Persona**: Compliance mapping to regulations

### ❌ Bad Compliance Questions

**Example 1**: Does CM-0049 meet compliance requirements?
- **Why it's bad**: Yes/no, vague "compliance requirements"
- **Fixed**: Which NIST SP 800-53 controls does CM-0049 address through its firmware verification capabilities?

**Example 2**: Is the firmware process auditable?
- **Why it's bad**: Yes/no, generic "auditable"
- **Fixed**: What audit trail information does CM-0049 generate for firmware verification events?

---

## Cybersecurity Expert Questions (Complex - 15+ words)

### ✅ Good Cybersecurity Expert Questions

**Example 1**: What specific cryptographic algorithms does CM-0049 use to verify firmware signatures and how does it validate certificate chain authenticity?
- **Why it's good**: Multi-part technical, specific algorithms, certificate validation
- **Complexity**: Complex (20 words)
- **Persona**: Expert needs implementation details

**Example 2**: How does CM-0049 handle firmware rollback attacks and what specific mechanisms prevent unauthorized version downgrades during the update process?
- **Why it's good**: Attack scenario, specific threat model, multi-mechanism query
- **Complexity**: Complex (20 words)
- **Persona**: Expert analyzing threat vectors

**Example 3**: What cryptographic primitives and key management protocols does CM-0049 implement to establish trust in the firmware verification process?
- **Why it's good**: Deep technical (primitives, key management), trust chain focus
- **Complexity**: Complex (20 words)
- **Persona**: Expert evaluating cryptographic implementation

**Example 4**: Explain how CM-0049 detects tampered firmware binaries during integrity checks and what specific hash algorithms verify package authenticity?
- **Why it's good**: Multi-part (detection + algorithms), specific technical mechanisms
- **Complexity**: Complex (21 words)
- **Persona**: Expert reviewing threat detection

**Example 5**: What side-channel attack mitigations does CM-0049 implement during cryptographic verification operations to prevent timing-based signature extraction?
- **Why it's good**: Advanced threat model, specific attack vector, mitigation focus
- **Complexity**: Complex (20 words)
- **Persona**: Expert assessing advanced threats

### ❌ Bad Cybersecurity Expert Questions

**Example 1**: Does CM-0049 use strong cryptography?
- **Why it's bad**: Yes/no, vague "strong cryptography"
- **Fixed**: What specific cryptographic algorithms and key lengths does CM-0049 use for firmware signature verification?

**Example 2**: Can firmware verification be bypassed?
- **Why it's bad**: Yes/no, speculation about attacks
- **Fixed**: What technical controls does CM-0049 implement to prevent firmware verification bypass through code injection attacks?

**Example 3**: Is the cryptographic implementation secure?
- **Why it's bad**: Yes/no, subjective "secure"  
- **Fixed**: What cryptographic best practices does CM-0049 follow to ensure firmware signature validation resists known attack patterns?

---

## Cross-Persona Comparison

### Same Topic, Different Personas

**Topic**: Firmware signature verification

**Layperson**: What does CM-0049 check to make sure firmware is safe?
- Simple language, basic safety concept, 10 words

**Project Manager**: What verification steps does CM-0049 perform to validate firmware authenticity before installation?
- Process-focused, validation requirements, 13 words

**Compliance**: What NIST-approved cryptographic standards does CM-0049 use to verify firmware signatures for regulatory compliance?
- Standards-focused, regulatory mapping, 15 words

**Cybersecurity Expert**: What specific cryptographic algorithms and certificate chain validation mechanisms does CM-0049 implement to verify firmware signature authenticity and establish provenance trust?
- Technical depth, multi-mechanism, attack-aware, 24 words

---

## Pattern Templates by Persona

### Layperson (Simple - 5-10 words)
```
✅ What does [ENTITY] check [when/before] [action]?
✅ How does [ENTITY] protect against [common-threat]?
✅ What files does [ENTITY] verify during [process]?
❌ Does [ENTITY] work?
❌ Is it secure?
```

### Project Manager (Medium - 10-15 words)
```
✅ What [key/main] [steps/requirements] does [ENTITY] perform to [outcome]?
✅ How does [ENTITY] ensure [quality-metric] during [workflow-phase]?
✅ What validation requirements must [input] meet before [ENTITY] approves [action]?
❌ Does [ENTITY] slow down [process]?
❌ Can this be automated?
```

### Compliance (Medium-Complex - 12-18 words)
```
✅ What [standard/regulation] requirements does [ENTITY] satisfy through its [mechanism]?
✅ How does [ENTITY] maintain [audit/documentation] of [events] including [failure-cases]?
✅ What [standard-requirement] does [ENTITY] enforce to meet [regulation] for [process]?
❌ Does [ENTITY] meet compliance?
❌ Is [process] auditable?
```

### Cybersecurity Expert (Complex - 15+ words)
```
✅ What specific [technical-mechanisms] does [ENTITY] use to [action] and how does it [validate/prevent] [attack-vector]?
✅ How does [ENTITY] handle [attack-type] and what mechanisms prevent [specific-threat] during [process-phase]?
✅ What [cryptographic-primitives] and [protocols] does [ENTITY] implement to [establish/ensure] [security-property]?
❌ Does [ENTITY] use strong cryptography?
❌ Can [process] be bypassed?
```

---

## Prompt Integration by Persona

### For Layperson QRA Generation
```
PERSONA: Layperson (non-technical user)
COMPLEXITY: Simple (5-10 words)
LANGUAGE: Common terms, avoid jargon

GOOD EXAMPLES:
- "What does CM-0049 verify before installing firmware?"
- "How does Firmware Update Verification protect against malware?"

BAD EXAMPLES (DO NOT GENERATE):
- "Does CM-0049 work?" (yes/no)
- "Is it secure?" (pronoun + vague)
```

### For Project Manager QRA Generation
```
PERSONA: Project Manager (process/workflow focus)
COMPLEXITY: Medium (10-15 words)
LANGUAGE: Business outcomes, workflow integration

GOOD EXAMPLES:
- "What key verification steps does CM-0049 perform to prevent unauthorized firmware installation?"
- "How does CM-0049 ensure firmware updates maintain system integrity during deployment cycles?"

BAD EXAMPLES (DO NOT GENERATE):
- "Does CM-0049 slow down updates?" (yes/no + subjective)
- "Can this be automated?" (pronoun + yes/no)
```

### For Cybersecurity Expert QRA Generation
```
PERSONA: Cybersecurity Expert (technical depth)
COMPLEXITY: Complex (15+ words)
LANGUAGE: Technical mechanisms, attack vectors, cryptographic details

GOOD EXAMPLES:
- "What specific cryptographic algorithms does CM-0049 use to verify firmware signatures and validate certificate chain authenticity?"
- "How does CM-0049 handle firmware rollback attacks and what mechanisms prevent unauthorized version downgrades?"

BAD EXAMPLES (DO NOT GENERATE):
- "Does CM-0049 use strong cryptography?" (yes/no + vague)
- "Can firmware verification be bypassed?" (yes/no + speculation)
```

---

## Validation by Persona

```python
from qra_validators import validate_qra_question

# Layperson question
validate_qra_question(
    "What does CM-0049 verify before installing firmware?",
    ["CM-0049", "Firmware Update Verification"],
    expected_complexity="simple"  # 5-10 word threshold
)

# Project Manager question
validate_qra_question(
    "What key verification steps does CM-0049 perform to prevent unauthorized installation?",
    ["CM-0049"],
    expected_complexity="medium"  # 10-15 word threshold
)

# Cybersecurity Expert question
validate_qra_question(
    "What specific cryptographic algorithms does CM-0049 use to verify firmware signatures and validate certificate chains?",
    ["CM-0049"],
    expected_complexity="complex"  # 15+ word threshold
)
```

---

**Last updated**: 2026-02-01  
**Version**: 2.0 (Persona-organized)  
**For**: SPARTA QRA Generation Pipeline
