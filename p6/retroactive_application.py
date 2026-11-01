"""Retroactive application of the ChangePassport schema to already-
published promotion events recorded in three companion research
pipelines' evidence corpora.

Every target event is loaded from a REAL evidence manifest (P4 E4
verdicts, P2 CWM ledger, P1 EGCL ledger) and mapped into a
ChangePassport candidate.  For each target we record:

  * fields_populated_mechanically — fields the mapper filled from a
    literal telemetry lookup, no author judgment
  * fields_required_judgment      — fields the mapper filled from an
    author judgment call (recorded per-event so the reader can
    inspect the concentration)
  * fields_unpopulatable          — fields the original telemetry did
    not carry, marked as null in the passport

The pipeline is deterministic: given the same source manifests, it
produces the same manifest.  The mapper is intentionally SIMPLE —
no learning, no guessing; it either finds a field in the source
row or reports it as un-populatable.

Outputs ``evidence/p6_retroactive_application.json`` with an
``aggregate`` block whose keys feed the paper's
``\\StampedCell{p6.retro}{...}`` literals.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from p6.passport import (
    REQUIRED_FIELDS,
    validate,
    field_population_summary,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


# --- source-corpus mappers ---------------------------------------------------


def _map_p4_e4(per_dir: dict, run_meta: dict) -> tuple[dict, list[str], list[str]]:
    """Map one P4 E4 per_dir entry into a passport candidate.

    P4 E4 events are policy-supersession decisions produced by
    ``p4.gate_composer.admit``.  Prior/next state refs are NOT
    present in this corpus (E4 has no paired batches — recorded as
    the largest single source of reconstruction failure in the
    paper).
    """
    features = per_dir.get("features", {}) or {}
    formal = per_dir.get("formal", {}) or {}
    causal = per_dir.get("causal", {}) or {}
    transition = per_dir.get("transition", {}) or {}
    thresholds = run_meta.get("operating_point_thresholds", {}) or {}

    composed = per_dir.get("composed_verdict")
    outcome_map = {"SUPPORTED": "promoted", "UNSUPPORTED": "rejected"}
    promotion_outcome = outcome_map.get(composed)

    # residual_risk: per-axis (score, threshold, ok) triples
    residual_risk: dict[str, tuple] = {}
    if "formal_confidence" in thresholds:
        residual_risk["compliance"] = (
            1.0 if formal.get("passed") else 0.0,
            thresholds["formal_confidence"],
            bool(formal.get("passed")),
        )
    if causal:
        residual_risk["causal_effect"] = (
            causal.get("dr_value", 0.0),
            thresholds.get("causal_confidence", 0.0),
            bool(causal.get("passed_supersession_aware", causal.get("passed"))),
        )
    if transition:
        residual_risk["transition"] = (
            0.0,  # E4 has no paired batch; effect is undefined
            thresholds.get("transition_effect", 0.0),
            bool(transition.get("passed")),
        )

    evidence_refs = []
    if formal:
        evidence_refs.append(f"formal:{per_dir.get('short_key')}")
    if causal:
        evidence_refs.append(f"causal:{per_dir.get('short_key')}")
    if transition:
        evidence_refs.append(f"transition:{per_dir.get('short_key')}")

    passport: dict = {
        "passport_id": f"p4-e4-{per_dir.get('short_key','unknown')}",
        "artifact_id": features.get("path", ""),
        "artifact_class": "policy",
        "promoter_id": per_dir.get("composed_via", ""),
        "promoted_at": run_meta.get("utc_end", ""),
        # E4 has no paired batches — record as unpopulatable
        "prior_state_ref": "",
        "next_state_ref": features.get("path", ""),
        "promotion_mechanism": "gate-composition",
        "mechanism_config_ref": (
            f"operating_point:{run_meta.get('operating_point_corner','')}"
        ),
        "promotion_outcome": promotion_outcome or "rejected",
        "evidence_refs": evidence_refs,
        "residual_risk": residual_risk,
        "blast_radius": [],  # empty = positive isolation assertion
        "dependencies": [],
        "rollback": {"procedure_ref": None, "tested_at": None},
        "justification_chain": per_dir.get("justification_chain", []) or [],
    }

    # Author-judgment fields: blast_radius, dependencies, rollback all
    # populated with defensible defaults but WITHOUT literal-telemetry
    # backing.  We record them explicitly so the paper reports
    # judgment share honestly.
    judgment = ["blast_radius", "dependencies", "rollback"]
    unpopulatable = ["prior_state_ref"]  # no paired batch
    return passport, judgment, unpopulatable


def _map_p2_cwm_claim(
    row: dict, verdict: str | None = None
) -> tuple[dict, list[str], list[str]]:
    """Map one P2 CWM ledger claim/verdict row into a passport candidate.

    P2 CWM events are memory-like claim writes into an evidence-gated
    ledger.  The ``verdict_set`` row carries the SUPPORTED/UNSUPPORTED
    decision; the ``claim`` row carries the artifact identity.  This
    mapper takes the CLAIM row (which is more field-rich) and derives
    outcome from the row's status.
    """
    passport: dict = {
        "passport_id": f"p2-cwm-{row.get('claim_id','unknown')}",
        "artifact_id": row.get("cell_key", ""),
        "artifact_class": "memory",
        "promoter_id": row.get("method_id", ""),
        "promoted_at": row.get("_ts", ""),
        "prior_state_ref": "",
        "next_state_ref": row.get("snapshot_id", ""),
        "promotion_mechanism": "automated-eval",
        "mechanism_config_ref": row.get("template_id", ""),
        # Outcome comes from the JOINED verdict_set row when available.
        # The claim row's own ``status`` is the stale ADD-time value; trusting it would
        # misreport any claim later refuted. Falls back to ``status``
        # only when no verdict row exists for this claim_id.
        "promotion_outcome": (
            ("promoted" if verdict == "SUPPORTED" else "rejected")
            if verdict is not None
            else ("promoted" if row.get("status") == "verified" else "rejected")
        ),
        "evidence_refs": [row.get("evidence_ref", "")],
        "residual_risk": {
            "support": (
                float(row.get("support_count", 0)),
                12.0,  # observed n_seeds_x_streams in P2 CWM
                row.get("support_count", 0) >= 12,
            )
        },
        "blast_radius": [],
        "dependencies": [],
        "rollback": {"procedure_ref": None, "tested_at": None},
        "justification_chain": [row.get("template_id", "")],
    }
    judgment = ["blast_radius", "dependencies", "rollback"]
    unpopulatable = ["prior_state_ref"]
    return passport, judgment, unpopulatable


def _map_p1_egcl_claim(row: dict) -> tuple[dict, list[str], list[str]]:
    """Map one P1 EGCL ledger row into a passport candidate.

    P1 EGCL rows are evidence-gated claim writes: each carries a
    ``claim_id``, the measured ``value``/``metric``, the ``source`` file
    the value was read from, and a SUPPORTED/UNSUPPORTED ``verdict``
    with a free-text ``verdict_reason``.  Structurally this is the same
    memory-class promotion as the P2 CWM ledger, but the row carries
    STRICTLY LESS: there is no method/promoter field and no pointer to
    the gate's configuration, so both are recorded un-populatable rather
    than guessed.  Confidence intervals are present on only some rows;
    ``residual_risk`` is populated only when they are.
    """
    verdict = row.get("verdict")
    source = row.get("source", "") or ""
    # Source paths in this ledger are absolute author-machine paths;
    # keep only the repo-relative tail so no local path enters the
    # manifest (the tail is the real pointer).
    if "neurips-26-workshop-papers/" in source:
        source = source.split("neurips-26-workshop-papers/", 1)[1]

    residual_risk: dict = {}
    unpopulatable = ["prior_state_ref", "promoter_id", "mechanism_config_ref"]
    if row.get("ci_low") is not None and row.get("ci_high") is not None:
        # (score, threshold, ok) with the interval's lower bound as the
        # threshold axis — the only risk-shaped quantity the row carries.
        residual_risk["interval"] = (
            row.get("value"),
            row.get("ci_low"),
            verdict == "SUPPORTED",
        )
    else:
        unpopulatable.append("residual_risk")

    passport: dict = {
        "passport_id": f"p1-egcl-{row.get('claim_id','unknown')}",
        "artifact_id": row.get("claim_id", ""),
        "artifact_class": "memory",
        # No promoter/method field exists in this corpus.
        "promoter_id": "",
        "promoted_at": row.get("timestamp", ""),
        "prior_state_ref": "",
        "next_state_ref": source,
        "promotion_mechanism": "automated-eval",
        # No pointer to the gate's config exists in this corpus.
        "mechanism_config_ref": "",
        "promotion_outcome": "promoted" if verdict == "SUPPORTED" else "rejected",
        "evidence_refs": [source] if source else [],
        "residual_risk": residual_risk,
        "blast_radius": [],
        "dependencies": [],
        "rollback": {"procedure_ref": None, "tested_at": None},
        "justification_chain": (
            [row.get("verdict_reason")] if row.get("verdict_reason") else []
        ),
    }
    judgment = ["blast_radius", "dependencies", "rollback"]
    return passport, judgment, unpopulatable


# --- driver ------------------------------------------------------------------


def load_p1_egcl_events(
    ledger_path: Path = REPO_ROOT / "evidence" / "p1_egcl" / "ledger.jsonl",
    max_events: int | None = None,
) -> list[tuple[dict, list[str], list[str]]]:
    """Load ALL P1 EGCL ledger rows as passport candidates."""
    if not ledger_path.exists():
        return []
    events = []
    with ledger_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            events.append(_map_p1_egcl_claim(json.loads(line)))
            if max_events is not None and len(events) >= max_events:
                break
    return events


def load_p4_e4_events(
    manifest_path: Path = REPO_ROOT / "evidence" / "p4_e4_verdicts" / "e4_verdicts_real.json",
    max_events: int | None = None,
) -> list[tuple[dict, list[str], list[str]]]:
    """Load and map all P4 E4 per_dir events as passport candidates."""
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    run_meta = {
        "utc_end": data.get("utc_end", ""),
        "operating_point_corner": data.get("operating_point_corner", ""),
        "operating_point_thresholds": data.get("operating_point_thresholds", {}),
    }
    per_dirs = data.get("per_dir", []) or []
    if max_events is not None:
        per_dirs = per_dirs[:max_events]
    return [_map_p4_e4(pd, run_meta) for pd in per_dirs]


def load_p2_cwm_events(
    ledger_path: Path = REPO_ROOT / "evidence" / "p2_ledger.jsonl",
    max_events: int | None = None,
) -> list[tuple[dict, list[str], list[str]]]:
    """Load P2 CWM claim rows as passport candidates.

    Each claim row is joined 1:1 to its ``verdict_set`` row on
    ``claim_id`` so the promotion outcome comes from the adjudicated
    verdict rather than the claim row's stale ADD-time ``status``.
    """
    if not ledger_path.exists():
        return []
    claims: list[dict] = []
    verdicts: dict[str, str] = {}
    with ledger_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            kind = row.get("_row_kind")
            if kind == "claim":
                claims.append(row)
            elif kind == "verdict_set":
                verdicts[row.get("claim_id")] = row.get("verdict")
    events = []
    for row in claims:
        events.append(_map_p2_cwm_claim(row, verdicts.get(row.get("claim_id"))))
        if max_events is not None and len(events) >= max_events:
            break
    return events


def build_manifest(
    max_p4_events: int | None = None,
    max_p2_events: int | None = None,
    max_p1_events: int | None = None,
) -> dict:
    """Produce the retroactive-application manifest.

    Returns a dict written to
    ``evidence/p6_retroactive_application.json``; the ``aggregate``
    key feeds the paper's ``\\StampedCell{p6.retro}{...}`` cells.
    """
    events = []
    corpus_of: list[str] = []
    for label, loaded in (
        ("p4_e4_policy_supersession", load_p4_e4_events(max_events=max_p4_events)),
        ("p2_cwm_claim_ledger", load_p2_cwm_events(max_events=max_p2_events)),
        ("p1_egcl_claim_ledger", load_p1_egcl_events(max_events=max_p1_events)),
    ):
        events.extend(loaded)
        corpus_of.extend([label] * len(loaded))

    per_event_rows = []
    reports = []
    for (passport, judgment, unpopulatable), corpus in zip(events, corpus_of):
        report = validate(passport)
        reports.append(report)
        per_event_rows.append(
            {
                "passport_id": passport["passport_id"],
                "corpus": corpus,
                "artifact_class": passport["artifact_class"],
                "fields_populated_pct": report["fields_populated_pct"],
                "n_populated": len(report["populated_fields"]),
                "n_required": len(REQUIRED_FIELDS),
                "fields_required_judgment": judgment,
                "fields_unpopulatable": unpopulatable,
                "conformant": report["conformant"],
            }
        )

    n = len(events)
    total_pct = sum(r["fields_populated_pct"] for r in reports)
    total_judgment = sum(len(j) for _, j, _ in events)
    n_conformant = sum(1 for r in reports if r["conformant"])
    if n == 0:
        aggregate = {"n_events": 0, "fields_populated_pct": 0.0,
                     "judgment_pct": 0.0, "conformant_pct": 0.0}
    else:
        aggregate = {
            "n_events": n,
            "fields_populated_pct": round(total_pct / n, 2),
            "judgment_pct": round(100.0 * total_judgment / (n * len(REQUIRED_FIELDS)), 2),
            "conformant_pct": round(100.0 * n_conformant / n, 2),
        }

    def _input_digest(rel: str) -> dict:
        """Pin the exact state of a source corpus.

        These evidence files are live artifacts of companion pipelines
        that may still be appended to; recording size + sha256 + row count
        makes any later drift detectable instead of silent, and lets a
        verifier confirm exactly which input state produced these
        numbers.
        """
        p = REPO_ROOT / rel
        if not p.exists():
            return {"path": rel, "present": False}
        raw = p.read_bytes()
        return {
            "path": rel,
            "present": True,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "n_lines": len([b for b in raw.splitlines() if b.strip()]),
        }

    def _breakdown(key: str) -> dict:
        """Per-<key> aggregates, so the headline cannot hide a
        corpus- or class-specific effect."""
        out: dict = {}
        groups: dict[str, list[int]] = {}
        for i, r in enumerate(per_event_rows):
            groups.setdefault(r[key], []).append(i)
        for name, idxs in sorted(groups.items()):
            n_g = len(idxs)
            out[name] = {
                "n_events": n_g,
                "fields_populated_pct": round(
                    sum(reports[i]["fields_populated_pct"] for i in idxs) / n_g, 2
                ),
                "judgment_pct": round(
                    100.0
                    * sum(len(events[i][1]) for i in idxs)
                    / (n_g * len(REQUIRED_FIELDS)),
                    2,
                ),
                "n_conformant": sum(1 for i in idxs if reports[i]["conformant"]),
                "outcome_rejected": sum(
                    1
                    for i in idxs
                    if events[i][0]["promotion_outcome"] == "rejected"
                ),
            }
        return out

    by_corpus = _breakdown("corpus")

    return {
        "manifest_version": 2,
        "manifest_kind": "p6_retroactive_application",
        "events": per_event_rows,
        "aggregate": aggregate,
        "input_digests": [
            _input_digest("evidence/p4_e4_verdicts/e4_verdicts_real.json"),
            _input_digest("evidence/p2_ledger.jsonl"),
            _input_digest("evidence/p1_egcl/ledger.jsonl"),
        ],
        "by_corpus": by_corpus,
        "by_artifact_class": _breakdown("artifact_class"),
        # Flat "key::metric" ledger keys — the lookup convention the
        # paper's stamped-cell guard uses.
        "ledger_rows": {
            "p6.retro::fields_populated_pct": aggregate["fields_populated_pct"],
            "p6.retro::n_events":              aggregate["n_events"],
            "p6.retro::judgment_pct":          aggregate["judgment_pct"],
            # Full-schema conformance: share of events for which
            # validate() returned conformant=True.  Stamped in the paper
            # so the headline "0 of 8" is guard-checked like the others
            # rather than living as bare prose.
            "p6.retro::conformant_pct":        aggregate["conformant_pct"],
            "p6.retro::n_conformant":          n_conformant,
            "p6.retro::n_fields_required":     len(REQUIRED_FIELDS),
            # Corpus composition + per-corpus field-presence, so the
            # paper can report the breakdown as stamped cells.
            "p6.retro::n_corpora":             len(set(corpus_of)),
            "p6.retro::n_rejected":            sum(
                1 for e, _, _ in events if e["promotion_outcome"] == "rejected"
            ),
            "p6.retro::n_p4":   sum(1 for c in corpus_of if c == "p4_e4_policy_supersession"),
            "p6.retro::n_p2":   sum(1 for c in corpus_of if c == "p2_cwm_claim_ledger"),
            "p6.retro::n_p1":   sum(1 for c in corpus_of if c == "p1_egcl_claim_ledger"),
            # .get(): a corpus absent from this checkout (e.g. this
            # release, which does not ship the companion evidence
            # inputs) yields 0.0 rather than a crash.
            "p6.retro::pct_p4": by_corpus.get(
                "p4_e4_policy_supersession", {}).get("fields_populated_pct", 0.0),
            "p6.retro::pct_p2": by_corpus.get(
                "p2_cwm_claim_ledger", {}).get("fields_populated_pct", 0.0),
            "p6.retro::pct_p1": by_corpus.get(
                "p1_egcl_claim_ledger", {}).get("fields_populated_pct", 0.0),
            "p6.retro::pct_min": (
                min(r["fields_populated_pct"] for r in per_event_rows)
                if per_event_rows else 0.0
            ),
            "p6.retro::pct_max": (
                max(r["fields_populated_pct"] for r in per_event_rows)
                if per_event_rows else 0.0
            ),
        },
    }


def write_manifest(
    out_path: Path = REPO_ROOT / "evidence" / "p6_retroactive_application.json",
    max_p4_events: int | None = None,
    max_p2_events: int | None = None,
    max_p1_events: int | None = None,
) -> dict:
    """Build + write the manifest to disk; return the manifest dict.

    Defaults are None = map EVERY qualifying row in every admitted
    corpus (the pre-declared completeness rule); the caps exist only
    so unit tests can build small deterministic fixtures.
    """
    manifest = build_manifest(
        max_p4_events=max_p4_events,
        max_p2_events=max_p2_events,
        max_p1_events=max_p1_events,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    m = write_manifest()
    print(json.dumps(m["aggregate"], indent=2))
