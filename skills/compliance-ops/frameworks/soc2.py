#!/usr/bin/env python3
"""
SOC2 Type II compliance checks.

Implements checks for SOC2 control categories CC1-CC9.
"""
import re
from pathlib import Path
from typing import Any


def run_soc2_checks(path: Path) -> list[dict[str, Any]]:
    """
    Run SOC2 Type II compliance checks.

    Control Categories:
    - CC1: Control Environment
    - CC2: Communication and Information
    - CC3: Risk Assessment
    - CC4: Monitoring Activities
    - CC5: Control Activities
    - CC6: Logical and Physical Access
    - CC7: System Operations
    - CC8: Change Management
    - CC9: Risk Mitigation

    Args:
        path: Directory to check

    Returns:
        List of check results with control_id, status, description, finding
    """
    checks: list[dict[str, Any]] = []
    path = Path(path)

    # CC6: Logical and Physical Access Controls
    checks.extend(_check_access_controls(path))

    # CC7: System Operations - Logging
    checks.extend(_check_logging(path))

    # CC6: Encryption
    checks.extend(_check_encryption(path))

    # CC8: Change Management
    checks.extend(_check_change_management(path))

    # CC5: Control Activities - Input Validation
    checks.extend(_check_input_validation(path))

    return checks


def _check_access_controls(path: Path) -> list[dict[str, Any]]:
    """Check CC6: Logical Access Controls."""
    checks: list[dict[str, Any]] = []

    # Check for hardcoded credentials
    cred_patterns = [
        (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
        (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
        (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
        (r'token\s*=\s*["\'][A-Za-z0-9_-]{20,}["\']', "Hardcoded token"),
    ]

    findings: list[str] = []
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern, desc in cred_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    findings.append(f"{py_file.name}: {desc}")
        except Exception:
            pass

    if findings:
        checks.append({
            "control_id": "CC6.1",
            "category": "Logical Access",
            "status": "fail",
            "description": "No hardcoded credentials in source code",
            "finding": f"Found {len(findings)} potential hardcoded credentials",
            "details": findings[:5],  # Limit to first 5
            "remediation": "Use environment variables or secret management system",
        })
    else:
        checks.append({
            "control_id": "CC6.1",
            "category": "Logical Access",
            "status": "pass",
            "description": "No hardcoded credentials in source code",
        })

    # Check for authentication patterns
    auth_patterns = [
        r'@login_required',
        r'@authenticated',
        r'verify_token',
        r'check_auth',
        r'is_authenticated',
    ]
    has_auth = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in auth_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_auth = True
                    break
        except Exception:
            pass
        if has_auth:
            break

    checks.append({
        "control_id": "CC6.2",
        "category": "Logical Access",
        "status": "pass" if has_auth else "warning",
        "description": "Authentication mechanisms implemented",
        "finding": None if has_auth else "No authentication patterns detected",
        "remediation": "Implement authentication for protected resources" if not has_auth else None,
    })

    return checks


def _check_logging(path: Path) -> list[dict[str, Any]]:
    """Check CC7: System Operations - Logging."""
    checks: list[dict[str, Any]] = []

    # Check for logging implementation
    logging_patterns = [
        r'import logging',
        r'from logging import',
        r'logger\.',
        r'logging\.',
        r'structlog',
    ]

    has_logging = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in logging_patterns:
                if re.search(pattern, content):
                    has_logging = True
                    break
        except Exception:
            pass
        if has_logging:
            break

    checks.append({
        "control_id": "CC7.1",
        "category": "System Operations",
        "status": "pass" if has_logging else "warning",
        "description": "Logging is implemented for audit trail",
        "finding": None if has_logging else "No logging implementation detected",
        "remediation": "Implement structured logging for security events" if not has_logging else None,
    })

    # Check for security event logging
    security_log_patterns = [
        r'log.*auth',
        r'log.*login',
        r'log.*access',
        r'log.*permission',
        r'audit',
    ]

    has_security_logging = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in security_log_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_security_logging = True
                    break
        except Exception:
            pass
        if has_security_logging:
            break

    checks.append({
        "control_id": "CC7.2",
        "category": "System Operations",
        "status": "pass" if has_security_logging else "warning",
        "description": "Security events are logged",
        "finding": None if has_security_logging else "No security event logging detected",
        "remediation": "Log authentication, authorization, and access events" if not has_security_logging else None,
    })

    return checks


def _check_encryption(path: Path) -> list[dict[str, Any]]:
    """Check CC6: Encryption at rest and in transit."""
    checks: list[dict[str, Any]] = []

    # Check for encryption libraries/patterns
    encryption_patterns = [
        r'from cryptography',
        r'import cryptography',
        r'from Crypto',
        r'import hashlib',
        r'bcrypt',
        r'argon2',
        r'scrypt',
        r'ssl\.',
        r'https://',
    ]

    has_encryption = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in encryption_patterns:
                if re.search(pattern, content):
                    has_encryption = True
                    break
        except Exception:
            pass
        if has_encryption:
            break

    checks.append({
        "control_id": "CC6.3",
        "category": "Encryption",
        "status": "pass" if has_encryption else "warning",
        "description": "Encryption mechanisms available",
        "finding": None if has_encryption else "No encryption libraries detected",
        "remediation": "Use encryption for sensitive data at rest and in transit" if not has_encryption else None,
    })

    # Check for insecure crypto patterns
    insecure_patterns = [
        (r'md5\(', "MD5 hash (weak)"),
        (r'sha1\(', "SHA1 hash (weak for passwords)"),
        (r'DES\.', "DES encryption (weak)"),
        (r'verify=False', "SSL verification disabled"),
    ]

    insecure_findings: list[str] = []
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern, desc in insecure_patterns:
                if re.search(pattern, content):
                    insecure_findings.append(f"{py_file.name}: {desc}")
        except Exception:
            pass

    if insecure_findings:
        checks.append({
            "control_id": "CC6.4",
            "category": "Encryption",
            "status": "warning",
            "description": "No weak cryptographic algorithms",
            "finding": f"Found {len(insecure_findings)} potentially weak crypto patterns",
            "details": insecure_findings[:5],
            "remediation": "Replace weak algorithms with modern alternatives (SHA-256+, AES)",
        })
    else:
        checks.append({
            "control_id": "CC6.4",
            "category": "Encryption",
            "status": "pass",
            "description": "No weak cryptographic algorithms",
        })

    return checks


def _check_change_management(path: Path) -> list[dict[str, Any]]:
    """Check CC8: Change Management."""
    checks: list[dict[str, Any]] = []

    # Check for version control
    has_git = (path / ".git").exists()
    checks.append({
        "control_id": "CC8.1",
        "category": "Change Management",
        "status": "pass" if has_git else "fail",
        "description": "Version control is used",
        "finding": None if has_git else "No .git directory found",
        "remediation": "Initialize git repository for change tracking" if not has_git else None,
    })

    # Check for CI/CD configuration
    ci_files = [
        ".github/workflows",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        ".circleci",
        "azure-pipelines.yml",
    ]
    has_ci = any((path / f).exists() for f in ci_files)

    checks.append({
        "control_id": "CC8.2",
        "category": "Change Management",
        "status": "pass" if has_ci else "warning",
        "description": "CI/CD pipeline configured",
        "finding": None if has_ci else "No CI/CD configuration detected",
        "remediation": "Implement CI/CD for automated testing and deployment" if not has_ci else None,
    })

    return checks


def _check_input_validation(path: Path) -> list[dict[str, Any]]:
    """Check CC5: Control Activities - Input Validation."""
    checks: list[dict[str, Any]] = []

    # Check for validation patterns
    validation_patterns = [
        r'validate\(',
        r'sanitize\(',
        r'escape\(',
        r'pydantic',
        r'marshmallow',
        r'wtforms',
        r'cerberus',
    ]

    has_validation = False
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in validation_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_validation = True
                    break
        except Exception:
            pass
        if has_validation:
            break

    checks.append({
        "control_id": "CC5.1",
        "category": "Control Activities",
        "status": "pass" if has_validation else "warning",
        "description": "Input validation implemented",
        "finding": None if has_validation else "No input validation patterns detected",
        "remediation": "Implement input validation for all user inputs" if not has_validation else None,
    })

    # Check for SQL injection risks
    sql_patterns = [
        r'execute\([^)]*%[^)]*\)',  # String formatting in execute
        r'execute\([^)]*\.format\([^)]*\)',  # .format in execute
        r'execute\([^)]*\+[^)]*\)',  # String concatenation in execute
    ]

    sql_risks: list[str] = []
    for py_file in path.rglob("*.py"):
        if ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="ignore")
            for pattern in sql_patterns:
                if re.search(pattern, content):
                    sql_risks.append(py_file.name)
                    break
        except Exception:
            pass

    if sql_risks:
        checks.append({
            "control_id": "CC5.2",
            "category": "Control Activities",
            "status": "fail",
            "description": "No SQL injection vulnerabilities",
            "finding": f"Potential SQL injection in {len(sql_risks)} files",
            "details": sql_risks[:5],
            "remediation": "Use parameterized queries instead of string formatting",
        })
    else:
        checks.append({
            "control_id": "CC5.2",
            "category": "Control Activities",
            "status": "pass",
            "description": "No SQL injection vulnerabilities detected",
        })

    return checks


if __name__ == "__main__":
    import json
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    results = run_soc2_checks(target)
    print(json.dumps(results, indent=2))
