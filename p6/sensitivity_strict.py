"""Strict-reader sensitivity analysis for the retroactive-application study.

The paper's liberal population policy counts a field as populated whenever
its value is non-empty and read literally from the source row.  One mapping
decision is genuinely debatable and is flagged as such in the paper's
appendix: for a claim-ledger event that carries a confidence interval, the
interval bound is used as the threshold axis of ``residual_risk``'s
(score, threshold, ok) triple.  The value IS read literally from the row, so
the liberal policy counts the field populated -- but a stricter reader may
regard repurposing an interval bound as a threshold as an act of author
judgment rather than a lookup.

This module recomputes the two headline rates under that strict reading and
reports whether the pre-registered decision rule (field-presence >= 25% AND
judgment share <= 50%) still returns the same verdict.

CRITICAL -- WHY THIS READS THE MANIFEST AND NOT THE SOURCE CORPORA:
``p6/retroactive_application.py`` maps from live evidence files of companion
pipelines, which have since been revised
(the second claim ledger moved from the pinned 59 rows to 75, and the
revision was not append-only, so the pinned state is unrecoverable).
Re-running the mapper would therefore silently change every headline number
in the paper.  The frozen manifest's per-event rows are the authoritative
record of what was mapped, so this analysis is computed from them alone and
touches no source corpus.  It also leaves the frozen manifest byte-identical
by writing its own output file.

Outputs ``evidence/p6_sensitivity_strict.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "evidence" / "p6_retroactive_application.json"
OUT = REPO_ROOT / "evidence" / "p6_sensitivity_strict.json"

# The single field whose mapping is being stress-tested.
DISPUTED_FIELD = "residual_risk"
N_REQUIRED = 16

# Pre-registered decision thresholds, fixed at the original freeze.
POSITIVE_PRESENCE = 25.0
POSITIVE_JUDGMENT = 50.0


def build(frozen_path: Path = FROZEN) -> dict:
    raw = frozen_path.read_bytes()
    manifest = json.loads(raw)
    events = manifest["events"]
    n = len(events)

    # An event's residual_risk was CI-derived exactly when the field is NOT
    # listed un-populatable and the event comes from a claim ledger whose
    # mapper populates residual_risk only under a confidence interval.
    # We detect it structurally from the frozen rows: the field is absent
    # from fields_unpopulatable while the event is not a gate-composition
    # (policy) event, whose residual_risk is threshold-derived and not in
    # dispute.
    # Level 1 -- the CI-derived mapping (claim ledger B): the threshold axis
    # is an interval bound read from the row.
    affected_ci = [
        e for e in events
        if e["corpus"] == "p1_egcl_claim_ledger"
        and DISPUTED_FIELD not in (e.get("fields_unpopulatable") or [])
    ]
    # Level 2 -- the constant-threshold mapping (claim ledger A): the score is
    # read from the row but the THRESHOLD is an author-supplied constant
    # (`12.0`, the observed seeds x streams count).  A reader who rejects the
    # CI mapping should reject this one at least as firmly, so the strict
    # reading is reported cumulatively.
    affected_const = [e for e in events if e["corpus"] == "p2_cwm_claim_ledger"]
    affected = affected_ci + affected_const

    liberal_pop = sum(e["n_populated"] for e in events)
    liberal_jud = sum(len(e.get("fields_required_judgment") or []) for e in events)

    # Strict reading: the disputed field moves from populated to judgment.
    # strict-1: only the CI mapping reclassified; strict-2: both.
    s1_pop, s1_jud = liberal_pop - len(affected_ci), liberal_jud + len(affected_ci)
    strict_pop = liberal_pop - len(affected)
    strict_jud = liberal_jud + len(affected)

    def pct(x: int) -> float:
        return round(100.0 * x / (n * N_REQUIRED), 2)

    strict_presence = pct(strict_pop)
    strict_judgment = pct(strict_jud)
    verdict_holds = (
        strict_presence >= POSITIVE_PRESENCE and strict_judgment <= POSITIVE_JUDGMENT
    )

    return {
        "manifest_version": 1,
        "manifest_kind": "p6_sensitivity_strict",
        "computed_from": {
            "path": str(frozen_path.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "n_events": n,
        },
        "disputed_field": DISPUTED_FIELD,
        "n_events_affected": len(affected),
        "n_affected_ci_mapping": len(affected_ci),
        "n_affected_constant_threshold": len(affected_const),
        "strict_ci_only": {
            "fields_populated_pct": pct(s1_pop),
            "judgment_pct": pct(s1_jud),
        },
        "liberal": {
            "fields_populated_pct": pct(liberal_pop),
            "judgment_pct": pct(liberal_jud),
        },
        "strict": {
            "fields_populated_pct": strict_presence,
            "judgment_pct": strict_judgment,
        },
        "pre_registered_thresholds": {
            "positive_presence_min": POSITIVE_PRESENCE,
            "positive_judgment_max": POSITIVE_JUDGMENT,
        },
        "verdict_unchanged_under_strict_reading": verdict_holds,
        "ledger_rows": {
            "p6.sens::n_affected": len(affected),
            "p6.sens::n_affected_ci": len(affected_ci),
            "p6.sens::strict_presence_pct": strict_presence,
            "p6.sens::strict_judgment_pct": strict_judgment,
            "p6.sens::strict1_presence_pct": pct(s1_pop),
            "p6.sens::strict1_judgment_pct": pct(s1_jud),
        },
    }


def write(out_path: Path = OUT) -> dict:
    m = build()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(m, indent=2))
    return m


if __name__ == "__main__":
    m = write()
    print(json.dumps(
        {"liberal": m["liberal"], "strict": m["strict"],
         "n_affected": m["n_events_affected"],
         "verdict_unchanged": m["verdict_unchanged_under_strict_reading"]},
        indent=2))
