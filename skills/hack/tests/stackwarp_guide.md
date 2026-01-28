# Understanding StackWarp (CVE-2025-29943)

## Introduction

StackWarp is a critical integrity break against AMD SEV-SNP on Zen 1–5 processors. It works by corrupting the stack pointer inside a confidential Virtual Machine (VM).

## Mechanism

The attack leverages a race condition in the microcode handling of the `VMRUN` instruction. By manipulating external interrupts at a specific cycle, an attacker can desynchronize the internal stack pointer tracking.

## Exploitation Steps

To exploit StackWarp, you must:

1.  Target an AMD SEV-SNP protected VM.
2.  Trigger the specific interrupt simulated by `sw_interrupt_0x29`.
3.  Monitor the `RSP` register for deviation.
4.  Inject a ROP chain when the stack alignment is offset.

## Impact

Successful exploitation allows arbitrary code execution within the confidential VM context, bypassing SEV-SNP protections.
