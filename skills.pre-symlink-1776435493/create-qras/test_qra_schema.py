"""
Pytest tests for CWE independent QRA schema validation.

Tests both Pydantic shape validation and grounding validation against source records.
"""
from __future__ import annotations
from copy import deepcopy

import pytest
from pydantic import ValidationError

from qra_schema import QRAResult, validate_qra_payload


@pytest.fixture
def record_sections() -> dict[str, str]:
    return {
        "description": (
            "The product performs operations on a memory buffer, but it reads from or writes to "
            "a memory location outside the buffer's intended boundary. This may result in read or "
            "write operations on unexpected memory locations that could be linked to other variables, "
            "data structures, or internal program data."
        ),
        "extended_description": "",
        "likelihood_of_exploit": "High",
        "common_consequences": (
            "If the memory accessible by the attacker can be effectively controlled, it may be "
            "possible to execute arbitrary code, as with a standard buffer overflow. "
            "If the attacker can overwrite a pointer's worth of memory (usually 32 or 64 bits), "
            "they can alter the intended control flow by redirecting a function pointer to their own "
            "malicious code. Even when the attacker can only modify a single byte arbitrary code "
            "execution can be possible. Sometimes this is because the same problem can be exploited "
            "repeatedly to the same effect. Other times it is because the attacker can overwrite "
            "security-critical application-specific data -- such as a flag indicating whether the "
            "user is an administrator.\n"
            "Out of bounds memory access will very likely result in the corruption of relevant "
            "memory, and perhaps instructions, possibly leading to a crash. Other attacks leading "
            "to lack of availability are possible, including putting the program into an infinite "
            "loop.\n"
            "In the case of an out-of-bounds read, the attacker may have access to sensitive "
            "information. If the sensitive information contains system details, such as the current "
            "buffer's position in memory, this knowledge can be used to craft further attacks, "
            "possibly with more severe consequences."
        ),
        "modes_of_introduction": "- Phase: Implementation",
        "potential_mitigations": (
            "Use a language that does not allow this weakness to occur or provides constructs that "
            "make this weakness easier to avoid. For example, many languages that perform their own "
            "memory management, such as Java and Perl, are not subject to buffer overflows. Other "
            "languages, such as Ada and C#, typically provide overflow protection, but the protection "
            "can be disabled by the programmer. Be wary that a language's interface to native code "
            "may still be subject to overflows, even if the language itself is theoretically safe.\n"
            "Use a vetted library or framework that does not allow this weakness to occur or provides "
            "constructs that make this weakness easier to avoid. Examples include the Safe C String "
            "Library (SafeStr) by Messier and Viega [REF-57], and the Strsafe.h library from Microsoft "
            "[REF-56]. These libraries provide safer versions of overflow-prone string-handling functions.\n"
            "Use automatic buffer overflow detection mechanisms that are offered by certain compilers "
            "or compiler extensions. Examples include: the Microsoft Visual Studio /GS flag, Fedora/Red "
            "Hat FORTIFY_SOURCE GCC flag, StackGuard, and ProPolice, which provide various mechanisms "
            "including canary-based detection and range/index checking. D3-SFCV (Stack Frame Canary "
            "Validation) from D3FEND [REF-1334] discusses canary-based detection in detail.\n"
            "Consider adhering to the following rules when allocating and managing an application's "
            "memory: Double check that the buffer is as large as specified. When using functions that "
            "accept a number of bytes to copy, such as strncpy(), be aware that if the destination "
            "buffer size is equal to the source buffer size, it may not NULL-terminate the string. "
            "Check buffer boundaries if accessing the buffer in a loop and make sure there is no danger "
            "of writing past the allocated space. If necessary, truncate all input strings to a "
            "reasonable length before passing them to the copy and concatenation functions.\n"
            "Run or compile the software using features or extensions that randomly arrange the positions "
            "of a program's executable and libraries in memory. Because this makes the addresses "
            "unpredictable, it can prevent an attacker from reliably jumping to exploitable code. "
            "Examples include Address Space Layout Randomization (ASLR) [REF-58] [REF-60] and "
            "Position-Independent Executables (PIE) [REF-64]. Imported modules may be similarly "
            "realigned if their default memory addresses conflict with other modules, in a process known "
            "as 'rebasing' (for Windows) and 'prelinking' (for Linux) [REF-1332] using randomly "
            "generated addresses. ASLR for libraries cannot be used in conjunction with prelink since "
            "it would require relocating the libraries at run-time, defeating the whole purpose of "
            "prelinking. For more information on these techniques see D3-SAOR (Segment Address Offset "
            "Randomization) from D3FEND [REF-1335].\n"
            "Use a CPU and operating system that offers Data Execution Protection (using hardware NX "
            "or XD bits) or the equivalent techniques that simulate this feature in software, such as "
            "PaX [REF-60] [REF-61]. These techniques ensure that any instruction executed is exclusively "
            "at a memory address that is part of the code segment. For more information on these "
            "techniques see D3-PSEP (Process Segment Execution Prevention) from D3FEND [REF-1336].\n"
            "Replace unbounded copy functions with analogous functions that support length arguments, "
            "such as strcpy with strncpy. Create these if they are not available."
        ),
        "observed_examples": (
            "CVE-2021-22991: Incorrect URI normalization in application traffic product leads to "
            "buffer overflow, as exploited in the wild per CISA KEV.\n"
            "CVE-2020-29557: Buffer overflow in Wi-Fi router web interface, as exploited in the wild "
            "per CISA KEV.\n"
            "CVE-2009-2550: Classic stack-based buffer overflow in media player using a long entry in "
            "a playlist\n"
            "CVE-2009-2403: Heap-based buffer overflow in media player using a long entry in a playlist\n"
            "CVE-2009-0689: large precision value in a format string triggers overflow"
        ),
    }


@pytest.fixture
def valid_payload() -> dict:
    return {
        "source_framework": "CWE",
        "source_id": "CWE-119",
        "pair_count": 4,
        "abstained": False,
        "pairs": [
            {
                "pair_id": "CWE-119-QRA-1",
                "pair_type": "scope_clarification",
                "actionable_for": ["vulnerability_assessment"],
                "question": "What kinds of memory operations are covered by CWE-119?",
                "reasoning": (
                    "The description defines the weakness as operations on a memory buffer that "
                    "read from or write to a memory location outside the buffer's intended boundary."
                ),
                "answer": (
                    "CWE-119 covers operations on a memory buffer where the product reads from or "
                    "writes to a memory location outside the buffer's intended boundary."
                ),
                "confidence": "high",
                "evidence": [
                    {
                        "field": "description",
                        "quote": (
                            "The product performs operations on a memory buffer, but it reads from or "
                            "writes to a memory location outside the buffer's intended boundary."
                        ),
                    }
                ],
            },
            {
                "pair_id": "CWE-119-QRA-2",
                "pair_type": "risk_context",
                "actionable_for": ["risk_analysis", "vulnerability_assessment"],
                "question": "Why is CWE-119 a serious security risk?",
                "reasoning": (
                    "The record states that out-of-bounds memory access can lead to arbitrary code "
                    "execution, corruption of relevant memory, crashes, and exposure of sensitive "
                    "information. It also explicitly lists the likelihood of exploit as high."
                ),
                "answer": (
                    "CWE-119 is a serious security risk because the record says it may be possible "
                    "to execute arbitrary code, corrupt relevant memory, cause crashes, and expose "
                    "sensitive information. The record also states that the likelihood of exploit is high."
                ),
                "confidence": "high",
                "evidence": [
                    {"field": "likelihood_of_exploit", "quote": "High"},
                    {
                        "field": "common_consequences",
                        "quote": (
                            "If the memory accessible by the attacker can be effectively controlled, "
                            "it may be possible to execute arbitrary code, as with a standard buffer overflow."
                        ),
                    },
                    {
                        "field": "common_consequences",
                        "quote": (
                            "Out of bounds memory access will very likely result in the corruption of "
                            "relevant memory, and perhaps instructions, possibly leading to a crash."
                        ),
                    },
                    {
                        "field": "common_consequences",
                        "quote": (
                            "In the case of an out-of-bounds read, the attacker may have access to "
                            "sensitive information."
                        ),
                    },
                ],
            },
            {
                "pair_id": "CWE-119-QRA-3",
                "pair_type": "implementation_guidance",
                "actionable_for": ["implementation"],
                "question": "How should a developer mitigate CWE-119?",
                "reasoning": (
                    "The mitigation section explicitly recommends safer languages or libraries, "
                    "compiler protections, careful buffer boundary management, and replacement of "
                    "unbounded copy functions."
                ),
                "answer": (
                    "A developer should mitigate CWE-119 by using languages or libraries that make "
                    "the weakness easier to avoid, enabling available buffer overflow detection "
                    "mechanisms, checking buffer boundaries carefully, and replacing unbounded copy "
                    "functions with alternatives that support length arguments."
                ),
                "confidence": "high",
                "evidence": [
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Use a language that does not allow this weakness to occur or provides "
                            "constructs that make this weakness easier to avoid."
                        ),
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Use a vetted library or framework that does not allow this weakness to "
                            "occur or provides constructs that make this weakness easier to avoid."
                        ),
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Use automatic buffer overflow detection mechanisms that are offered by "
                            "certain compilers or compiler extensions."
                        ),
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Check buffer boundaries if accessing the buffer in a loop and make sure "
                            "there is no danger of writing past the allocated space."
                        ),
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Replace unbounded copy functions with analogous functions that support "
                            "length arguments, such as strcpy with strncpy."
                        ),
                    },
                ],
            },
            {
                "pair_id": "CWE-119-QRA-4",
                "pair_type": "assessment_criteria",
                "actionable_for": ["audit", "vulnerability_assessment"],
                "question": "What should an auditor or reviewer look for when assessing exposure to CWE-119?",
                "reasoning": (
                    "The record gives explicit mitigations that can be used as review criteria, and "
                    "it states that the weakness is introduced in the implementation phase."
                ),
                "answer": (
                    "An auditor or reviewer assessing CWE-119 should look for implementation-phase "
                    "code that fails to keep buffers as large as specified, lacks boundary checks when "
                    "accessing buffers in loops, or still uses unbounded copy functions instead of "
                    "alternatives with length arguments."
                ),
                "confidence": "high",
                "evidence": [
                    {"field": "modes_of_introduction", "quote": "- Phase: Implementation"},
                    {
                        "field": "potential_mitigations",
                        "quote": "Double check that the buffer is as large as specified.",
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Check buffer boundaries if accessing the buffer in a loop and make sure "
                            "there is no danger of writing past the allocated space."
                        ),
                    },
                    {
                        "field": "potential_mitigations",
                        "quote": (
                            "Replace unbounded copy functions with analogous functions that support "
                            "length arguments, such as strcpy with strncpy."
                        ),
                    },
                ],
            },
        ],
    }


@pytest.fixture
def valid_abstain_payload() -> dict:
    return {
        "source_framework": "CWE",
        "source_id": "CWE-119",
        "pair_count": 0,
        "abstained": True,
        "abstain_reason_code": "insufficient_grounded_content",
        "abstain_reason": "The record does not contain enough grounded content for useful QRA pairs.",
        "pairs": [],
    }


def test_valid_payload_passes(record_sections: dict[str, str], valid_payload: dict) -> None:
    result = validate_qra_payload(valid_payload, record_sections)
    assert isinstance(result, QRAResult)
    assert result.source_id == "CWE-119"
    assert result.pair_count == 4
    assert result.abstained is False


def test_valid_abstain_payload_passes(
    record_sections: dict[str, str],
    valid_abstain_payload: dict,
) -> None:
    result = validate_qra_payload(valid_abstain_payload, record_sections)
    assert result.abstained is True
    assert result.pair_count == 0
    assert result.pairs == []


def test_pair_count_mismatch_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pair_count"] = 3

    with pytest.raises(ValidationError, match="pair_count must equal len\\(pairs\\)"):
        validate_qra_payload(payload, record_sections)


def test_question_missing_cwe_id_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][0]["question"] = "What kinds of memory operations are covered?"

    with pytest.raises(ValidationError, match="question must explicitly contain source_id"):
        validate_qra_payload(payload, record_sections)


def test_duplicate_pair_id_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][1]["pair_id"] = payload["pairs"][0]["pair_id"]

    with pytest.raises(ValidationError, match="duplicate pair_id"):
        validate_qra_payload(payload, record_sections)


def test_duplicate_actionable_for_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][1]["actionable_for"] = ["risk_analysis", "risk_analysis"]

    with pytest.raises(ValidationError, match="actionable_for must not contain duplicates"):
        validate_qra_payload(payload, record_sections)


def test_abstained_with_pairs_fails(
    record_sections: dict[str, str],
    valid_abstain_payload: dict,
) -> None:
    payload = deepcopy(valid_abstain_payload)
    payload["pairs"] = [
        {
            "pair_id": "CWE-119-QRA-1",
            "pair_type": "risk_context",
            "actionable_for": ["risk_analysis"],
            "question": "Why is CWE-119 dangerous?",
            "reasoning": "Because it can cause security impact.",
            "answer": "It can cause security impact.",
            "confidence": "medium",
            "evidence": [
                {"field": "likelihood_of_exploit", "quote": "High"},
            ],
        }
    ]
    payload["pair_count"] = 1

    with pytest.raises(ValidationError, match="abstained result must have pair_count == 0"):
        validate_qra_payload(payload, record_sections)


def test_non_abstained_with_reason_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["abstain_reason_code"] = "only_generic_pairs_available"
    payload["abstain_reason"] = "unexpected"

    with pytest.raises(ValidationError, match="non-abstained result must not include abstain_reason"):
        validate_qra_payload(payload, record_sections)


def test_quote_not_found_in_section_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][0]["evidence"][0]["quote"] = "This sentence does not exist in the record."

    with pytest.raises(ValueError, match="quote not found in section 'description'"):
        validate_qra_payload(payload, record_sections)


def test_missing_record_section_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    bad_sections = deepcopy(record_sections)
    del bad_sections["description"]

    with pytest.raises(ValueError, match="missing source section 'description'"):
        validate_qra_payload(payload, bad_sections)


def test_extra_field_rejected(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][0]["unexpected_field"] = "should fail"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_qra_payload(payload, record_sections)


def test_invalid_source_id_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["source_id"] = "119"

    with pytest.raises(ValidationError, match="source_id must match CWE-<number>"):
        validate_qra_payload(payload, record_sections)


def test_invalid_enum_value_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][0]["pair_type"] = "mitigation_help"

    with pytest.raises(ValidationError):
        validate_qra_payload(payload, record_sections)


def test_blank_quote_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][0]["evidence"][0]["quote"] = "   "

    with pytest.raises(ValidationError, match="quote must not be blank"):
        validate_qra_payload(payload, record_sections)


def test_duplicate_question_fails(record_sections: dict[str, str], valid_payload: dict) -> None:
    payload = deepcopy(valid_payload)
    payload["pairs"][1]["question"] = payload["pairs"][0]["question"]

    with pytest.raises(ValidationError, match="duplicate or near-duplicate question"):
        validate_qra_payload(payload, record_sections)


def test_payload_can_be_validated_directly_with_model(valid_payload: dict) -> None:
    """
    This shows the difference between schema validation and grounding validation.
    The model can validate shape without access to record_sections.
    """
    result = QRAResult.model_validate(valid_payload)
    assert result.pair_count == 4
    assert result.abstained is False
