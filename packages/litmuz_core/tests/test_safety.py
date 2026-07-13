"""The independent lexical safety oracle: high recall on clear target/dose/indication
assertions, without sweeping in generic mechanism (AC-CATEGORY-5, AC-SAFETY-4)."""

import pytest

from litmuz_core.safety import is_safety_critical_text, match_safety


@pytest.mark.parametrize(
    "text,subtype",
    [
        ("The recommended dose was 5 mg daily.", "dosing"),
        ("Patients received 10 mg/kg twice daily.", "dosing"),
        ("Administered at a dosage of 200 mg.", "dosing"),
        ("Escalated per a weight-based regimen.", "dosing"),
        ("Drug X is indicated for metastatic melanoma.", "indication"),
        ("First-line therapy for NSCLC.", "indication"),
        ("Approved for the treatment of hypertension.", "indication"),
        ("Osimertinib targets EGFR T790M.", "target"),
        ("It is a selective EGFR inhibitor.", "target"),
        ("The antagonist of the receptor reduced signalling.", "target"),
    ],
)
def test_positive_safety_signals(text, subtype):
    matched, found = match_safety(text)
    assert matched
    assert found == subtype


@pytest.mark.parametrize(
    "text",
    [
        "TP53 regulates apoptosis in colorectal carcinoma cells.",
        "The signalling pathway is upregulated in tumour samples.",
        "This citation supports the stated finding.",
        "The receptor is expressed in hepatic tissue.",
        "Expression increased under hypoxic conditions.",
    ],
)
def test_negative_non_safety_claims(text):
    assert not is_safety_critical_text(text)


@pytest.mark.parametrize(
    "text,subtype",
    [
        ("The maximum tolerated amount was 3 grams.", "dosing"),
        ("Adjusted for 2 kilograms of body weight.", "dosing"),
        ("Infused 250 milliliters over an hour.", "dosing"),
        ("Used to treat chronic migraine.", "indication"),
        ("Prescribed for the management of pain.", "indication"),
        ("Recommended in patients with heart failure.", "indication"),
        ("The drug acts on the EGFR receptor.", "target"),
    ],
)
def test_adversarial_indirect_phrasings(text, subtype):
    matched, found = match_safety(text)
    assert matched
    assert found == subtype
