"""Three-Tier Cascade integration for /hack skill.

Provides cascade validation of security findings and RepoAudit-style
parallel GPT analysis (swarm mode).

Tiers:
    T0: Rule-based CWE pattern matching + dedup
    T1.5: GPT swarm classifiers (vuln, severity, exploitability)
    T2: Brandon teacher validation for low-confidence findings
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

# Add skills directory to path for common imports
SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.cascade import CascadeRunner, TierResult, TierDef
    HAS_CASCADE = True
except ImportError:
    HAS_CASCADE = False
    logger.warning("common.cascade not available; cascade validation disabled")

# Paths
SKILL_DIR = Path(__file__).parent
ASSISTANT_SKILL = SKILLS_DIR / "assistant"
SCILLM_SKILL = SKILLS_DIR / "scillm"
TREESITTER_SKILL = SKILLS_DIR / "treesitter"

# Configuration
SWARM_MAX_WORKERS = int(os.getenv("HACK_SWARM_WORKERS", "10"))
SWARM_TIMEOUT = int(os.getenv("HACK_SWARM_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FunctionSite:
    """A source site found by tree-sitter seeding."""
    file_path: str
    function_name: str
    start_line: int
    end_line: int
    source: str = ""
    sink_type: str = ""  # "subprocess", "eval", "import", "open"


@dataclass
class SwarmFinding:
    """Finding from swarm analysis."""
    file_path: str
    function_name: str
    vulnerability_type: str
    severity: str = "medium"
    confidence: float = 0.0
    description: str = ""
    cwe_id: str = ""
    validated: bool = False
    tier_source: str = ""


# ---------------------------------------------------------------------------
# Known CWE patterns for Tier 0
# ---------------------------------------------------------------------------

_CWE_PATTERNS: dict[str, re.Pattern] = {
    "CWE-78": re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True"),
    "CWE-95": re.compile(r"\b(eval|exec)\s*\("),
    "CWE-798": re.compile(r'(?i)(api_key|password|secret)\s*[=:]\s*["\x27]\w{8,}'),
    "CWE-400": re.compile(r"subprocess\.run\((?!.*timeout)"),
    "CWE-502": re.compile(r"pickle\.loads?\(|yaml\.load\((?!.*Loader)"),
    "CWE-77": re.compile(r"os\.system\("),
}

_SEEN_HASHES: set[str] = set()


def _finding_hash(finding: dict) -> str:
    """Compute dedup hash from file+line+type."""
    key = f"{finding.get('file_path', '')}:{finding.get('line_number', '')}:{finding.get('vulnerability_type', '')}"
    return hashlib.md5(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Tier 0: Rule-based CWE check + dedup
# ---------------------------------------------------------------------------

def tier0_rule_check(finding: Any, **kw) -> TierResult | None:
    """Known CWE pattern matching, dedup by file+line."""
    if not HAS_CASCADE:
        return None

    if isinstance(finding, dict):
        desc = finding.get("description", "")
        fpath = finding.get("file_path", "")
    else:
        desc = str(finding)
        fpath = ""

    # Dedup
    fhash = _finding_hash(finding if isinstance(finding, dict) else {"description": desc})
    if fhash in _SEEN_HASHES:
        return TierResult(
            result={"verdict": "duplicate", "hash": fhash},
            confidence=1.0,
            source="rule_dedup",
            prediction="false_positive",
        )
    _SEEN_HASHES.add(fhash)

    # CWE pattern matching
    for cwe_id, pattern in _CWE_PATTERNS.items():
        if pattern.search(desc):
            return TierResult(
                result={"cwe_id": cwe_id, "verdict": "true_positive"},
                confidence=0.95,
                source="cwe_rule",
                prediction="true_positive",
            )

    # No rule matched — escalate
    return TierResult(
        result={"verdict": "unknown"},
        confidence=0.3,
        source="rule_check",
        prediction="needs_review",
    )


# ---------------------------------------------------------------------------
# Tier 1.5: GPT swarm classifiers
# ---------------------------------------------------------------------------

def tier15_gpt_swarm(finding: Any, **kw) -> TierResult | None:
    """Route to vuln-classifier, severity-classifier, exploitability-classifier
    via /assistant. Run in parallel on local H200s."""
    if not HAS_CASCADE:
        return None

    assistant_script = ASSISTANT_SKILL / "run.sh"
    if not assistant_script.exists():
        return None

    desc = finding.get("description", str(finding)) if isinstance(finding, dict) else str(finding)

    classifiers = ["vuln-classifier", "severity-classifier", "exploitability-classifier"]
    results = {}

    def _classify(task_name: str) -> tuple[str, dict]:
        try:
            result = subprocess.run(
                [str(assistant_script), "classify",
                 "--text", desc[:2000],
                 "--task", task_name, "--json"],
                capture_output=True, text=True, timeout=SWARM_TIMEOUT,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0 and result.stdout:
                return task_name, json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass
        return task_name, {}

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_classify, c): c for c in classifiers}
        for future in as_completed(futures, timeout=SWARM_TIMEOUT + 10):
            try:
                name, data = future.result()
                results[name] = data
            except Exception:
                continue

    # Compute aggregate confidence
    vuln = results.get("vuln-classifier", {})
    severity = results.get("severity-classifier", {})
    exploit = results.get("exploitability-classifier", {})

    vuln_conf = vuln.get("confidence", 0.0)
    verdict = vuln.get("prediction", "needs_review")

    avg_conf = sum(
        r.get("confidence", 0.0) for r in results.values()
    ) / max(len(results), 1)

    return TierResult(
        result={
            "vuln": vuln,
            "severity": severity,
            "exploitability": exploit,
        },
        confidence=avg_conf,
        source="gpt_swarm",
        prediction=verdict,
        probabilities={"true_positive": vuln_conf, "false_positive": 1 - vuln_conf},
    )


# ---------------------------------------------------------------------------
# Tier 2: Brandon teacher validation
# ---------------------------------------------------------------------------

def tier2_brandon_validate(finding: Any, **kw) -> TierResult | None:
    """scillm teacher for low-confidence findings. Labels stored for training."""
    if not HAS_CASCADE:
        return None

    scillm_script = SCILLM_SKILL / "run.sh"
    if not scillm_script.exists():
        return None

    desc = finding.get("description", str(finding)) if isinstance(finding, dict) else str(finding)

    prompt = (
        "You are Brandon Bailey, a senior security researcher. Analyze this security finding "
        "and determine if it is a true positive or false positive. Respond with JSON: "
        '{"verdict": "true_positive"|"false_positive", "confidence": 0.0-1.0, '
        '"reasoning": "...", "severity": "critical|high|medium|low"}\n\n'
        f"Finding:\n{desc[:3000]}"
    )

    try:
        result = subprocess.run(
            [str(scillm_script), "complete", "--prompt", prompt, "--json"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            verdict = data.get("verdict", "needs_review")
            confidence = float(data.get("confidence", 0.8))

            # Store label for training
            _store_training_label(finding, data)

            return TierResult(
                result=data,
                confidence=confidence,
                source="brandon_teacher",
                prediction=verdict,
            )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.debug("Brandon validation failed: {}", e)

    return None


def _store_training_label(finding: Any, judgment: dict) -> None:
    """Append Brandon's judgment to training_labels.jsonl."""
    labels_file = Path.home() / ".pi" / "monitor-security" / "training_labels.jsonl"
    labels_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        import time
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "finding": finding if isinstance(finding, dict) else {"description": str(finding)},
            "judgment": judgment,
        }
        with open(labels_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# CascadeRunner construction
# ---------------------------------------------------------------------------

def build_security_cascade() -> CascadeRunner | None:
    """Construct cascade: T0 rule-check -> T1.5 GPT swarm -> T2 Brandon."""
    if not HAS_CASCADE:
        return None

    shadow_file = Path.home() / ".pi" / "monitor-security" / "shadow.jsonl"
    metrics_file = Path.home() / ".pi" / "monitor-security" / "metrics.jsonl"

    return CascadeRunner(
        tiers=[
            TierDef(tier=0, name="rule_check", fn=tier0_rule_check, threshold=0.8),
            TierDef(tier=1.5, name="gpt_swarm", fn=tier15_gpt_swarm,
                    threshold=0.8, shadow_mode=True),
            TierDef(tier=2, name="brandon", fn=tier2_brandon_validate,
                    is_teacher=True),
        ],
        shadow_file=shadow_file,
        metrics_file=metrics_file,
    )


def _route_finding_scope(finding: dict) -> str:
    """Select persona scope for a security finding via bridge routing."""
    try:
        from common.persona_router import route_personas_for_task

        matches = route_personas_for_task(
            "vulnerability_triage", finding, top_k=1,
        )
        if matches:
            return matches[0].scope
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return "security"


def cascade_validate_findings(
    findings: list[dict],
    persona_routing: bool = False,
) -> list[dict]:
    """Bulk validation: pipe all findings through cascade.

    Args:
        findings: List of finding dicts with at least 'description'.
        persona_routing: If True, auto-select persona scope per finding.
    """
    cascade = build_security_cascade()
    if cascade is None:
        logger.warning("Cascade not available, returning findings unvalidated")
        return findings

    validated = []
    for finding in findings:
        desc = finding.get("description", str(finding))
        input_hash = hashlib.md5(desc[:500].encode()).hexdigest()

        scope = "security"
        if persona_routing:
            scope = _route_finding_scope(finding)

        result = cascade.run(
            input_data=finding,
            task="vulnerability_triage",
            scope=scope,
            input_hash=input_hash,
        )

        finding["cascade_verdict"] = result.prediction
        finding["cascade_confidence"] = result.confidence
        finding["cascade_tier"] = result.tier
        finding["cascade_source"] = result.source
        finding["cascade_scope"] = scope
        validated.append(finding)

    return validated


# ---------------------------------------------------------------------------
# RepoAudit-style swarm analysis
# ---------------------------------------------------------------------------

def treesitter_seed(file_path: str) -> list[FunctionSite]:
    """Find source sites: subprocess, eval, import, open calls using treesitter."""
    sites: list[FunctionSite] = []

    treesitter_script = TREESITTER_SKILL / "run.sh"
    if not treesitter_script.exists():
        # Fallback: simple regex-based seeding
        return _regex_seed(file_path)

    try:
        result = subprocess.run(
            [str(treesitter_script), "symbols", file_path, "--json"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout:
            symbols = json.loads(result.stdout)
            for sym in symbols.get("functions", []):
                source = sym.get("source", "")
                sink_type = ""
                for sink in ("subprocess", "eval", "exec", "import", "open", "os.system"):
                    if sink in source:
                        sink_type = sink
                        break
                if sink_type:
                    sites.append(FunctionSite(
                        file_path=file_path,
                        function_name=sym.get("name", ""),
                        start_line=sym.get("start_line", 0),
                        end_line=sym.get("end_line", 0),
                        source=source,
                        sink_type=sink_type,
                    ))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return _regex_seed(file_path)

    return sites


def _regex_seed(file_path: str) -> list[FunctionSite]:
    """Fallback: regex-based function seeding."""
    sites = []
    sink_patterns = {
        "subprocess": re.compile(r"subprocess\.\w+\("),
        "eval": re.compile(r"\beval\s*\("),
        "exec": re.compile(r"\bexec\s*\("),
        "os.system": re.compile(r"os\.system\("),
        "open": re.compile(r"\bopen\s*\("),
    }

    try:
        text = Path(file_path).read_text(errors="ignore")
        lines = text.splitlines()
        current_func = "module_level"
        func_start = 1

        for i, line in enumerate(lines, 1):
            # Track function definitions
            func_match = re.match(r"^(async\s+)?def\s+(\w+)", line)
            if func_match:
                current_func = func_match.group(2)
                func_start = i

            for sink_name, pattern in sink_patterns.items():
                if pattern.search(line):
                    sites.append(FunctionSite(
                        file_path=file_path,
                        function_name=current_func,
                        start_line=func_start,
                        end_line=i,
                        source=line.strip()[:200],
                        sink_type=sink_name,
                    ))
    except OSError:
        pass

    return sites


def hallucination_validator(finding: SwarmFinding) -> bool:
    """Verify claimed data-flow facts against file structure.

    Checks that the reported file and function actually exist and contain
    the claimed vulnerability pattern.
    """
    try:
        path = Path(finding.file_path)
        if not path.exists():
            return False

        text = path.read_text(errors="ignore")

        # Check function exists
        if finding.function_name and finding.function_name != "module_level":
            if f"def {finding.function_name}" not in text:
                return False

        # Check vulnerability type pattern exists
        vuln_patterns = {
            "command_injection": re.compile(r"subprocess|os\.system|os\.popen"),
            "eval_injection": re.compile(r"\beval\s*\(|\bexec\s*\("),
            "path_traversal": re.compile(r"open\s*\(.*\+"),
            "sql_injection": re.compile(r"execute\s*\(.*%|execute\s*\(.*\+"),
            "deserialization": re.compile(r"pickle\.loads?|yaml\.load"),
        }

        pattern = vuln_patterns.get(finding.vulnerability_type)
        if pattern and not pattern.search(text):
            return False

        return True

    except OSError:
        return False


def swarm_analyze(targets: list[str], max_workers: int | None = None) -> list[SwarmFinding]:
    """RepoAudit-style: tree-sitter seeds -> parallel GPT analysis per function.

    Each worker gets ONE function. Hallucination validator checks results.
    """
    if max_workers is None:
        max_workers = SWARM_MAX_WORKERS

    # Phase 1: Seed source sites
    all_sites: list[FunctionSite] = []
    for target in targets:
        target_path = Path(target)
        if target_path.is_file():
            all_sites.extend(treesitter_seed(str(target_path)))
        elif target_path.is_dir():
            for py_file in target_path.rglob("*.py"):
                if ".venv" in str(py_file) or "node_modules" in str(py_file):
                    continue
                all_sites.extend(treesitter_seed(str(py_file)))

    logger.info("Swarm: found {} source sites across {} targets", len(all_sites), len(targets))

    if not all_sites:
        return []

    # Phase 2: Parallel GPT analysis
    findings: list[SwarmFinding] = []

    def _analyze_site(site: FunctionSite) -> SwarmFinding | None:
        """Analyze a single function site via /assistant."""
        assistant_script = ASSISTANT_SKILL / "run.sh"
        if not assistant_script.exists():
            return None

        try:
            result = subprocess.run(
                [str(assistant_script), "validate",
                 "--text", json.dumps({
                     "function_source": site.source[:2000],
                     "vulnerability_type": site.sink_type,
                     "file_path": site.file_path,
                     "function_name": site.function_name,
                 }),
                 "--task", "vuln-gpt-analyzer", "--json"],
                capture_output=True, text=True, timeout=SWARM_TIMEOUT,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return SwarmFinding(
                    file_path=site.file_path,
                    function_name=site.function_name,
                    vulnerability_type=data.get("vulnerability_type", site.sink_type),
                    severity=data.get("severity", "medium"),
                    confidence=float(data.get("confidence", 0.5)),
                    description=data.get("description", ""),
                    cwe_id=data.get("cwe_id", ""),
                    tier_source="gpt_swarm",
                )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_analyze_site, site): site for site in all_sites}
        for future in as_completed(futures, timeout=SWARM_TIMEOUT * 2):
            try:
                result = future.result()
                if result is not None:
                    # Hallucination check
                    if hallucination_validator(result):
                        result.validated = True
                        findings.append(result)
                    else:
                        logger.debug("Hallucination rejected: {} in {}",
                                     result.vulnerability_type, result.file_path)
            except Exception:
                continue

    logger.info("Swarm: {} validated findings from {} sites", len(findings), len(all_sites))
    return findings
