"""AC-CITE-1..10: the deterministic citation check. No network; FakeClient only."""

from litmuz_core.cite.checker import check_citation
from litmuz_core.config import IdType, ResolutionStatus, SourceStatus
from litmuz_core.schemas import CitedId, ClaimAttribution


def _pmid(v="12345"):
    return CitedId(id_type=IdType.PMID, value=v)


def test_valid_pmid_with_matching_attribution_is_ok(fake_client, config):
    attribution = ClaimAttribution(surnames=["Smith"], year=2020)
    check = check_citation(_pmid(), attribution, fake_client, config)
    assert check.resolution_status is ResolutionStatus.OK
    assert check.source_status is SourceStatus.ACTIVE
    assert check.author_match.value == "true"
    assert check.year_match.value == "true"


def test_fabricated_pmid_is_flagged(fake_client, config):
    # AC-CITE-2: well-formed but authoritatively absent id.
    check = check_citation(_pmid("99999999"), None, fake_client, config)
    assert check.resolution_status is ResolutionStatus.FABRICATED
    assert check.source_status is None


def test_metadata_mismatch_on_wrong_year(fake_client, config):
    # AC-CITE-4: exists, but attribution year does not match.
    attribution = ClaimAttribution(surnames=["Smith"], year=2001)
    check = check_citation(_pmid(), attribution, fake_client, config)
    assert check.resolution_status is ResolutionStatus.METADATA_MISMATCH
    assert check.year_match.value == "false"


def test_bare_identifier_never_yields_metadata_mismatch(fake_client, config):
    # AC-CITE-8: no attribution -> matches are not_applicable -> status ok.
    check = check_citation(_pmid(), None, fake_client, config)
    assert check.resolution_status is ResolutionStatus.OK
    assert check.title_match.value == "not_applicable"
    assert check.author_match.value == "not_applicable"
    assert check.year_match.value == "not_applicable"


def test_retracted_source_is_recorded(fake_client, config):
    # AC-CITE-9: retraction is deterministic; severity (Phase 2) caps it.
    check = check_citation(_pmid("22222"), None, fake_client, config)
    assert check.resolution_status is ResolutionStatus.OK
    assert check.source_status is SourceStatus.RETRACTED


def test_expression_of_concern_is_recorded(fake_client, config):
    check = check_citation(_pmid("44444"), None, fake_client, config)
    assert check.source_status is SourceStatus.CONCERN


def test_preprint_doi_is_unresolved_not_fabricated(fake_client, config):
    # AC-CITE-3: a valid-looking id absent from queried sources is unresolved.
    doi = CitedId(id_type=IdType.DOI, value="10.5555/preprint.2026")
    check = check_citation(doi, None, fake_client, config)
    assert check.resolution_status is ResolutionStatus.UNRESOLVED


def test_transient_failure_is_unknown_and_not_cached(fake_client, config):
    # AC-CITE-5: bounded backoff exhausted -> unknown, never fabricated, never ok.
    cache: dict = {}
    check = check_citation(_pmid("33333"), None, fake_client, config, cache=cache)
    assert check.resolution_status is ResolutionStatus.UNKNOWN
    assert cache == {}  # transient outcomes are never cached


def test_pmcid_resolves(fake_client, config):
    # AC-CITE-10.
    pmcid = CitedId(id_type=IdType.PMCID, value="PMC7654321")
    check = check_citation(pmcid, None, fake_client, config)
    assert check.resolution_status is ResolutionStatus.OK
    assert check.source_status is SourceStatus.ACTIVE


def test_cache_prevents_a_second_client_call(fake_client, config):
    # AC-CITE-6: within a run the same id is not re-fetched.
    cache: dict = {}
    check_citation(_pmid(), None, fake_client, config, cache=cache)
    check_citation(_pmid(), None, fake_client, config, cache=cache)
    assert fake_client.calls.count("pmid:12345") == 1
