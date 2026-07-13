"""AC-JUDGE-1..7: the entailment judge. Offline; a scripted FakeLlm, never a model."""

import json

from litmuz_core.config import JudgeLabel, RetrievalMode
from litmuz_core.judge import JUDGE_SYSTEM_PROMPT, judge_claim
from litmuz_core.llm import LlmError, LlmResponse
from litmuz_core.schemas import Passage

PASSAGE_TEXT = (
    "Drug X reduced tumor volume by 40 percent in treated mice. "
    "The cohort included 20 animals followed for 12 weeks."
)
SENTENCE = "Drug X reduced tumor volume by 40 percent in treated mice."
CLAIM = "Drug X shrinks tumors in mice."


class FakeLlm:
    """Scripted client: returns queued texts in order; a queued exception is raised."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024):
        self.calls.append({"system": system, "prompt": prompt, "temperature": temperature})
        if not self.script:
            raise AssertionError("FakeLlm called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LlmResponse(text=item, model="fake-judge")


def _passage(text=PASSAGE_TEXT, source_id="pmid:12345"):
    return Passage(source_id=source_id, text=text, retrieval_mode=RetrievalMode.CITED_ABSTRACT)


def _reply(label, sentence=None, confidence=0.9, rationale="entailment result"):
    return json.dumps(
        {
            "label": label,
            "evidence_sentence": sentence,
            "confidence": confidence,
            "rationale": rationale,
        }
    )


def test_supported_claim_carries_verbatim_evidence(config):
    llm = FakeLlm([_reply("supported", SENTENCE, confidence=0.92)])
    verdict, evidence = judge_claim(CLAIM, [_passage()], llm, config)
    assert verdict.label is JudgeLabel.SUPPORTED
    assert verdict.confidence == 0.92
    assert evidence.evidence_sentence == SENTENCE
    assert evidence.evidence_sentence in PASSAGE_TEXT
    assert evidence.source_locator == {"source_id": "pmid:12345"}
    assert evidence.evidence_not_located is False


def test_judge_call_uses_pinned_prompt_and_zero_temperature(config):
    llm = FakeLlm([_reply("supported", SENTENCE)])
    judge_claim(CLAIM, [_passage()], llm, config)
    call = llm.calls[0]
    assert call["system"] == JUDGE_SYSTEM_PROMPT
    assert call["temperature"] == 0.0
    assert CLAIM in call["prompt"]
    assert PASSAGE_TEXT in call["prompt"]


def test_contradicted_claim(config):
    llm = FakeLlm([_reply("contradicted", SENTENCE, confidence=0.8)])
    verdict, evidence = judge_claim("Drug X grows tumors in mice.", [_passage()], llm, config)
    assert verdict.label is JudgeLabel.CONTRADICTED
    assert evidence.evidence_sentence == SENTENCE
    assert evidence.source_locator == {"source_id": "pmid:12345"}


def test_unsupported_claim_has_no_located_evidence(config):
    llm = FakeLlm([_reply("unsupported", None, confidence=0.7)])
    verdict, evidence = judge_claim("Drug X cures headaches.", [_passage()], llm, config)
    assert verdict.label is JudgeLabel.UNSUPPORTED
    assert evidence.evidence_not_located is True
    assert evidence.evidence_sentence is None


def test_non_substring_evidence_becomes_judge_error(config):
    # AC-JUDGE-1: evidence must be a verbatim substring of the judged passage.
    attempts = config.retrieval_max_retries + 1
    llm = FakeLlm([_reply("supported", "A sentence the passage never said.")] * attempts)
    verdict, evidence = judge_claim(CLAIM, [_passage()], llm, config)
    assert verdict.label is JudgeLabel.JUDGE_ERROR
    assert verdict.confidence is None
    assert evidence.evidence_not_located is True
    assert len(llm.calls) == attempts


def test_invalid_label_becomes_judge_error(config):
    attempts = config.retrieval_max_retries + 1
    llm = FakeLlm([_reply("plausible", SENTENCE)] * attempts)
    verdict, _ = judge_claim(CLAIM, [_passage()], llm, config)
    assert verdict.label is JudgeLabel.JUDGE_ERROR


def test_llm_error_is_bounded_and_contained(config):
    # AC-JUDGE-7: retries are bounded and the failure never raises out of judge_claim.
    attempts = config.retrieval_max_retries + 1
    llm = FakeLlm([LlmError("model unavailable")] * attempts)
    verdict, evidence = judge_claim(CLAIM, [_passage()], llm, config)
    assert verdict.label is JudgeLabel.JUDGE_ERROR
    assert verdict.confidence is None
    assert evidence.evidence_not_located is True
    assert len(llm.calls) == attempts


def test_retry_recovers_from_unparseable_output(config):
    llm = FakeLlm(["not json at all", _reply("supported", SENTENCE, confidence=0.9)])
    verdict, _ = judge_claim(CLAIM, [_passage()], llm, config)
    assert verdict.label is JudgeLabel.SUPPORTED
    assert len(llm.calls) == 2


def test_any_contradiction_wins_aggregation(config):
    contra_text = "Drug X had no effect on tumor volume in treated mice."
    passages = [_passage(source_id="pmid:1"), _passage(text=contra_text, source_id="pmid:2")]
    llm = FakeLlm(
        [
            _reply("supported", SENTENCE, confidence=0.99),
            _reply("contradicted", contra_text, confidence=0.6),
        ]
    )
    verdict, evidence = judge_claim(CLAIM, passages, llm, config)
    assert verdict.label is JudgeLabel.CONTRADICTED
    assert evidence.evidence_sentence == contra_text
    assert evidence.source_locator == {"source_id": "pmid:2"}


def test_supported_choice_is_highest_confidence(config):
    other_text = "Tumor volume fell sharply after Drug X was given."
    passages = [_passage(source_id="pmid:1"), _passage(text=other_text, source_id="pmid:2")]
    llm = FakeLlm(
        [
            _reply("supported", SENTENCE, confidence=0.55),
            _reply("supported", other_text, confidence=0.91),
        ]
    )
    verdict, evidence = judge_claim(CLAIM, passages, llm, config)
    assert verdict.label is JudgeLabel.SUPPORTED
    assert verdict.confidence == 0.91
    assert evidence.evidence_sentence == other_text
    assert evidence.source_locator == {"source_id": "pmid:2"}


def test_one_errored_passage_does_not_hide_a_real_result(config):
    attempts = config.retrieval_max_retries + 1
    script = [LlmError("down")] * attempts + [_reply("unsupported", None, confidence=0.7)]
    llm = FakeLlm(script)
    passages = [_passage(source_id="pmid:1"), _passage(source_id="pmid:2")]
    verdict, evidence = judge_claim(CLAIM, passages, llm, config)
    assert verdict.label is JudgeLabel.UNSUPPORTED
    assert evidence.evidence_not_located is True


def test_prompt_is_narrow_entailment_only():
    # AC-JUDGE-2: entailment vocabulary present; judgement-of-writing vocabulary absent.
    lowered = JUDGE_SYSTEM_PROMPT.lower()
    assert "support" in lowered
    assert "contradict" in lowered
    assert "fails to support" in lowered
    assert "verbatim" in lowered
    assert "only evidence source" in lowered
    for key in ('"label"', '"evidence_sentence"', '"confidence"', '"rationale"'):
        assert key in JUDGE_SYSTEM_PROMPT
    assert "supported|contradicted|unsupported" in JUDGE_SYSTEM_PROMPT
    for banned in ("quality", "score", "rating", "rate", "well-written", "opinion"):
        assert banned not in lowered


def test_empty_passages_short_circuits(config):
    llm = FakeLlm([])
    verdict, evidence = judge_claim(CLAIM, [], llm, config)
    assert verdict.label is JudgeLabel.UNSUPPORTED
    assert verdict.confidence is None
    assert evidence.evidence_not_located is True
    assert llm.calls == []
