"""Strict-reader sensitivity for the ``rollback`` stub, and the empty-list fix.

Two follow-up checks on the retroactive-application study, both computed
from the frozen manifest's per-event rows (same rationale as
``p6/sensitivity_strict.py``: the source corpora have since been revised, so
the frozen rows are the authoritative record of what was mapped).

1. Rollback stub.  Every mapper in ``p6/retroactive_application.py`` fills
   ``rollback`` with ``{"procedure_ref": None, "tested_at": None}``.  The
   validator's liberal-empty rule counts that dict as populated because it
   has non-zero length, although it carries no recoverable information.
   A strict reader counts it unpopulated.  The field stays author judgment
   either way, so judgment share does not move.  The strict reading is also
   reported cumulatively with the strictest ``residual_risk`` reading of
   ``p6/sensitivity_strict.py``.

2. Empty-list fix.  ``blast_radius=[]`` and ``dependencies=[]`` are
   positive assertions by the schema's own definition, yet the conformance
   rule counts them missing.  Under a corrected rule that counts an empty
   list present for those two fields, an event conforms only if no other
   required field is unpopulatable.  No mapper emits ``self-write``, so the
   enum and cross-field constraints cannot block conformance here.

Outputs ``evidence/p6_sensitivity_rollback_stub.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "evidence" / "p6_retroactive_application.json"
OUT = REPO_ROOT / "evidence" / "p6_sensitivity_rollback_stub.json"

N_REQUIRED = 16
EMPTY_LIST_FIELDS = ("blast_radius", "dependencies")

# Pre-registered decision thresholds, fixed at the original freeze.
POSITIVE_PRESENCE = 25.0
POSITIVE_JUDGMENT = 50.0


def build(frozen_path: Path = FROZEN) -> dict:
    raw = frozen_path.read_bytes()
    events = json.loads(raw)["events"]
    n = len(events)

    def pct(x: float) -> float:
        return round(100.0 * x / (n * N_REQUIRED), 2)

    # Every mapper emits the null stub and records rollback as judgment, so
    # the judgment list identifies the stubbed events.
    stub = [e for e in events if "rollback" in (e.get("fields_required_judgment") or [])]
    stub_ids = {e["passport_id"] for e in stub}

    liberal_pop = sum(e["n_populated"] for e in events)
    liberal_jud = sum(len(e.get("fields_required_judgment") or []) for e in events)
    rb_pop = liberal_pop - len(stub)
    per_event = [
        100.0 * (e["n_populated"] - (e["passport_id"] in stub_ids)) / N_REQUIRED
        for e in events
    ]

    # Cumulative with the strictest residual_risk reading (same event sets as
    # p6/sensitivity_strict.py: CI-mapped claim-ledger-B rows plus all
    # constant-threshold claim-ledger-A rows).
    rr_affected = [
        e for e in events
        if (e["corpus"] == "p1_egcl_claim_ledger"
            and "residual_risk" not in (e.get("fields_unpopulatable") or []))
        or e["corpus"] == "p2_cwm_claim_ledger"
    ]
    both_pop = rb_pop - len(rr_affected)
    both_jud = liberal_jud + len(rr_affected)

    # Empty-list fix: the two list fields stop counting as missing; an event
    # still fails if any other required field is unpopulatable.
    conform_fix = [
        e for e in events
        if not [f for f in (e.get("fields_unpopulatable") or []) if f not in EMPTY_LIST_FIELDS]
    ]
    n_prior_missing = sum(
        "prior_state_ref" in (e.get("fields_unpopulatable") or []) for e in events
    )

    readings = {
        "rollback_strict": (pct(rb_pop), pct(liberal_jud)),
        "rollback_and_residual_risk_strict": (pct(both_pop), pct(both_jud)),
    }
    verdict_holds = all(
        p >= POSITIVE_PRESENCE and j <= POSITIVE_JUDGMENT for p, j in readings.values()
    )

    return {
        "manifest_version": 1,
        "manifest_kind": "p6_sensitivity_rollback_stub",
        "computed_from": {
            "path": str(frozen_path.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "n_events": n,
        },
        "liberal": {
            "fields_populated_pct": pct(liberal_pop),
            "judgment_pct": pct(liberal_jud),
        },
        "rollback_strict": {
            "n_events_with_null_stub": len(stub),
            "fields_populated_pct": readings["rollback_strict"][0],
            "judgment_pct": readings["rollback_strict"][1],
            "per_event_min_pct": round(min(per_event), 2),
            "per_event_max_pct": round(max(per_event), 2),
        },
        "rollback_and_residual_risk_strict": {
            "n_residual_risk_affected": len(rr_affected),
            "fields_populated_pct": readings["rollback_and_residual_risk_strict"][0],
            "judgment_pct": readings["rollback_and_residual_risk_strict"][1],
        },
        "empty_list_fix": {
            "fields": list(EMPTY_LIST_FIELDS),
            "n_prior_state_ref_unpopulatable": n_prior_missing,
            "n_conformant": len(conform_fix),
        },
        "pre_registered_thresholds": {
            "positive_presence_min": POSITIVE_PRESENCE,
            "positive_judgment_max": POSITIVE_JUDGMENT,
        },
        "verdict_unchanged_under_all_readings": verdict_holds,
        "ledger_rows": {
            "p6.rbs::n_stub": len(stub),
            "p6.rbs::presence_pct": readings["rollback_strict"][0],
            "p6.rbs::min_pct": round(min(per_event), 2),
            "p6.rbs::max_pct": round(max(per_event), 2),
            "p6.rbs::both_presence_pct": readings["rollback_and_residual_risk_strict"][0],
            "p6.rbs::both_judgment_pct": readings["rollback_and_residual_risk_strict"][1],
            "p6.rbs::n_prior_missing": n_prior_missing,
            "p6.rbs::n_conformant_fix": len(conform_fix),
        },
    }


def main() -> None:
    result = build()
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["ledger_rows"], indent=2))


if __name__ == "__main__":
    main()
