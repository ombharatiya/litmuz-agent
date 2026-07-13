"""Categorizer behaviour, fully offline (AC-CATEGORY-1..6).

The suite proves the safety cap does not depend on the model. A fake LlmClient stands
in for the real one: it returns a canned LlmResponse or raises LlmError. The lexical
fail-safe fixtures are adversarial and indirect phrasings that carry no literal category
word yet the shared safety oracle catches, and the fake model returns the wrong label
for every one of them, so a pass proves 100 percent recall independent of the model.
"""

from __future__ import annotations

import pytest

from litmuz_core.categorize import categorize, validate_taxonomy_config
from litmuz_core.config import Category, Config
from litmuz_core.llm import LlmError, LlmResponse


class FakeLlm:
    """Deterministic stand-in for LlmClient. Returns canned text or raises LlmError."""

    def __init__(
        self,
        text: str = "",
        *,
        error: bool = False,
        responder=None,
    ) -> None:
        self.text = text
        self.error = error
        self.responder = responder
        self.calls = 0

    def complete(
        self, *, system: str, prompt: str, temperature: float = 0.0, max_tokens: int = 1024
    ) -> LlmResponse:
        self.calls += 1
        if self.error:
            raise LlmError("simulated model failure")
        text = self.responder(prompt) if self.responder is not None else self.text
        return LlmResponse(text=text, model="fake")


def _json(category: str, confidence: float) -> str:
    return '{"category": "' + category + '", "confidence": ' + str(confidence) + "}"


# Adversarial and indirect safety claims that carry no literal category word but the
# shared lexical oracle catches. Recall on these must be independent of the model.
DOSING_CLAIMS = [
    "5 mg twice daily.",
    "10 mg/kg was given intravenously.",
    "Patients received 200 mg every morning.",
    "Escalated to 1 g per day.",
    "50 mcg administered subcutaneously.",
    "A 0.5 mg/kg loading amount was used.",
    "Titrated upward over four weeks.",
    "Given bid for two weeks.",
    "Infused at 100 units per hour.",
    "The regimen comprised three agents.",
    "Administration occurred every 8 hours.",
    "Escalation followed a q8h schedule.",
    "2.5 mg was given at bedtime.",
    "Delivered as 15 mg/m2 by infusion.",
    "Maintenance was 100 mg qd.",
    "Received 40 IU nightly.",
    "Dosage was capped at the low end.",
    "Three times daily with meals.",
]

TARGET_CLAIMS = [
    "Osimertinib targets EGFR.",
    "It is a selective EGFR inhibitor.",
    "The compound binds to BRAF.",
    "A potent inhibitor of ALK.",
    "Acts as an antagonist of the D2 receptor.",
    "Functions as an agonist of GLP-1.",
    "The molecule is selective for JAK2.",
    "Targeting KRAS G12C directly.",
    "A targeted covalent binder was designed.",
    "This kinase inhibitor blocks proliferation.",
    "The antibody targets PD-L1.",
    "Binds to the ATP pocket of CDK4.",
    "Designed as an inhibitor of PARP.",
    "A selective agonist of the MOR.",
    "It targeted the MAPK node.",
    "A reversible BTK inhibitor.",
    "The ligand binds to VEGFR2.",
    "An antagonist of CXCR4 signalling.",
]

INDICATION_CLAIMS = [
    "Indicated for metastatic melanoma.",
    "First-line therapy for NSCLC.",
    "Approved for the treatment of hypertension.",
    "A second-line option in colorectal cancer.",
    "Used off-label for pediatric epilepsy.",
    "Contraindicated in hepatic impairment.",
    "The indication is advanced breast cancer.",
    "Standard therapy for relapsed lymphoma.",
    "Approved for adults with type 2 diabetes.",
    "Indicated for the maintenance of remission.",
    "First line in newly diagnosed myeloma.",
    "Its indications include chronic pain.",
    "Reserved as second line after failure.",
    "For the treatment of moderate asthma.",
    "Approved for use in heart failure.",
    "Off label in refractory cases.",
    "Contraindicated during pregnancy.",
    "Adjuvant therapy for early-stage disease.",
]

SAFETY_CLAIMS = DOSING_CLAIMS + TARGET_CLAIMS + INDICATION_CLAIMS

# Plain mechanistic or citation claims the safety oracle does not catch, paired with the
# category a correct model would return.
NEGATIVE_CONTROLS = [
    ("TP53 regulates apoptosis.", Category.MECHANISTIC),
    ("This is supported by reference 1.", Category.CITATION),
    ("The pathway is upregulated in tumor samples.", Category.MECHANISTIC),
    ("Expression increased under hypoxic conditions.", Category.MECHANISTIC),
    ("As shown in the cited study, the effect persisted.", Category.CITATION),
    ("MYC amplification drives proliferation.", Category.MECHANISTIC),
    ("The finding aligns with prior work.", Category.CITATION),
    ("BRCA1 participates in DNA repair.", Category.MECHANISTIC),
    ("The reference supports this conclusion.", Category.CITATION),
    ("Wnt signalling promotes stem cell renewal.", Category.MECHANISTIC),
    ("According to the source, levels dropped.", Category.CITATION),
    ("Hypermethylation silences the promoter.", Category.MECHANISTIC),
    ("This claim cites the accompanying figure.", Category.CITATION),
    ("NF-kB activation follows stimulation.", Category.MECHANISTIC),
    ("The authors report a similar trend.", Category.CITATION),
    ("Mitochondrial dysfunction impairs metabolism.", Category.MECHANISTIC),
    ("The result is consistent with the literature.", Category.CITATION),
    ("PTEN loss activates the pathway.", Category.MECHANISTIC),
    ("This statement references the appendix.", Category.CITATION),
    ("Apoptosis is triggered by cytochrome release.", Category.MECHANISTIC),
    ("The observation matches an earlier publication.", Category.CITATION),
    ("Glycolysis is enhanced in these cells.", Category.MECHANISTIC),
]


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.mark.parametrize("claim", SAFETY_CLAIMS)
def test_lexical_failsafe_forces_safety_against_adversarial_model(claim, config):
    """AC-CATEGORY-4/5: the oracle forces SAFETY_CRITICAL even when the model insists
    every claim is mechanistic. This is 100 percent recall independent of the model."""
    model = FakeLlm(text=_json("mechanistic", 0.99))
    assert categorize(claim, model, config) is Category.SAFETY_CRITICAL


def test_lexical_failsafe_does_not_call_the_model(config):
    """AC-CATEGORY-5: a lexical safety hit short-circuits before any model call."""
    model = FakeLlm(text=_json("mechanistic", 0.99))
    result = categorize("Patients received 200 mg every morning.", model, config)
    assert result is Category.SAFETY_CRITICAL
    assert model.calls == 0


@pytest.mark.parametrize("claim,expected", NEGATIVE_CONTROLS)
def test_negative_controls_are_not_misflagged(claim, expected, config):
    """A correct model on a non-safety claim yields that claim's true category, never
    an over-flag to safety_critical."""
    model = FakeLlm(text=_json(expected.value, 0.99))
    assert categorize(claim, model, config) is expected


def test_model_safety_label_dominates(config):
    """AC-CATEGORY-1: a safety_critical label from the model wins outright, even below
    the confidence floor, on a claim the oracle does not catch."""
    model = FakeLlm(text=_json("safety_critical", 0.30))
    assert categorize("TP53 regulates apoptosis.", model, config) is Category.SAFETY_CRITICAL


def test_model_error_fails_closed(config):
    """AC-CATEGORY-5: a raised LlmError falls closed to SAFETY_CRITICAL."""
    model = FakeLlm(error=True)
    assert categorize("TP53 regulates apoptosis.", model, config) is Category.SAFETY_CRITICAL


@pytest.mark.parametrize(
    "text",
    [
        "I cannot classify this claim.",
        "",
        "{category: mechanistic, confidence: 0.9}",
        '{"category": "mechanistic"}',
        '{"category": "nonsense", "confidence": 0.99}',
        '{"category": "mechanistic", "confidence": "high"}',
    ],
)
def test_unparseable_output_fails_closed(text, config):
    """AC-CATEGORY-5: missing, malformed, or off-schema output falls closed."""
    model = FakeLlm(text=text)
    assert categorize("TP53 regulates apoptosis.", model, config) is Category.SAFETY_CRITICAL


def test_low_confidence_fails_closed(config):
    """AC-CATEGORY-5: confidence below config.categorizer_conf falls closed."""
    model = FakeLlm(text=_json("mechanistic", 0.50))
    assert config.categorizer_conf == 0.80
    assert categorize("TP53 regulates apoptosis.", model, config) is Category.SAFETY_CRITICAL


def test_confidence_at_or_above_floor_is_kept(config):
    """A confident, correct, non-safety label passes through unchanged."""
    model = FakeLlm(text=_json("mechanistic", 0.80))
    assert categorize("TP53 regulates apoptosis.", model, config) is Category.MECHANISTIC


def test_model_json_with_surrounding_prose_is_parsed(config):
    """The JSON object is extracted even with leading and trailing prose."""
    text = 'Here is my answer: {"category": "citation", "confidence": 0.95}. Done.'
    model = FakeLlm(text=text)
    assert categorize("This is supported by reference 1.", model, config) is Category.CITATION


def test_validate_taxonomy_passes_for_real_config(config):
    """AC-CATEGORY-6: the shipped taxonomy is valid; the guard does not raise."""
    validate_taxonomy_config(config)


def test_validate_taxonomy_raises_on_empty_subtypes(config, monkeypatch):
    """AC-CATEGORY-6: an empty SAFETY_SUBTYPES is a fail-closed startup error."""
    monkeypatch.setattr("litmuz_core.categorize.categorizer.SAFETY_SUBTYPES", ())
    with pytest.raises(ValueError):
        validate_taxonomy_config(config)


def test_validate_taxonomy_raises_when_category_missing_safety(config, monkeypatch):
    """AC-CATEGORY-6: a Category enum without SAFETY_CRITICAL is a fail-closed error."""
    from enum import Enum

    class BrokenCategory(str, Enum):
        CITATION = "citation"
        MECHANISTIC = "mechanistic"

    monkeypatch.setattr("litmuz_core.categorize.categorizer.Category", BrokenCategory)
    with pytest.raises(ValueError):
        validate_taxonomy_config(config)
