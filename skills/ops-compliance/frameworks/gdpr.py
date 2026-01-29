#!/usr/bin/env python3
"""
GDPR compliance checks.

Implements checks for GDPR Articles focusing on data protection.
"""
import re
from pathlib import Path
from typing import Any


# Common PII patterns
PII_PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    "date_of_birth": r'\b(dob|birth_date|birthdate|date_of_birth)\b',
}

# PII field name patterns (in code)
PII_FIELD_PATTERNS = [
    r'first_?name',
    r'last_?name',
    r'full_?name',
    r'email',
    r'phone',
    r'address',
    r'ssn',
    r'social_security',
    r'credit_card',
    r'birth_?date',
    r'passport',
    r'driver_?license',
    r'national_id',
    r'ip_?address',
    r'user_?agent',
    r'location',
    r'gps',
    r'latitude',
    r'longitude',
]


def run_gdpr_checks(path: Path) -> list[dict[str, Any]]:
    """
    Run GDPR compliance checks.

    Key Articles checked:
    - Article 5: Principles of processing (data minimization)
    - Article 6: Lawfulness of processing (consent)
    - Article 17: Right to erasure
    - Article 25: Data protection by design
    - Article 32: Security of processing

    Args:
        path: Directory to check

    Returns:
        List of check results with article, status, description, finding
    """
    checks: list[dict[str, Any]] = []
    path = Path(path)

    # Article 5: Data inventory / PII detection
    checks.extend(_check_pii_handling(path))

    # Article 6: Consent mechanisms
    checks.extend(_check_consent(path))

    # Article 17: Right to erasure
    checks.extend(_check_data_deletion(path))

    # Article 25: Data protection by design
    checks.extend(_check_data_protection(path))

    # Article 32: Security measures
    checks.extend(_check_security_measures(path))

    return checks


def _check_pii_handling(path: Path) -> list[dict[str, Any]]:
    """Check Article 5: PII data inventory."""
    checks: list[dict[str, Any]] = []

    pii_locations: list[dict[str, Any]] = []

    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")

            # Check for PII field patterns in code
            for pattern in PII_FIELD_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    pii_locations.append({
                        "file": str(py_file.relative_to(path)),
                        "type": pattern.replace(r'_?', '_'),
                        "count": len(matches),
                    })
        except Exception:
            pass

    if pii_locations:
        # Group by type
        pii_types = set(loc["type"] for loc in pii_locations)
        checks.append({
            "control_id": "GDPR-5.1",
            "article": "Article 5 - Data Minimization",
            "status": "warning",
            "description": "PII data inventory",
            "finding": f"Found {len(pii_types)} types of PII fields in {len(pii_locations)} locations",
            "details": pii_locations[:10],
            "remediation": "Document data inventory and ensure each PII field has a lawful basis",
        })
    else:
        checks.append({
            "control_id": "GDPR-5.1",
            "article": "Article 5 - Data Minimization",
            "status": "pass",
            "description": "PII data inventory",
            "finding": "No obvious PII field patterns detected",
        })

    # Check for data logging (potential PII leakage)
    log_pii_patterns = [
        r'log.*email',
        r'log.*password',
        r'log.*user',
        r'print.*email',
        r'print.*password',
    ]

    log_leaks: list[str] = []
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in log_pii_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    log_leaks.append(str(py_file.relative_to(path)))
                    break
        except Exception:
            pass

    if log_leaks:
        checks.append({
            "control_id": "GDPR-5.2",
            "article": "Article 5 - Data Minimization",
            "status": "warning",
            "description": "No PII in logs",
            "finding": f"Potential PII logging in {len(log_leaks)} files",
            "details": log_leaks[:5],
            "remediation": "Review logging to ensure PII is not logged or is properly masked",
        })
    else:
        checks.append({
            "control_id": "GDPR-5.2",
            "article": "Article 5 - Data Minimization",
            "status": "pass",
            "description": "No obvious PII logging detected",
        })

    return checks


def _check_consent(path: Path) -> list[dict[str, Any]]:
    """Check Article 6: Consent mechanisms."""
    checks: list[dict[str, Any]] = []

    consent_patterns = [
        r'consent',
        r'opt_?in',
        r'opt_?out',
        r'gdpr_?consent',
        r'privacy_?consent',
        r'terms_?accepted',
        r'marketing_?consent',
    ]

    has_consent = False
    consent_files: list[str] = []

    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in consent_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_consent = True
                    consent_files.append(str(py_file.relative_to(path)))
                    break
        except Exception:
            pass

    if has_consent:
        checks.append({
            "control_id": "GDPR-6.1",
            "article": "Article 6 - Lawful Processing",
            "status": "pass",
            "description": "Consent mechanisms present",
            "finding": f"Found consent-related code in {len(consent_files)} files",
            "details": consent_files[:5],
        })
    else:
        checks.append({
            "control_id": "GDPR-6.1",
            "article": "Article 6 - Lawful Processing",
            "status": "warning",
            "description": "Consent mechanisms present",
            "finding": "No consent-related patterns detected",
            "remediation": "Implement consent collection for personal data processing",
        })

    return checks


def _check_data_deletion(path: Path) -> list[dict[str, Any]]:
    """Check Article 17: Right to erasure."""
    checks: list[dict[str, Any]] = []

    deletion_patterns = [
        r'delete_?user',
        r'remove_?user',
        r'erase_?data',
        r'gdpr_?delete',
        r'right_?to_?be_?forgotten',
        r'data_?deletion',
        r'purge_?user',
        r'anonymize',
    ]

    has_deletion = False
    deletion_files: list[str] = []

    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in deletion_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_deletion = True
                    deletion_files.append(str(py_file.relative_to(path)))
                    break
        except Exception:
            pass

    if has_deletion:
        checks.append({
            "control_id": "GDPR-17.1",
            "article": "Article 17 - Right to Erasure",
            "status": "pass",
            "description": "Data deletion capability exists",
            "finding": f"Found deletion-related code in {len(deletion_files)} files",
            "details": deletion_files[:5],
        })
    else:
        checks.append({
            "control_id": "GDPR-17.1",
            "article": "Article 17 - Right to Erasure",
            "status": "warning",
            "description": "Data deletion capability exists",
            "finding": "No data deletion patterns detected",
            "remediation": "Implement user data deletion functionality for GDPR compliance",
        })

    return checks


def _check_data_protection(path: Path) -> list[dict[str, Any]]:
    """Check Article 25: Data protection by design."""
    checks: list[dict[str, Any]] = []

    # Check for data minimization in APIs
    api_patterns = [
        r'@app\.(get|post|put|delete)',
        r'@router\.',
        r'def get\(',
        r'def post\(',
    ]

    # Check for privacy-by-design patterns
    privacy_patterns = [
        r'encryption',
        r'anonymize',
        r'pseudonymize',
        r'mask_?pii',
        r'redact',
        r'data_?protection',
    ]

    has_privacy_design = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in privacy_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_privacy_design = True
                    break
        except Exception:
            pass
        if has_privacy_design:
            break

    checks.append({
        "control_id": "GDPR-25.1",
        "article": "Article 25 - Data Protection by Design",
        "status": "pass" if has_privacy_design else "warning",
        "description": "Privacy-by-design patterns present",
        "finding": "Found privacy protection patterns" if has_privacy_design else "No explicit privacy-by-design patterns",
        "remediation": "Implement data anonymization, pseudonymization, or encryption for PII" if not has_privacy_design else None,
    })

    return checks


def _check_security_measures(path: Path) -> list[dict[str, Any]]:
    """Check Article 32: Security of processing."""
    checks: list[dict[str, Any]] = []

    # Check for encryption
    encryption_patterns = [
        r'cryptography',
        r'encrypt',
        r'aes',
        r'fernet',
        r'bcrypt',
        r'argon2',
        r'hashlib',
    ]

    has_encryption = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in encryption_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_encryption = True
                    break
        except Exception:
            pass
        if has_encryption:
            break

    checks.append({
        "control_id": "GDPR-32.1",
        "article": "Article 32 - Security of Processing",
        "status": "pass" if has_encryption else "warning",
        "description": "Encryption measures implemented",
        "finding": "Found encryption patterns" if has_encryption else "No encryption patterns detected",
        "remediation": "Implement encryption for personal data at rest and in transit" if not has_encryption else None,
    })

    # Check for access controls
    access_patterns = [
        r'@login_required',
        r'@permission',
        r'@roles_required',
        r'rbac',
        r'access_control',
        r'authorize',
    ]

    has_access_control = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in access_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_access_control = True
                    break
        except Exception:
            pass
        if has_access_control:
            break

    checks.append({
        "control_id": "GDPR-32.2",
        "article": "Article 32 - Security of Processing",
        "status": "pass" if has_access_control else "warning",
        "description": "Access controls implemented",
        "finding": "Found access control patterns" if has_access_control else "No access control patterns detected",
        "remediation": "Implement role-based access control for personal data" if not has_access_control else None,
    })

    return checks


if __name__ == "__main__":
    import json
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    results = run_gdpr_checks(target)
    print(json.dumps(results, indent=2))
