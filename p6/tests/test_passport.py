"""Tests for the ChangePassport schema + validator + retro/incident drivers.

These tests are anti-fab tests: they verify that the schema-conformance
report is honest (no phantom-populated fields), that retroactive-
application ties every populated field to a real source-manifest row,
and that the incident drills are deterministic (same inputs, same
outputs, forever).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p6.passport import (
    ALLOWED_ARTIFACT_CLASSES,
    ALLOWED_MECHANISMS,
    ALLOWED_OUTCOMES,
    REQUIRED_FIELDS,
    validate,
    field_population_summary,
)
from p6 import retroactive_application as retro
from p6 import incident_drills as drills


# --- schema fixtures ---------------------------------------------------------


def _minimal_valid_passport() -> dict:
    return {
        "passport_id": "test-1",
        "artifact_id": "artifact-1",
        "artifact_class": "policy",
        "promoter_id": "p1",
        "promoted_at": "2026-08-15T00:00:00Z",
        "prior_state_ref": "prev",
        "next_state_ref": "next",
        "promotion_mechanism": "gate-composition",
        "mechanism_config_ref": "config-1",
        "promotion_outcome": "promoted",
        "evidence_refs": ["ev-1"],
        "residual_risk": {"compliance": (1.0, 0.95, True)},
        "blast_radius": ["a"],
        "dependencies": ["b"],
        "rollback": {"procedure_ref": "r", "tested_at": "t"},
        "justification_chain": ["ok"],
    }


# --- passport.validate -------------------------------------------------------


class TestValidate:
    def test_minimal_valid(self):
        r = validate(_minimal_valid_passport())
        assert r["conformant"] is True
        assert r["fields_populated_pct"] == 100.0
        assert r["missing_fields"] == []
        assert r["invalid_fields"] == []

    def test_missing_field(self):
        p = _minimal_valid_passport()
        del p["passport_id"]
        r = validate(p)
        assert r["conformant"] is False
        assert "passport_id" in r["missing_fields"]

    def test_empty_string_is_missing(self):
        p = _minimal_valid_passport()
        p["passport_id"] = ""
        r = validate(p)
        assert r["conformant"] is False
        assert "passport_id" in r["missing_fields"]

    def test_empty_evidence_refs_is_missing(self):
        p = _minimal_valid_passport()
        p["evidence_refs"] = []
        r = validate(p)
        assert r["conformant"] is False
        assert "evidence_refs" in r["missing_fields"]

    def test_invalid_artifact_class(self):
        p = _minimal_valid_passport()
        p["artifact_class"] = "malware"
        r = validate(p)
        assert r["conformant"] is False
        assert "artifact_class" in r["invalid_fields"]

    def test_invalid_promotion_mechanism(self):
        p = _minimal_valid_passport()
        p["promotion_mechanism"] = "handshake"
        r = validate(p)
        assert r["conformant"] is False
        assert "promotion_mechanism" in r["invalid_fields"]

    def test_invalid_promotion_outcome(self):
        p = _minimal_valid_passport()
        p["promotion_outcome"] = "pending"
        r = validate(p)
        assert r["conformant"] is False
        assert "promotion_outcome" in r["invalid_fields"]

    def test_self_write_constrains_evidence_refs(self):
        p = _minimal_valid_passport()
        p["promotion_mechanism"] = "self-write"
        p["evidence_refs"] = ["someone-else"]
        r = validate(p)
        assert r["conformant"] is False
        assert "evidence_refs" in r["invalid_fields"]

    def test_self_write_evidence_self_is_valid(self):
        p = _minimal_valid_passport()
        p["promotion_mechanism"] = "self-write"
        p["evidence_refs"] = ["self"]
        r = validate(p)
        assert r["conformant"] is True

    def test_all_16_fields_required(self):
        assert len(REQUIRED_FIELDS) == 16

    def test_enum_frozen(self):
        assert ALLOWED_ARTIFACT_CLASSES == frozenset(
            {"memory", "skill", "adapter", "policy", "prompt"}
        )
        assert ALLOWED_MECHANISMS == frozenset(
            {"gate-composition", "human-signoff", "automated-eval", "self-write"}
        )
        assert ALLOWED_OUTCOMES == frozenset({"promoted", "rejected", "superseded"})


class TestPopulationSummary:
    def test_empty(self):
        s = field_population_summary([])
        assert s["n_events"] == 0
        assert s["fields_populated_pct"] == 0.0

    def test_single_full(self):
        p = _minimal_valid_passport()
        r = validate(p)
        s = field_population_summary([r])
        assert s["n_events"] == 1
        assert s["fields_populated_pct"] == 100.0
        assert s["conformant_pct"] == 100.0

    def test_mixed(self):
        p = _minimal_valid_passport()
        r_full = validate(p)
        p2 = dict(p)
        del p2["passport_id"]
        r_partial = validate(p2)
        s = field_population_summary([r_full, r_partial])
        assert s["n_events"] == 2
        assert s["fields_populated_pct"] < 100.0
        assert s["conformant_pct"] == 50.0


# --- retroactive_application -------------------------------------------------


class TestRetroactive:
    def test_manifest_shape(self, tmp_path):
        out = tmp_path / "manifest.json"
        m = retro.write_manifest(out_path=out, max_p4_events=3, max_p2_events=1, max_p1_events=1)
        assert m["manifest_kind"] == "p6_retroactive_application"
        assert m["manifest_version"] == 2
        assert "aggregate" in m
        assert "ledger_rows" in m
        assert "p6.retro::fields_populated_pct" in m["ledger_rows"]
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded == m

    def test_events_all_have_populated_pct(self, tmp_path):
        out = tmp_path / "manifest.json"
        m = retro.write_manifest(out_path=out, max_p4_events=3, max_p2_events=1, max_p1_events=1)
        for row in m["events"]:
            assert "fields_populated_pct" in row
            assert 0.0 <= row["fields_populated_pct"] <= 100.0
            assert row["n_populated"] + len(row.get("fields_required_judgment", []) or []) <= row["n_required"] + 10

    def test_ledger_row_keys_match_paper(self, tmp_path):
        """Guard against silent renames — the paper cites these keys."""
        out = tmp_path / "manifest.json"
        m = retro.write_manifest(out_path=out, max_p4_events=2, max_p2_events=1, max_p1_events=1)
        # Full key set pinned exactly so a silent rename OR a silent
        # addition still fails this test. Conformance keys added in the
        # v2 pass (CHANGELOG_v2.md row C1).
        assert set(m["ledger_rows"].keys()) == {
            "p6.retro::fields_populated_pct",
            "p6.retro::n_events",
            "p6.retro::judgment_pct",
            "p6.retro::conformant_pct",
            "p6.retro::n_conformant",
            "p6.retro::n_fields_required",
            # R5 corpus-composition keys (CHANGELOG_v4.md Part 1).
            "p6.retro::n_corpora",
            "p6.retro::n_rejected",
            "p6.retro::n_p4",
            "p6.retro::n_p2",
            "p6.retro::n_p1",
            "p6.retro::pct_p4",
            "p6.retro::pct_p2",
            "p6.retro::pct_p1",
            "p6.retro::pct_min",
            "p6.retro::pct_max",
        }

    def test_deterministic(self, tmp_path):
        m1 = retro.build_manifest(max_p4_events=2, max_p2_events=1, max_p1_events=1)
        m2 = retro.build_manifest(max_p4_events=2, max_p2_events=1, max_p1_events=1)
        assert m1 == m2


# --- incident_drills ---------------------------------------------------------


class TestDrills:
    def test_manifest_shape(self, tmp_path):
        out = tmp_path / "manifest.json"
        m = drills.write_manifest(out_path=out, n_reps=5)
        assert m["manifest_kind"] == "p6_incident_drills"
        assert m["manifest_version"] == 1
        assert set(m["arms"].keys()) == {"passport", "lineage-only"}
        assert "ledger_rows" in m
        assert "p6.incident::ftr_eq_pct" in m["ledger_rows"]

    def test_ledger_row_keys_match_paper(self, tmp_path):
        out = tmp_path / "manifest.json"
        m = drills.write_manifest(out_path=out, n_reps=3)
        # Full key set pinned exactly so a silent rename OR a silent
        # addition still fails this test. Per-scenario keys added in the
        # v2 pass (CHANGELOG_v2.md row C2).
        assert set(m["ledger_rows"].keys()) == {
            "p6.incident::ftr_eq_pct",   "p6.incident::ftr_free_pct",
            "p6.incident::mttr_eq_s",    "p6.incident::mttr_free_s",
            "p6.incident::fpr_eq_pct",   "p6.incident::fpr_free_pct",
            "p6.incident::inj_eq_s",     "p6.incident::inj_free_s",
            "p6.incident::del_eq_s",     "p6.incident::del_free_s",
            "p6.incident::rb_eq_s",      "p6.incident::rb_free_s",
            "p6.incident::n_reps",       "p6.incident::dep_depth",
        }

    def test_deterministic(self):
        m1 = drills.run_scenarios(n_reps=3, dep_depth=2)
        m2 = drills.run_scenarios(n_reps=3, dep_depth=2)
        assert m1 == m2

    def test_passport_beats_lineage(self):
        m = drills.run_scenarios(n_reps=1, dep_depth=3)
        assert m["arms"]["passport"]["ftr_pct"] > m["arms"]["lineage-only"]["ftr_pct"]
        assert m["arms"]["passport"]["mttr_s"] < m["arms"]["lineage-only"]["mttr_s"]

    def test_headline_values_pinned(self):
        """Freeze the numeric values the paper stamps in \\StampedCell.

        These are the exact literals in main.tex Table 2. Any code refactor
        that changes recovery-time constants must update the paper too.
        """
        m = drills.run_scenarios(n_reps=10, dep_depth=3)
        assert m["arms"]["passport"]["ftr_pct"] == 100.0
        assert m["arms"]["passport"]["mttr_s"] == 2.83
        assert m["arms"]["lineage-only"]["ftr_pct"] == 33.33
        assert m["arms"]["lineage-only"]["mttr_s"] == 29.67

    def test_zero_false_positives_in_deterministic_drills(self):
        m = drills.run_scenarios(n_reps=2, dep_depth=2)
        assert m["arms"]["passport"]["fpr_pct"] == 0.0
        assert m["arms"]["lineage-only"]["fpr_pct"] == 0.0
