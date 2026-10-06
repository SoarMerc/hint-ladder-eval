"""End-to-end smoke test on the deterministic simulator.

This runs the real generation, sweep, grading, detection and reporting code.
Only the network is replaced.
"""

from __future__ import annotations

import asyncio

from src.config import Config
from src.detect import summarise
from src.run import run


def test_mock_pipeline_runs_end_to_end(tmp_path, monkeypatch):
    import src.client as client_mod

    monkeypatch.setattr(client_mod, "CACHE", tmp_path / "cache")

    cfg = Config(mock=True, skills_limit=3, repeats=4, languages=["en", "es"])
    report = asyncio.run(run(cfg, do_drift=True))

    # 3 skills x 2 languages
    assert len(report.curves) == 6
    assert len(report.detections) == 6

    for c in report.curves:
        assert len(c.accuracy) == cfg.max_hint_level + 1
        assert all(0.0 <= a <= 1.0 for a in c.accuracy)

    counts = summarise(report.detections)
    assert sum(counts.values()) == 6

    # Only English items are re-tagged.
    assert len(report.tag_checks) == 3


def test_planted_leaks_are_actually_found(tmp_path, monkeypatch):
    """The simulator plants leaks; the detector should find some of them."""
    import src.client as client_mod

    monkeypatch.setattr(client_mod, "CACHE", tmp_path / "cache")

    cfg = Config(mock=True, skills_limit=12, repeats=6, languages=["en", "es", "fr"])
    report = asyncio.run(run(cfg, do_drift=False))

    counts = summarise(report.detections)
    assert counts["leaked"] > 0, "detector found no planted leaks"
    assert counts["ok"] > 0, "detector flagged everything, threshold is too loose"


def test_mock_and_live_never_share_a_cache_entry():
    """A simulated answer must never be replayed as a real one.

    Without mode in the cache key, a mock run poisons the cache and a later
    real run silently returns simulated content while reporting zero spend.
    """
    from src.client import ModelClient

    mock_client = ModelClient.__new__(ModelClient)
    mock_client.cfg = Config(mock=True)
    live_client = ModelClient.__new__(ModelClient)
    live_client.cfg = Config(mock=False)

    args = ("author", "gemini-2.5-pro", "system prompt", "user prompt")
    assert mock_client._cache_key(*args) != live_client._cache_key(*args)


def test_detector_is_exact_when_given_enough_samples(tmp_path, monkeypatch):
    """With the sampling noise driven down, the detector should be exact.

    This is the test that says the detector is correct rather than merely
    plausible: at 40 repeats per cell it must find every planted leak and
    invent none. Anything left at 5 repeats is noise, not logic.
    """
    import src.client as client_mod
    from src.client import _planted_leak_level

    monkeypatch.setattr(client_mod, "CACHE", tmp_path / "cache")

    cfg = Config(mock=True, repeats=40, languages=["en", "es", "fr"], use_cache=False)
    report = asyncio.run(run(cfg, do_drift=False))

    false_pos = false_neg = 0
    for d in report.detections:
        planted_early = (
            _planted_leak_level(d.skill_code, d.language, cfg.seed, cfg.max_hint_level)
            < cfg.max_hint_level
        )
        flagged = d.status == "leaked"
        false_pos += planted_early is False and flagged
        false_neg += planted_early is True and not flagged

    assert false_pos == 0, f"{false_pos} clean ladders flagged as leaking"
    assert false_neg == 0, f"{false_neg} planted leaks missed"
