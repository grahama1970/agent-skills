# Quality Sampling Review

Review each case and mark as CORRECT or INCORRECT.


## ATT&CK (3 samples)

### T1584.004: Server
**Description:** Adversaries may compromise third-party servers that can be used during targeting. Use of servers allows an adversary to stage, launch, and execute an operation. During post-compromise activity, advers...
**Predicted:** C=['Corruption'] T=['Exploit'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### T1053.002: At
**Description:** Adversaries may abuse the [at](https://attack.mitre.org/software/S0110) utility to perform task scheduling for initial or recurring execution of malicious code. The [at](https://attack.mitre.org/softw...
**Predicted:** C=['Corruption'] T=['Persist'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### T1059: Command and Scripting Interpreter
**Description:** Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries. These interfaces and languages provide ways of interacting with computer systems and are a common featu...
**Predicted:** C=['Corruption'] T=['Exploit'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________


## NIST (3 samples)

### AU-12 (1): SYSTEM-WIDE / TIME-CORRELATED AUDIT TRAIL
**Description:** The information system compiles audit records from [Assignment: organization-defined information system components] into a system-wide (logical or physical) audit trail that is time-correlated to with...
**Predicted:** C=['Resilience'] T=['Detect'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### CA-3: SYSTEM INTERCONNECTIONS
**Description:** The organization:...
**Predicted:** C=['Loyalty'] T=['Harden'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### SA-17 (1): FORMAL POLICY MODEL
**Description:** The organization requires the developer of the information system, system component, or information system service to:...
**Predicted:** C=['Loyalty'] T=['Harden'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________


## CWE (3 samples)

### CWE-1038: Insecure Automated Optimizations
**Description:** The product uses a mechanism that automatically optimizes code, e.g. to improve a characteristic such as performance, but the optimizations can have an unintended side effect that might violate an int...
**Predicted:** C=['Fragility'] T=['Exploit'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### CWE-312: Cleartext Storage of Sensitive Information
**Description:** The product stores sensitive information in cleartext within a resource that might be accessible to another control sphere....
**Predicted:** C=['Fragility'] T=['Exploit'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### CWE-1421: Exposure of Sensitive Information in Shared Microarchitectural Structures during Transient Execution
**Description:** A processor event may allow transient operations to access architecturally restricted data (for example, in another address space) in a shared microarchitectural structure (for example, a CPU cache), ...
**Predicted:** C=['Fragility'] T=['Exploit'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________


## D3FEND (3 samples)

### d3f:D3-DE: Decoy Environment
**Description:** A Decoy Environment comprises hosts and networks for the purposes of deceiving an attacker....
**Predicted:** C=['Stealth'] T=['Evade'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### d3f:D3-NI: Network Isolation
**Description:** Network Isolation techniques prevent network hosts from accessing non-essential system network resources....
**Predicted:** C=['Resilience'] T=['Isolate'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________

### d3f:D3-NTA: Network Traffic Analysis
**Description:** Analyzing intercepted or summarized computer network traffic to detect unauthorized activity....
**Predicted:** C=['Resilience'] T=['Detect'] (conf=0.90)
**Correct?** [ ] Yes  [ ] No
**Notes:** _________________


---
Total samples: 12
Quality Score = (Correct / Total) * 100%