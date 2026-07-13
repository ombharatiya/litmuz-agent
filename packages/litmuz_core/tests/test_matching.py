from litmuz_core.cite.matching import (
    author_match,
    title_match,
    title_similarity,
    year_match,
)
from litmuz_core.config import MatchResult

THRESHOLD = 0.95


def test_title_similarity_is_word_order_insensitive():
    assert title_similarity("TP53 regulates apoptosis", "apoptosis regulates TP53") == 1.0
    assert title_similarity("kinase inhibition effects", "unrelated immunology review") < 0.5


def test_title_match_tristate():
    assert title_match(None, "anything", THRESHOLD) is MatchResult.NOT_APPLICABLE
    assert title_match("A B C", "C B A", THRESHOLD) is MatchResult.TRUE
    assert title_match("A B C", "completely different words here", THRESHOLD) is MatchResult.FALSE
    assert title_match("some title", None, THRESHOLD) is MatchResult.FALSE


def test_author_match_subset_and_folding():
    assert author_match(["Smith"], ["Smith", "Doe"]) is MatchResult.TRUE
    assert author_match(["Núñez"], ["Nunez", "Smith"]) is MatchResult.TRUE  # diacritics folded
    assert author_match(["Smith", "Zhang"], ["Smith", "Doe"]) is MatchResult.FALSE
    assert author_match([], ["Smith"]) is MatchResult.NOT_APPLICABLE
    assert author_match(["Smith"], []) is MatchResult.FALSE


def test_year_match_membership_over_epub_and_print():
    assert year_match(2020, [2019, 2020]) is MatchResult.TRUE  # print year
    assert year_match(2019, [2019, 2020]) is MatchResult.TRUE  # epub year
    assert year_match(2001, [2019, 2020]) is MatchResult.FALSE
    assert year_match(None, [2020]) is MatchResult.NOT_APPLICABLE
    assert year_match(2020, []) is MatchResult.FALSE
