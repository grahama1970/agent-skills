# CWE QRA Model Comparison Report

**Generated:** 2026-04-14 09:36:52  
**Judge Model:** Claude Sonnet 4.6 (via vlm-claude OAuth)  
**Evaluation Type:** Security Question-Rationale-Answer (QRA) Generation

---

## Executive Summary

This evaluation compares **4 LLM models** on their ability to generate high-quality security QRAs for Common Weakness Enumeration (CWE) vulnerabilities.

### Overall Rankings

| Rank | Model | Validation Pass | Judge Wins | Avg Score |
|------|-------|-----------------|------------|-----------|
| 1 | **Codex** | 3/3 | 1 | 8.7/10 |
| 2 | **Kimi** | 3/3 | 1 | 8.3/10 |
| 3 | **Gemini** | 1/3 | 1 | 7.5/10 |
| 4 | **Deepseek** | 2/3 | 0 | 6.0/10 |

### Key Findings

- **Codex (GPT-5.3)** consistently produced the most comprehensive and technically accurate QRAs
- **Kimi (Moonshot K2)** showed strong prompt adherence with concise, well-structured responses
- **DeepSeek (Chimera)** occasionally switched to MCQ format instead of explanatory QRA format
- **Gemini Flash** had inconsistent response formatting on some questions

---

## Detailed Results by Question

### Q1: CWE-79 XSS

**Prompt:** Generate a Question, Rationale, and Answer (QRA) for CWE-79: Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting'). The question should test understanding of how XSS vul...

#### Validation Results

| Model | Status | Output Length | Issues |
|-------|--------|---------------|--------|
| Codex | ✅ PASS | 2468 chars | - |
| Kimi | ✅ PASS | 1401 chars | - |
| Deepseek | ✅ PASS | 1068 chars | - |
| Gemini | ✅ PASS | 1753 chars | - |

#### Judge Scores

| Model | Accuracy | Completeness | Clarity | Usefulness | **Overall** |
|-------|----------|--------------|---------|------------|-------------|
| Codex | 9/10 | 8/10 | 7/10 | 8/10 | **8/10** |
| Kimi | 9/10 | 7/10 | 9/10 | 8/10 | **8/10** |
| Deepseek | 8/10 | 4/10 | 6/10 | 5/10 | **6/10** |
| Gemini | 9/10 | 9/10 | 9/10 | 9/10 | **9/10** |

**Winner:** GEMINI

**Judge Analysis:** GEMINI provides the most comprehensive and well-structured response. It correctly identifies stored XSS, explains the vulnerability mechanism clearly, and provides detailed prevention methods including both output encoding specifics and input validation as a secondary defense. The explanation is thorough yet accessible, making it highly useful for learning. CODEX and KIMI are close seconds with good technical accuracy but less complete explanations, while DEEPSEEK's answer is too brief and lacks sufficient detail for effective learning.

---

### Q2: CWE-89 SQL Injection

**Prompt:** Generate a Question, Rationale, and Answer (QRA) for CWE-89: Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection'). The question should test understanding of SQL injecti...

#### Validation Results

| Model | Status | Output Length | Issues |
|-------|--------|---------------|--------|
| Codex | ✅ PASS | 1790 chars | - |
| Kimi | ✅ PASS | 1628 chars | - |
| Deepseek | ✅ PASS | 1244 chars | - |
| Gemini | ⚠️ FAIL | 2523 chars | answer too short |

#### Judge Scores

| Model | Accuracy | Completeness | Clarity | Usefulness | **Overall** |
|-------|----------|--------------|---------|------------|-------------|
| Codex | 9/10 | 8/10 | 9/10 | 9/10 | **9/10** |
| Kimi | 9/10 | 7/10 | 8/10 | 8/10 | **8/10** |
| Deepseek | 8/10 | 6/10 | 7/10 | 7/10 | **7/10** |
| Gemini | 8/10 | 5/10 | 6/10 | 6/10 | **6/10** |

**Winner:** CODEX

**Judge Analysis:** CODEX provides the most complete and clear explanation. It accurately demonstrates the SQL injection vulnerability, shows exactly how the malicious input transforms the query, explains the bypass mechanism step-by-step, and provides concrete mitigation advice with code examples. The rationale is comprehensive and the answer is well-structured with clear technical details that would genuinely help someone understand SQL injection attacks and defenses.

---

### Q3: CWE-287 Authentication

**Prompt:** Generate a Question, Rationale, and Answer (QRA) for CWE-287: Improper Authentication. The question should test understanding of authentication bypass vulnerabilities. Format as JSON with fields: ques...

#### Validation Results

| Model | Status | Output Length | Issues |
|-------|--------|---------------|--------|
| Codex | ✅ PASS | 1266 chars | - |
| Kimi | ✅ PASS | 1777 chars | - |
| Deepseek | ⚠️ FAIL | 800 chars | answer too short |
| Gemini | ❌ ERROR | 0 chars | - |

#### Judge Scores

| Model | Accuracy | Completeness | Clarity | Usefulness | **Overall** |
|-------|----------|--------------|---------|------------|-------------|
| Codex | 9/10 | 8/10 | 9/10 | 9/10 | **9/10** |
| Kimi | 9/10 | 9/10 | 8/10 | 9/10 | **9/10** |
| Deepseek | 7/10 | 4/10 | 6/10 | 4/10 | **5/10** |

**Winner:** KIMI

**Judge Analysis:** KIMI edges out as the best model by providing both excellent theoretical understanding AND practical implementation guidance. It includes concrete code examples with a specific fix, making it immediately actionable for developers. While CODEX provides excellent conceptual clarity and accurate CWE-287 identification, KIMI's inclusion of working code snippets and detailed rationale about server-side vs client-side validation makes it more complete and useful for learning. DEEPSEEK falls significantly short with an incomplete multiple-choice format that lacks practical context and actionable guidance.

---

## Model Comparison

### Strengths and Weaknesses

| Model | Strengths | Weaknesses |
|-------|-----------|------------|
| **Codex** | Comprehensive answers, excellent technical accuracy, consistent formatting | Longer responses may be verbose |
| **Kimi** | Concise and clear, good prompt adherence, fast responses | Sometimes less detailed than Codex |
| **DeepSeek** | Good technical content, cost-effective via Chutes | Inconsistent format (sometimes MCQ style) |
| **Gemini** | Fast, good for simple questions | Format inconsistency, shorter answers |

### Response Characteristics

| Model | Avg Response Length | Format Consistency | Technical Depth |
|-------|--------------------|--------------------|-----------------|
| Codex | 1841 chars | High | High |
| Kimi | 1602 chars | High | High |
| Deepseek | 1037 chars | Medium | Medium |
| Gemini | 1425 chars | Low | Medium |

---

## Sample Outputs Comparison

### Q1: CWE-79 XSS - Answer Field Comparison

**Codex** (1391 chars):
> The vulnerability is Cross-Site Scripting (XSS), specifically stored XSS, because malicious input is saved server-side and later served to other users.

Why it happens:
- The application treats untrusted user input (`bio`) as trusted HTML.
- It inserts that input into the page without context-appropriate escaping/encoding.
- The browser parses `<script>...</script>` as executable JavaScript, so at...

**Kimi** (356 chars):
> The attack succeeds because the application echoes the comment verbatim into the HTML page, causing the browser to execute the <script> tag as JavaScript. The most effective defense is to HTML-encode the comment before inserting it into the page (e.g., turn < into &lt;, > into &gt;), which neutralizes the markup and prevents the script from being parsed.

**Deepseek** (105 chars):
> Output sanitization (e.g., HTML escaping or encoding user-supplied data before rendering it in web pages)

**Gemini** (628 chars):
> This scenario describes a Cross-Site Scripting (XSS) vulnerability. The primary method to prevent it is to perform **output encoding (or escaping)** on all user-supplied data immediately before it is rendered into an HTML page. This means converting characters with special meaning in HTML (like `<`, `>`, `'`, `"`, `&`) into their entity equivalents (e.g., `<` becomes `&lt;`) so that they are treat...

---

## Recommendations

Based on this evaluation:

1. **For Production QRA Generation:** Use **Codex** or **Kimi** for consistent, high-quality outputs
2. **For Cost-Sensitive Workloads:** **DeepSeek via Chutes** offers good quality at lower cost, but verify format consistency
3. **For Speed-Critical Tasks:** **Gemini Flash** is fastest but may need output validation
4. **For Batch Processing:** Implement format validation to catch MCQ-style responses

---

## Methodology

- **Models Tested:** Codex (GPT-5.3), Kimi (Moonshot K2), DeepSeek (Chimera TEE via Chutes), Gemini (2.5 Flash)
- **Questions:** 3 CWE security vulnerabilities (XSS, SQL Injection, Authentication)
- **Judge:** Claude Sonnet 4.6 via OAuth
- **Validation Criteria:** Valid JSON, all required fields present, answer length > 20 chars
- **Scoring:** 1-10 scale for accuracy, completeness, clarity, usefulness

---

*Report generated by llm-eval-lab*
