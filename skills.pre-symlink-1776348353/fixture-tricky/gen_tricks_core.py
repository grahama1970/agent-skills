"""
Core trick definitions: false tables, classification, malformed tables,
cursed text, and layout traps.

These are pure data dictionaries describing adversarial PDF content patterns.
"""

FALSE_TABLE_TRICKS = {
    "numbered-list": {
        "description": "Numbered list with aligned numbers (triggers table detection)",
        "content": """1.  First item in the list that has some longer text
2.  Second item that continues the pattern
3.  Third item with similar formatting
4.  Fourth item to establish the pattern
5.  Fifth and final item in this sequence""",
    },
    "address-block": {
        "description": "Multi-line address with aligned fields",
        "content": """John Smith
Director of Engineering
Acme Corporation
123 Main Street, Suite 456
San Francisco, CA 94102
United States""",
    },
    "code-block": {
        "description": "Indented code with column-like alignment",
        "content": """def process_data(input_file, output_file):
    data = load_file(input_file)
    result = transform(data)
    save_file(result, output_file)
    return result""",
    },
    "signature-block": {
        "description": "Email/document signature with name/title/contact",
        "content": """Best regards,

Jane Doe
Senior Vice President
jane.doe@company.com
+1 (555) 123-4567""",
    },
    "key-value-pairs": {
        "description": "Key: Value patterns that look tabular",
        "content": """Document ID:     DOC-2024-00142
Author:          John Smith
Created:         January 15, 2024
Modified:        January 23, 2024
Status:          Under Review
Classification:  Internal Use Only""",
    },
    "toc-entries": {
        "description": "Table of contents with dotted leaders",
        "content": """1. Introduction .......................... 1
2. Background ............................ 5
3. Methodology .......................... 12
4. Results .............................. 28
5. Discussion ........................... 45
6. Conclusions .......................... 52
References .............................. 55""",
    },
    "receipt-text": {
        "description": "Receipt-style aligned text",
        "content": """Coffee, Large          $4.50
Bagel w/ Cream Cheese  $3.25
Orange Juice           $2.75
                      ------
Subtotal               $10.50
Tax (8.5%)             $0.89
                      ------
Total                  $11.39""",
    },
    "form-fields": {
        "description": "Form-like text with underlines",
        "content": """Name: _______________________

Date of Birth: _______________

Address: ____________________

City: _________ State: __ ZIP: _____

Phone: (___) ___-____""",
    },
    # === NEW TRICKS FROM REAL-WORLD BUGS (2026-01-23) ===
    "toc-with-pagenums": {
        "description": "TOC entries with page numbers that get detected as section headers",
        "content": """1. Operation Blockbuster.............................................4
2. [Wiper] WhiskeyAlfa.................................................7
2.1 WhiskeyAlfa-One.........................................................................9
2.2 WhiskeyAlfa-Two.......................................................................10
3. [Wiper] WhiskeyBravo........................................... 17
4. Conclusions............................................................. 43""",
    },
}

CLASSIFICATION_TRICKS = {
    "arxiv-manual-hybrid": {
        "description": "Arxiv-style header with Technical Manual body (page count/formulas mix)",
        "preset": "arxiv",
        "content": """SENSITIVE DETECTION TEST DOCUMENT
        
        This document contains an Arxiv-style header but follows the structural
        conventions of a Technical Manual. It is designed to test the 
        multimodal HybridClassifier's ability to resolve ambiguous visual inputs
        using text-based features.
        
        Section 1.1: System Overview (Decimal numbering)
        The system SHALL perform operations within 50ms.
        
        1.   Step one includes detailed instruction 
        2.   Step two continues the manual flow
        """,
        "text_features": {
            "page_count": 25,
            "has_formulas": False,
            "has_tables": True,
            "layout": "single",
            "section_style": "decimal"
        }
    },
    "technical-arxiv-hybrid": {
        "description": "Technical Manual header with Arxiv body (math heavy)",
        "preset": "requirements_spec",
        "content": """REQ-001: The system shall be fast.
        
        Abstract: We present a new mathematical model for fast operations.
        
        Let f(x) = ∫ x² dx. Our methodology uses:
        Σᵢ₌₁ⁿ i = n(n+1)/2
        
        This document has few pages but high formula density.
        """,
        "text_features": {
            "page_count": 5,
            "has_formulas": True,
            "has_tables": False,
            "layout": "double",
            "section_style": "roman"
        }
    }
}

MALFORMED_TABLE_TRICKS = {
    "missing-columns": {
        "description": "Rows with fewer cells than header (Word PDF import bug)",
        "columns": ["ID", "Name", "Department", "Status", "Notes"],
        "rows": [
            ["001", "Alice", "Engineering", "Active", "Team lead"],
            ["002", "Bob", "Marketing"],  # Missing 2 columns
            ["003", "Carol", "Sales", "Active"],  # Missing 1 column
            ["004"],  # Missing 4 columns
            ["005", "Eve", "HR", "Inactive", "On leave"],
        ],
    },
    "ragged-rows": {
        "description": "Completely inconsistent column counts",
        "columns": ["A", "B", "C", "D"],
        "rows": [
            ["1", "2", "3", "4", "5", "6"],  # Too many
            ["1", "2"],  # Too few
            ["1", "2", "3", "4"],  # Just right
            ["1"],  # Way too few
            ["1", "2", "3", "4", "5"],  # One too many
        ],
    },
    "empty-cells-chaos": {
        "description": "Random empty cells breaking structure",
        "columns": ["Col1", "Col2", "Col3", "Col4"],
        "rows": [
            ["", "Data", "", "More"],
            ["", "", "", ""],
            ["Value", "", "Something", ""],
            ["", "", "Only here", ""],
        ],
    },
    "merged-simulation": {
        "description": "Simulated merged cells with repeated values",
        "columns": ["Category", "Item", "Q1", "Q2"],
        "rows": [
            ["Electronics", "Phones", "100", "120"],
            ["", "Tablets", "50", "60"],  # Merged category cell
            ["", "Laptops", "30", "40"],  # Merged category cell
            ["Furniture", "Desks", "20", "25"],
            ["", "Chairs", "40", "45"],  # Merged category cell
        ],
    },
    "numeric-alignment-hell": {
        "description": "Numbers that don't align properly",
        "columns": ["Item", "Quantity", "Price", "Total"],
        "rows": [
            ["Widget A", "5", "$10.00", "$50.00"],
            ["Widget B", "123", "$0.50", "$61.50"],
            ["Gadget", "1", "$1,234.56", "$1,234.56"],
            ["Thing", "10000", "$0.01", "$100.00"],
        ],
    },
    "unicode-in-tables": {
        "description": "Unicode characters breaking table structure",
        "columns": ["Name", "Symbol", "Description"],
        "rows": [
            ["Alpha", "α", "First letter"],
            ["Beta", "β", "Second letter"],
            ["Sigma", "Σ", "Sum notation"],
            ["Infinity", "∞", "Unbounded"],
            ["Arrow", "→", "Direction"],
        ],
    },
    "borderless-nasa": {
        "description": "Borderless table like NASA technical reports - lattice mode misses these",
        "columns": ["Parameter", "Value", "Units", "Tolerance"],
        "rows": [
            ["Thrust", "450,000", "lbf", "±2%"],
            ["Specific Impulse", "452", "sec", "±1%"],
            ["Chamber Pressure", "3,260", "psia", "±3%"],
            ["Mixture Ratio", "6.0", "O/F", "±0.1"],
            ["Flow Rate", "1,035", "lbm/sec", "±2%"],
        ],
        "borderless": True,
    },
    "bibliography-single-column": {
        "description": "Bibliography/reference list that looks like single-column table",
        "columns": ["References"],
        "rows": [
            ["[1] Smith, J. et al. (2023). Machine Learning for PDF Extraction. Nature, 123, 45-67."],
            ["[2] Jones, A. & Brown, B. (2022). Table Detection in Scientific Documents. ICML 2022."],
            ["[3] Williams, C. (2021). Neural Document Understanding. arXiv:2101.12345."],
            ["[4] Davis, M. et al. (2020). Camelot: PDF Table Extraction. JMLR, 21, 1-30."],
            ["[5] Taylor, R. (2019). Deep Learning for Document Analysis. IEEE TPAMI."],
        ],
        "single_column": True,
    },
}

CURSED_TEXT_TRICKS = {
    "ligatures": {
        "description": "Ligature characters that break text extraction",
        "content": """The officefficials were fi nding it diffi cult to handle the affl uent
fi nancial matters effi ciently. The effl orescence of fi nesse in their
offi cial duties was insufficient for the affl icted circumstances.""",
    },
    "math-notation": {
        "description": "Mathematical symbols and notation",
        "content": """Given f(x) = x² + 2x + 1, find f'(x).

The solution is: f'(x) = 2x + 2

For the integral: ∫₀^∞ e^(-x²) dx = √π/2

And the sum: Σᵢ₌₁ⁿ i = n(n+1)/2""",
    },
    "subscript-superscript": {
        "description": "Chemical formulas and footnote markers",
        "content": """Water (H₂O) reacts with carbon dioxide (CO₂) to form
carbonic acid (H₂CO₃)¹. The reaction proceeds as follows²:

H₂O + CO₂ → H₂CO₃

The equilibrium constant Kₐ = 4.3 × 10⁻⁷ at 25°C³.""",
    },
    "lookalike-chars": {
        "description": "Characters that look identical but aren't (homoglyphs)",
        # Mix of Latin, Cyrillic, and Greek lookalikes
        "content": """Compare these seemingly identical words:
- apple vs аpple (Cyrillic 'а')
- hello vs hеllo (Cyrillic 'е')
- office vs оffice (Cyrillic 'о')
- Example vs Ехample (Cyrillic 'Е' and 'х')""",
    },
    "invisible-chars": {
        "description": "Zero-width and invisible characters",
        "content": """This sentence has a zero\u200bwidth space in it.
This one has a soft\u00adhyphen that may or may not show.
And this has a word\u2060joiner between words.
Finally, a non\u00a0breaking space here.""",
    },
    "mixed-numbers": {
        "description": "Different number representations",
        "content": """Numbers in various forms:
- Arabic: 0 1 2 3 4 5 6 7 8 9
- Roman: I II III IV V VI VII VIII IX X
- Superscript: ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹
- Circled: ① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩""",
    },
    # === NEW TRICKS FROM BATCH HARDENING (2026-02-04) ===
    "symbol-fonts": {
        "description": "PUA chars from Microsoft Symbol/Wingdings fonts (U+F000-F0FF)",
        "content": """\uf0b7 First bullet point using Symbol font bullet
\uf0b7 Second bullet with same Symbol encoding
\uf0d8 Arrow-style bullet from Wingdings
\uf0fc Checkmark item from Wingdings
\uf0a7 Section marker from Symbol font
\uf0aa Up-arrow reference mark

Normal text between PUA characters.

\uf0b7 Mixed content with \uf0fc checkmarks and \uf0d8 arrows inline.
Some \uf020 space \uf021 exclamation \uf022 quote characters too.""",
    },
    "math-heavy": {
        "description": "Dense mathematical content that loses symbols during extraction",
        "content": """Theorem 3.1: For all x ∈ ℝ, if f: ℝ → ℝ is continuous on [a,b], then:

∫ₐᵇ f(x)dx = F(b) - F(a)

where F'(x) = f(x). The Cauchy-Schwarz inequality states:

|⟨u,v⟩|² ≤ ⟨u,u⟩ · ⟨v,v⟩

For matrices A ∈ ℝⁿˣⁿ, the spectral norm satisfies:
‖A‖₂ = σ_max(A) = √(λ_max(AᵀA))

Proof follows from ∀ε > 0, ∃δ > 0 s.t. |x - x₀| < δ ⟹ |f(x) - f(x₀)| < ε.""",
    },
}

LAYOUT_TRAP_TRICKS = {
    "deep-nesting": {
        "description": "Deeply nested section hierarchy (10+ levels)",
        "sections": [
            ("1. Introduction", 1),
            ("1.1 Background", 2),
            ("1.1.1 Historical Context", 3),
            ("1.1.1.1 Early Development", 4),
            ("1.1.1.1.1 Initial Research", 5),
            ("1.1.1.1.1.1 First Experiments", 6),
            ("1.1.1.1.1.1.1 Preliminary Results", 7),
            ("1.1.1.1.1.1.1.1 Data Analysis", 8),
            ("1.1.1.1.1.1.1.1.1 Statistical Methods", 9),
            ("1.1.1.1.1.1.1.1.1.1 Regression Analysis", 10),
        ],
    },
    "footnote-sections": {
        "description": "Footnotes that look like new sections",
        "content": """Main content paragraph discussing important topics.

¹ This is a footnote that spans multiple lines and looks very much
like it could be a new section with its own content that continues
for quite a while.

² Another footnote that might confuse section detection because it
starts with a number and has substantial content below it.

1. Actual Section One

This is the real content of section one.""",
    },
    "sidebar-content": {
        "description": "Marginal notes alongside main text",
        "main_text": "This is the primary content that flows down the page in the main column area.",
        "sidebar_text": "SIDEBAR: Additional context that appears in the margin.",
    },
    "out-of-order": {
        "description": "Content in non-reading order (like some PDFs)",
        "blocks": [
            {"text": "Third paragraph", "order": 3},
            {"text": "First paragraph", "order": 1},
            {"text": "Second paragraph", "order": 2},
        ],
    },
    # === NEW TRICKS FROM REAL-WORLD BUGS (2026-01-23) ===
    "page-number-sections": {
        "description": "Standalone page numbers/footnote refs mistaken for section headers",
        "content": """1

This is regular paragraph text on page 1.

2

More paragraph text on page 2 that should not be sectioned.

5

A footnote reference⁵ that might confuse section detection.

7

Page 7 content continues here with normal text flow.""",
    },
    "partial-header": {
        "description": "Incomplete headers like 'Table of' without 'Contents'",
        "content": """Table of

This text should be part of the 'Table of Contents' section but
the header was truncated during extraction.

Executive

Summary text that got separated from its header due to
formatting issues in the source PDF.""",
    },
    "sentence-as-header": {
        "description": "Partial sentences detected as section headers",
        "content": """// This section gives a brief overview of the technical

architecture and implementation details that follow in
subsequent sections of this document.

3.  The heap memory buffer is zeroed out and written over the entirety of the selected file starting at byte 0

which is a common technique used in secure deletion.""",
    },
    # === NEW TRICK FROM ROUND 2 TESTING (2026-01-23) ===
    "allcaps-header-missed": {
        "description": "ALL-CAPS headers not detected while numbered list items are (false positive)",
        "content": """Legal Over-the-Air Spoofing of GPS
and the Resulting Effects on Autonomous Vehicles

INTRODUCTION/BACKGROUND

Many systems rely on an accurate global positioning system (GPS) signal for
normal operation. GPS is vulnerable to external interference. The spoofing
attack was performed:

1. inside a fully enclosed Faraday cage
2. under an experimental license from the FCC
3. with proper safety precautions

A user can insert an offset in any direction and by any distance desired.

METHODOLOGY

The test setup consisted of the following components...""",
    },
    "numbered-sections-as-text": {
        "description": "Numbered sections that Marker classifies as plain Text (not headers)",
        "content": """SATELLITE HACKING:
A Guide for the Perplexed

By Jason Fritz

1. Introduction: Three Key Questions

Satellites are vital to sustaining the current global infrastructure.
This section examines the fundamental questions surrounding satellite security.

2. Background: Historical Context

The development of satellite technology began in the 1950s with Sputnik.

2.1 Early Satellite Programs

The United States and Soviet Union competed to establish space dominance.

3. Current Vulnerabilities

Modern satellites face numerous cyber threats including jamming and spoofing.

4. Conclusions

Satellite security requires continuous vigilance and updated protocols.""",
    },
    # === NEW TRICKS FROM BATCH HARDENING (2026-02-04) ===
    "toc-leaders-captured": {
        "description": "TOC dotted leaders captured in section headers by S04",
        "content": """Table of Contents

1. Introduction .......................... 1
   1.1 Background ....................... 3
   1.2 Scope ............................ 5
2. System Requirements .................. 8
   2.1 Functional Requirements ......... 10
   2.2 Non-Functional Requirements ..... 15
3. Architecture ......................... 20
   3.1 High-Level Design ............... 22
   3.2 Component Interfaces ............ 28
Appendix A .............................. 35
Appendix B .............................. 42

1. Introduction

This document describes the system requirements and architecture.""",
    },
    "requirements-doc": {
        "description": "Engineering doc with SHALL/MUST requirements that S08 must find",
        "content": """3.1 System Requirements

REQ-001: The system shall provide real-time telemetry data to ground stations.

REQ-002: The system shall maintain a minimum uptime of 99.97%.

REQ-003: All communication links must use AES-256 encryption.

3.2 Performance Requirements

REQ-004: The system shall process incoming data within 50 milliseconds.

REQ-005: The system must support concurrent connections from up to 100 clients.

REQ-006: Response time should not exceed 200ms under peak load conditions.

3.3 Safety Requirements

REQ-007: The system shall implement fail-safe mode when telemetry is lost.

REQ-008: All safety-critical functions must have redundant backup systems.""",
    },
    "section-merge-cascade": {
        "description": "Many short sections that cascade-merge when content measured from wrong field",
        "content": """1. Overview

Brief intro.

2. Scope

Short scope.

3. Definitions

Terms here.

4. References

See docs.

5. System Description

Brief.

6. Interfaces

API list.

7. Data Requirements

Schema.

8. Security

Access control.

9. Verification

Test plan.

10. Appendices

See attached.""",
    },
    # === NEW TRICKS FROM S00 FONT ESTIMATION WORK (2026-02-04) ===
    "code-heavy-font-skew": {
        "description": "Document with 7pt code listings dominating font size distribution, body text at 10pt",
        "content": """1. Introduction

This document contains extensive code examples that skew font metrics.

The body text is at 10pt while code blocks use 7pt monospace.

    def process_data(input: str) -> dict:
        result = {}
        for line in input.split('\\n'):
            key, val = line.split('=')
            result[key.strip()] = val.strip()
        return result

    class DataProcessor:
        def __init__(self, config):
            self.config = config
            self.cache = {}

        def run(self, data):
            processed = self.process_data(data)
            self.cache.update(processed)
            return processed

2. Architecture

The system architecture follows a pipeline pattern.

    pipeline = Pipeline([
        Stage('extract', extract_fn),
        Stage('transform', transform_fn),
        Stage('load', load_fn),
    ])
    pipeline.execute(input_data)

3. Testing

Unit tests cover all major components.""",
    },
    "front-matter-heavy": {
        "description": "Document with extensive front matter (title, TOC, lists) before real content",
        "content": """TECHNICAL SPECIFICATION DOCUMENT

Version 2.1 | Classification: Public

Prepared by: Engineering Division
Reviewed by: Quality Assurance
Approved by: Program Manager

Date: 2026-01-15

REVISION HISTORY

Rev 1.0 - Initial Release
Rev 1.1 - Minor corrections
Rev 2.0 - Major update
Rev 2.1 - Current release

TABLE OF CONTENTS

1. Introduction .................. 3
2. Scope ........................ 4
3. Requirements ................. 5
  3.1 Functional ................ 5
  3.2 Performance ............... 8
  3.3 Interface ................. 10
4. Design ....................... 12
5. Verification ................. 15
Appendix A ...................... 18
Appendix B ...................... 20

LIST OF FIGURES

Figure 1 - System Overview
Figure 2 - Architecture Diagram
Figure 3 - Data Flow

LIST OF TABLES

Table 1 - Requirements Matrix
Table 2 - Test Coverage""",
    },
    "boundary-heading-sizes": {
        "description": "Headings at exactly 1.2x body font size (boundary detection case)",
        "content": """1. Overview

This section provides a high-level description. The body text is at standard
size while headings are at precisely 1.2 times the body font size, which is
a common ratio in academic and engineering documents.

2. Background

Previous work established the baseline metrics for performance evaluation
across multiple document types and extraction scenarios.

3. Methodology

The approach uses a three-phase pipeline to progressively refine extraction
quality through iterative validation passes.

4. Results

Measurements show significant improvement in section detection accuracy
when font-based estimation is combined with regex pattern matching.

5. Discussion

The combined approach addresses the fundamental limitation of single-signal
section estimation methods used in prior implementations.""",
    },
}

