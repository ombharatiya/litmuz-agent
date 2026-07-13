"""AC-SAFETY-3 merge-blocking gate: no safety-critical claim can auto-pass.

Each safety claim is scored in the strongest possible pass posture (supported, confidence
1.0, clean citation, active source, full text). The gate asserts the count of auto-passed
safety-critical claims is exactly zero, with a non-vacuous corpus precondition and an
independent lexical re-derivation, and that the gate is not vacuously blocking everything.
"""

from litmuz_core.config import (
    Category,
    Config,
    IdType,
    JudgeLabel,
    ResolutionStatus,
    RetrievalMode,
    SourceStatus,
)
from litmuz_core.safety import is_safety_critical_text
from litmuz_core.schemas import CitationCheck
from litmuz_core.severity.mapping import score_claim

DOSING = [
    "The recommended dose was 5 mg daily.",
    "Patients received 10 mg/kg twice daily.",
    "Administered at a dosage of 200 mg.",
    "Titrated to 50 mg per day.",
    "A single 1 g infusion was given.",
    "Maintenance dosing of 25 mg twice daily.",
]
TARGET = [
    "Osimertinib targets EGFR T790M.",
    "It is a selective EGFR inhibitor.",
    "The antagonist of the receptor reduced signalling.",
    "The compound is an inhibitor of BRAF.",
    "An agonist of the GLP-1 receptor improved outcomes.",
    "The drug targets the KRAS G12C mutation.",
]
INDICATION = [
    "Indicated for metastatic melanoma.",
    "First-line therapy for NSCLC.",
    "Approved for the treatment of hypertension.",
    "For the treatment of type 2 diabetes.",
    "Second-line therapy for refractory epilepsy.",
    "Contraindicated in pregnancy.",
]
SAFETY = DOSING + TARGET + INDICATION  # all lexically detectable
NORMAL = [
    "TP53 regulates apoptosis in colorectal cells.",
    "The signalling pathway is upregulated in tumours.",
    "This finding is supported by reference 1.",
]


def _ok_check() -> CitationCheck:
    return CitationCheck(
        identifier="pmid:1",
        id_type=IdType.PMID,
        resolution_status=ResolutionStatus.OK,
        source_status=SourceStatus.ACTIVE,
    )


def _score(text: str, category: Category):
    return score_claim(
        category=category,
        label=JudgeLabel.SUPPORTED,
        confidence=1.0,
        citation_checks=[_ok_check()],
        retrieval_mode=RetrievalMode.CITED_FULLTEXT,
        claim_text=text,
        config=Config(),
    )


def _corpus() -> list[tuple[str, Category]]:
    rows: list[tuple[str, Category]] = []
    for text in SAFETY:
        rows.append((text, Category.SAFETY_CRITICAL))  # correctly categorized
        rows.append((text, Category.MECHANISTIC))  # adversarially miscategorized
    for text in NORMAL:
        rows.append((text, Category.MECHANISTIC))
    return rows


def test_corpus_is_non_vacuous():
    safety_rows = [r for r in _corpus() if r[1] is Category.SAFETY_CRITICAL]
    assert len(safety_rows) >= 15
    assert all(is_safety_critical_text(t) for t in SAFETY)
    for subtype in (DOSING, TARGET, INDICATION):
        assert all(is_safety_critical_text(t) for t in subtype)


def test_no_safety_critical_claim_auto_passes():
    leaks = [
        text
        for text, category in _corpus()
        if category is Category.SAFETY_CRITICAL and _score(text, category).auto_passed
    ]
    assert leaks == []


def test_independent_oracle_no_lexical_safety_claim_auto_passes():
    leaks = [
        text
        for text, category in _corpus()
        if is_safety_critical_text(text) and _score(text, category).auto_passed
    ]
    assert leaks == []


def test_gate_is_not_vacuous_a_plain_grounded_claim_can_auto_pass():
    result = _score("TP53 regulates apoptosis in colorectal cells.", Category.MECHANISTIC)
    assert result.auto_passed is True
