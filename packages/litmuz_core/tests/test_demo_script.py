"""The scripted demo (apps/cli/demo.py) is part of the gated suite, so it cannot drift from
the guarantees it narrates. We load it by path (apps/cli is a loose runner dir, not a
workspace package) and exercise the same functions the demo runs.
"""

from __future__ import annotations

import importlib.util
import pathlib

from litmuz_core.config import Category, Diagnostic, RetrievalMode, TrafficLight

_DEMO_PATH = pathlib.Path(__file__).resolve().parents[3] / "apps" / "cli" / "demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("litmuz_demo", _DEMO_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


demo = _load_demo()


def test_beat_1_fabricated_citation_is_red():
    report = demo.run_demo()
    fabricated = demo._claim(report, "fabricated result")
    statuses = [c.resolution_status.value for c in fabricated.citation_checks]
    assert "fabricated" in statuses
    assert fabricated.traffic_light == TrafficLight.RED
    assert fabricated.auto_passed is not True


def test_beat_2_unlocated_support_is_yellow_and_judge_never_runs():
    # _NoSupportLlm raises if the judge is called; returning at all proves it was not.
    yellow = demo.run_yellow_scenario()
    claim = yellow.claims[0]
    assert claim.category == Category.MECHANISTIC
    assert claim.traffic_light == TrafficLight.YELLOW
    assert claim.diagnostic == Diagnostic.D3
    assert claim.retrieval_mode == RetrievalMode.NONE
    assert claim.routed_to_review is True


def test_beat_3_safety_critical_never_auto_passes():
    report = demo.run_demo()
    dose = demo._claim(report, "5 mg")
    assert dose.category == Category.SAFETY_CRITICAL
    assert dose.traffic_light != TrafficLight.GREEN
    assert dose.auto_passed is not True
    assert dose.routed_to_review is True

    safety_autopassed = [
        c for c in report.claims if c.category == Category.SAFETY_CRITICAL and c.auto_passed is True
    ]
    assert safety_autopassed == []


def test_beat_4_model_swap_changes_provenance_only():
    default = demo.run_demo()
    swapped = demo.run_demo(judge_model="claude-sonnet-5")
    assert default.model_versions.get("judge") == "claude-opus-4-8"
    assert swapped.model_versions.get("judge") == "claude-sonnet-5"


def test_demo_main_reports_all_beats_hold(capsys):
    assert demo.main() == 0
    out = capsys.readouterr().out
    assert "All four beats held." in out
    assert "FAIL" not in out
