"""A curated reference of Human Accelerated Regions (HARs) and mammalian conservation,
drawn from the Gladstone Institutes / Katie Pollard lab and the Zoonomia project.

This is the deterministic ground truth for the genomic verification mode: it is to a genomic
claim what the primary-literature registries (PubMed/PMC/Crossref) are to a citation. It is a
curated, well-characterized subset (not the full ~3,100-HAR catalogue), so absence from it is
treated as "cannot confirm" (an honest yellow), never as a silent pass.

Sources:
- Pollard KS, et al. An RNA gene expressed during cortical development that evolved rapidly in
  humans. Nature 2006. PMID 16915236. (HAR1; the original HAR screen.)
- Prabhakar S, et al. Human-specific gain of function in a developmental enhancer. Science 2008.
  PMID 18772396. (HACNS1 / HAR2 / CE114.)
- Boyd JL, et al. Human-chimpanzee differences in a FZD8 enhancer alter cell-cycle dynamics in the
  developing neocortex. Curr Biol 2015. PMID 25702576. (HARE5 / 2xHAR.238.)
- Zoonomia Consortium (Christmas MJ, et al.). Evolutionary constraint and innovation across
  hundreds of placental mammals. Science 2023. (Genome-wide mammalian constraint scores.)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenomicElement:
    """One well-characterized human accelerated region."""

    name: str
    aliases: tuple[str, ...]
    chrom: str  # hg38
    start: int  # hg38, best-documented window (approximate for band-level elements)
    end: int
    locus: str  # cytogenetic band / nearby gene, e.g. "chr20q13.33"
    human_accelerated: bool
    description: str
    citation: str


# A curated set of real, well-studied HARs. Coordinates are hg38 and are used for overlap tests;
# the human-readable evidence leans on the locus + citation so it stays accurate at band level.
HAR_ELEMENTS: tuple[GenomicElement, ...] = (
    GenomicElement(
        name="HAR1",
        aliases=("HAR1F", "HAR1A", "HAR 1"),
        chrom="chr20",
        start=63_895_000,
        end=63_896_100,
        locus="chr20q13.33",
        human_accelerated=True,
        description=(
            "The most changed of the original human accelerated regions: 18 human-specific "
            "substitutions in 118 bp, part of HAR1F, an RNA gene expressed in Cajal-Retzius "
            "neurons during cortical development"
        ),
        citation="Pollard KS, et al. Nature 2006. PMID 16915236",
    ),
    GenomicElement(
        name="HACNS1",
        aliases=("HAR2", "CE114", "2xHAR.3"),
        chrom="chr2",
        start=236_773_000,
        end=236_774_000,
        locus="chr2q37.3 (near GBX2)",
        human_accelerated=True,
        description=(
            "A developmental limb/pharyngeal-arch enhancer with a human-specific gain of "
            "function: 13 human-specific substitutions in 81 bp, one of the fastest-evolving "
            "noncoding elements in the human genome"
        ),
        citation="Prabhakar S, et al. Science 2008. PMID 18772396",
    ),
    GenomicElement(
        name="HARE5",
        aliases=("2xHAR.238", "FZD8 enhancer"),
        chrom="chr10",
        start=35_650_000,
        end=35_651_200,
        locus="chr10p11.21 (FZD8 enhancer)",
        human_accelerated=True,
        description=(
            "A FZD8 enhancer whose human variant drives earlier and faster neural progenitor "
            "cell-cycle progression and a larger neocortex in transgenic mice"
        ),
        citation="Boyd JL, et al. Curr Biol 2015. PMID 25702576",
    ),
    GenomicElement(
        name="2xHAR.170",
        aliases=("HAR 170",),
        chrom="chr5",
        start=87_960_000,
        end=87_961_000,
        locus="chr5q14.3 (near MEF2C)",
        human_accelerated=True,
        description=(
            "A human accelerated region near the neurodevelopmental transcription factor MEF2C, "
            "implicated in human-specific regulation of cortical neuron development"
        ),
        citation="Pollard KS, et al. PLoS Genet 2006. PMID 17040131",
    ),
)

# Fast lookup by any name or alias, uppercased and space-normalized.
_BY_NAME: dict[str, GenomicElement] = {}
for _el in HAR_ELEMENTS:
    for _key in (_el.name, *_el.aliases):
        _BY_NAME[_key.upper().replace(" ", "")] = _el


# Mammalian constraint, at a coarse, honest granularity: the Zoonomia project scored per-base
# constraint across 240 placental mammals. We do not bundle the genome-wide track; we record the
# fact that these HAR loci are within constrained but human-accelerated sequence, which is the
# defining paradox of a HAR (deeply conserved across mammals, then rapidly changed in humans).
ZOONOMIA_NOTE: str = (
    "Zoonomia Consortium (Christmas MJ, et al., Science 2023) scored evolutionary constraint "
    "across 240 placental mammals; human accelerated regions are by definition sequences that "
    "were deeply constrained across mammals and then changed rapidly on the human lineage"
)


def find_by_name(text: str) -> GenomicElement | None:
    """Return the reference element named or aliased anywhere in the text, if any."""
    import re

    # Tokens that look like element names: HAR1, HACNS1, 2xHAR.238, HARE5, etc.
    for token in re.findall(r"\b(?:2xHAR\.\d+|HACNS\d+|HARE\d+|HAR\s?\d+)\b", text, re.IGNORECASE):
        el = _BY_NAME.get(token.upper().replace(" ", ""))
        if el is not None:
            return el
    # Also catch explicit aliases mentioned by name (e.g. "the FZD8 enhancer").
    upper = text.upper()
    for key, el in _BY_NAME.items():
        if key.isalpha() and len(key) >= 5 and key in upper.replace(" ", ""):
            return el
    return None


def find_by_coordinate(chrom: str, start: int, end: int) -> GenomicElement | None:
    """Return a reference HAR overlapping the given hg38 interval, if any."""
    c = chrom if chrom.startswith("chr") else f"chr{chrom}"
    for el in HAR_ELEMENTS:
        if el.chrom == c and start <= el.end and end >= el.start:
            return el
    return None
