from litmuz_core.cite.identifiers import (
    extract_identifiers,
    normalize_doi,
    normalize_pmcid,
    normalize_pmid,
)
from litmuz_core.config import IdType


def test_normalize_pmid_strips_leading_zeros():
    assert normalize_pmid("0012345") == "12345"
    assert normalize_pmid(" 678 ") == "678"


def test_normalize_doi_lowercases_and_strips_url_and_trailing_punct():
    assert normalize_doi("https://doi.org/10.1000/AbC") == "10.1000/abc"
    assert normalize_doi("doi:10.1000/xyz.") == "10.1000/xyz"
    assert normalize_doi("10.1000/xyz),") == "10.1000/xyz"


def test_normalize_pmcid():
    assert normalize_pmcid("PMC0007654321") == "PMC7654321"
    assert normalize_pmcid("pmc123") == "PMC123"


def test_extract_labelled_identifiers():
    text = "As shown (PMID: 12345) and in PMC7654321, with doi:10.1000/xyz123."
    ids = extract_identifiers(text)
    pairs = {(c.id_type, c.value) for c in ids}
    assert (IdType.PMID, "12345") in pairs
    assert (IdType.PMCID, "PMC7654321") in pairs
    assert (IdType.DOI, "10.1000/xyz123") in pairs


def test_extract_bare_doi_and_url_doi():
    text = "See 10.1000/abc and https://doi.org/10.2000/DEF for details."
    values = {c.value for c in extract_identifiers(text) if c.id_type is IdType.DOI}
    assert "10.1000/abc" in values
    assert "10.2000/def" in values


def test_no_identifiers_returns_empty_list():
    assert extract_identifiers("A plain mechanistic claim with no citation.") == []


def test_extraction_is_deduplicated():
    text = "PMID: 12345 and again PMID:12345."
    ids = [c for c in extract_identifiers(text) if c.id_type is IdType.PMID]
    assert len(ids) == 1
