from litmuz_core.config import (
    Category,
    Config,
    Diagnostic,
    MatchResult,
    ResolutionStatus,
    SourceStatus,
    TrafficLight,
)


def test_enum_values_are_the_canonical_strings():
    assert ResolutionStatus.FABRICATED.value == "fabricated"
    assert {s.value for s in ResolutionStatus} == {
        "ok",
        "metadata_mismatch",
        "fabricated",
        "unresolved",
        "unknown",
    }
    assert {s.value for s in SourceStatus} == {"active", "retracted", "concern"}
    assert {t.value for t in TrafficLight} == {"green", "yellow", "red"}
    assert {d.value for d in Diagnostic} == {"D1", "D2", "D3", "D4", "D5"}
    assert {c.value for c in Category} == {"citation", "mechanistic", "safety_critical"}
    assert MatchResult.NOT_APPLICABLE.value == "not_applicable"


def test_config_defaults_are_the_ac_pass_lines():
    c = Config()
    assert c.judge_model == "claude-opus-4-8"
    assert c.high_conf == 0.85
    assert c.borderline == 0.70
    assert c.title_match_threshold == 0.95
    assert c.max_input_bytes == 51_200


def test_from_env_overrides_and_coerces_types():
    c = Config.from_env(
        {
            "JUDGE_MODEL": "claude-sonnet-5",
            "HIGH_CONF": "0.9",
            "TOP_K": "8",
            "NCBI_API_KEY": "abc123",
        }
    )
    assert c.judge_model == "claude-sonnet-5"
    assert c.high_conf == 0.9 and isinstance(c.high_conf, float)
    assert c.top_k == 8 and isinstance(c.top_k, int)
    assert c.ncbi_api_key == "abc123"
    # untouched knobs keep defaults
    assert c.borderline == 0.70


def test_from_env_empty_keeps_all_defaults():
    assert Config.from_env({}) == Config()
