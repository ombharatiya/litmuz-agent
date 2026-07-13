"""AC-DECOMP-3/7: deterministic citation extraction and reference resolution."""

from litmuz_core.cite.checker import check_citation
from litmuz_core.config import IdType, ResolutionStatus, SourceStatus
from litmuz_core.decompose.references import build_reference_index, resolve_citations

NUMBERED_MEMO = """\
TP53 loss drives proliferation [1]. Kinase X inhibits the downstream pathway [2, 3].

References
1. Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
2. Nguyen T. Kinase inhibition and pathway effects. Cell. 2021. doi:10.1000/xyz123.
3. Garcia M. Receptor binding full text. 2017. PMCID: PMC7654321.
"""

AUTHOR_YEAR_MEMO = """\
The recommended dose was 5 mg daily (Smith et al., 2020).

References
Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
Nguyen T. Kinase inhibition and pathway effects. 2021. doi:10.1000/xyz123.
"""


def test_numbered_marker_resolves_to_reference_identifier():
    index = build_reference_index(NUMBERED_MEMO)
    resolved = resolve_citations("TP53 loss drives proliferation [1].", index)
    assert len(resolved) == 1
    rc = resolved[0]
    assert rc.cited_id.id_type is IdType.PMID
    assert rc.cited_id.value == "12345"
    assert rc.attribution.year == 2020
    assert "Smith" in rc.attribution.surnames


def test_numbered_list_and_range_markers_expand():
    index = build_reference_index(NUMBERED_MEMO)
    resolved = resolve_citations("Kinase X inhibits the pathway [2, 3].", index)
    values = {(rc.cited_id.id_type, rc.cited_id.value) for rc in resolved}
    assert (IdType.DOI, "10.1000/xyz123") in values
    assert (IdType.PMCID, "PMC7654321") in values

    resolved_range = resolve_citations("Multiple lines of evidence [1-3].", index)
    assert len(resolved_range) == 3


def test_author_year_marker_resolves():
    index = build_reference_index(AUTHOR_YEAR_MEMO)
    resolved = resolve_citations("The recommended dose was 5 mg daily (Smith et al., 2020).", index)
    assert len(resolved) == 1
    assert resolved[0].cited_id.value == "12345"


def test_inline_identifier_without_references_has_empty_attribution():
    index = build_reference_index("The target is EGFR (PMID: 12345).")
    resolved = resolve_citations("The target is EGFR (PMID: 12345).", index)
    assert len(resolved) == 1
    assert resolved[0].cited_id.value == "12345"
    assert resolved[0].attribution.surnames == []
    assert resolved[0].attribution.year is None


def test_end_to_end_reference_resolution_then_citation_check(fake_client, config):
    # AC-DECOMP-7 -> AC-CITE-1: a numbered marker resolves and the citation checks out.
    index = build_reference_index(NUMBERED_MEMO)
    resolved = resolve_citations("TP53 loss drives proliferation [1].", index)
    check = check_citation(resolved[0].cited_id, resolved[0].attribution, fake_client, config)
    assert check.resolution_status is ResolutionStatus.OK
    assert check.source_status is SourceStatus.ACTIVE
    assert check.author_match.value == "true"
    assert check.year_match.value == "true"
