"""Local runner: verify a memo end to end against live NCBI and the judge model.

This is a thin adapter over litmuz_core.run_pipeline for local testing. It performs real
network calls: PubMed and Crossref for citation resolution, PubMed and PMC for evidence,
and the judge model for decomposition, entailment and categorization.

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...        # required
  export NCBI_API_KEY=...                     # optional, lifts NCBI rate limits
  uv run python apps/cli/verify.py apps/cli/sample_memo.md
  cat memo.md | uv run python apps/cli/verify.py -      # read from stdin
  uv run python apps/cli/verify.py memo.md --json       # full report as JSON
"""

from __future__ import annotations

import argparse
import os
import sys

from litmuz_core.cite.clients import NcbiCrossrefClient
from litmuz_core.config import Config
from litmuz_core.llm import AnthropicClient
from litmuz_core.pipeline import run_pipeline
from litmuz_core.report.assembler import human_readable
from litmuz_core.retrieve.clients import NcbiPmcClient


def _read_memo(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    with open(source, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a research memo with Litmuz.")
    parser.add_argument("memo", help="path to a memo file, or - to read from stdin")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. Decomposition, the judge and categorization "
            "need it. Export it and re-run.",
            file=sys.stderr,
        )
        return 2

    memo = _read_memo(args.memo)
    config = Config.from_env()

    def progress(stage: str, done: int, total: int) -> None:
        print(f"  [{stage}] {done}/{total}", file=sys.stderr)

    print(f"Verifying with judge model {config.judge_model} ...", file=sys.stderr)
    report = run_pipeline(
        memo,
        llm=AnthropicClient(config),
        metadata_client=NcbiCrossrefClient(config),
        retrieval_client=NcbiPmcClient(config),
        config=config,
        on_progress=progress,
    )

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(human_readable(report))

    print(f"\nSummary: {report.summary_counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
