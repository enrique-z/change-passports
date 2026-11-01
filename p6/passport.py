"""ChangePassport schema — reference definition + validator.

This module is the code embodiment of the schema specified in
`papers/p6_clea_change_passports/main.tex` §3.  It defines the
TypedDict, a JSON-Schema-style required-fields list, and a
mechanical validator that reports (a) whether a candidate dict is
schema-conformant and (b) which required fields are populated versus
missing.  No file I/O; pure functions.

The schema is closed-world in this freeze: exactly 16 required
fields grouped into six field groups (Identity, Provenance,
Mechanism+Outcome, Evidence, Risk, Dependencies+Rollback) plus a
human-readable justification chain.  Extensions are appendix-scoped
and NOT accepted by this validator.
"""

from __future__ import annotations

from typing import TypedDict


ALLOWED_ARTIFACT_CLASSES = frozenset(
    {"memory", "skill", "adapter", "policy", "prompt"}
)
ALLOWED_MECHANISMS = frozenset(
    {"gate-composition", "human-signoff", "automated-eval", "self-write"}
)
ALLOWED_OUTCOMES = frozenset({"promoted", "rejected", "superseded"})

REQUIRED_FIELDS: tuple[str, ...] = (
    "passport_id",
    "artifact_id",
    "artifact_class",
    "promoter_id",
    "promoted_at",
    "prior_state_ref",
    "next_state_ref",
    "promotion_mechanism",
    "mechanism_config_ref",
    "promotion_outcome",
    "evidence_refs",
    "residual_risk",
    "blast_radius",
    "dependencies",
    "rollback",
    "justification_chain",
)

FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "Identity": ("passport_id", "artifact_id", "artifact_class"),
    "Provenance": ("promoter_id", "promoted_at", "prior_state_ref", "next_state_ref"),
    "MechanismOutcome": (
        "promotion_mechanism",
        "mechanism_config_ref",
        "promotion_outcome",
    ),
    "Evidence": ("evidence_refs",),
    "Risk": ("residual_risk", "blast_radius"),
    "DependenciesRollback": ("dependencies", "rollback", "justification_chain"),
}


class ChangePassport(TypedDict):
    passport_id: str
    artifact_id: str
    artifact_class: str
    promoter_id: str
    promoted_at: str
    prior_state_ref: str
    next_state_ref: str
    promotion_mechanism: str
    mechanism_config_ref: str
    promotion_outcome: str
    evidence_refs: list[str]
    residual_risk: dict[str, tuple[float, float, bool]]
    blast_radius: list[str]
    dependencies: list[str]
    rollback: dict[str, object]
    justification_chain: list[str]


class ValidationReport(TypedDict, total=False):
    conformant: bool
    populated_fields: list[str]
    missing_fields: list[str]
    invalid_fields: list[str]  # fields present but with disallowed values
    fields_populated_pct: float
    reason: str


def _is_populated(value: object) -> bool:
    """A field is populated iff its value is non-empty and non-null.

    An empty list / empty dict / empty string counts as UNPOPULATED
    for reporting purposes — the schema permits them as valid values
    (e.g., ``blast_radius=[]`` is a positive isolation assertion) but
    for FIELD-PRESENCE metrics we count only fields that carry
    non-empty content.  A consumer that wants strict-conformance
    checking should use ``conformant``.
    """
    if value is None:
        return False
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return False
    return True


def validate(passport: dict) -> ValidationReport:
    """Mechanical schema check.

    Returns a ``ValidationReport`` naming which required fields are
    populated, which are missing entirely, and which are present but
    carry disallowed enum values (artifact_class,
    promotion_mechanism, promotion_outcome).  Never raises.
    """
    populated: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in passport:
            missing.append(field)
            continue
        if _is_populated(passport[field]):
            populated.append(field)
        else:
            missing.append(field)

    # Enum checks (only for fields we have)
    ac = passport.get("artifact_class")
    if ac is not None and ac not in ALLOWED_ARTIFACT_CLASSES:
        invalid.append("artifact_class")
    pm = passport.get("promotion_mechanism")
    if pm is not None and pm not in ALLOWED_MECHANISMS:
        invalid.append("promotion_mechanism")
    po = passport.get("promotion_outcome")
    if po is not None and po not in ALLOWED_OUTCOMES:
        invalid.append("promotion_outcome")
    # self-write mechanism constrains evidence_refs
    if pm == "self-write":
        er = passport.get("evidence_refs") or []
        if er and er != ["self"]:
            invalid.append("evidence_refs")

    pct = 100.0 * len(populated) / len(REQUIRED_FIELDS)
    return ValidationReport(
        conformant=(not missing and not invalid),
        populated_fields=populated,
        missing_fields=missing,
        invalid_fields=invalid,
        fields_populated_pct=round(pct, 2),
        reason=(
            "conformant"
            if not missing and not invalid
            else f"missing={missing};invalid={invalid}"
        ),
    )


def field_population_summary(reports: list[ValidationReport]) -> dict:
    """Aggregate multiple ValidationReports into a headline summary.

    Used by the retroactive-application driver to produce the headline
    numbers stamped into the paper (see
    ``evidence/p6_retroactive_application.json``).
    """
    n = len(reports)
    if n == 0:
        return {"n_events": 0, "fields_populated_pct": 0.0, "conformant_pct": 0.0}
    total_pct = sum(r.get("fields_populated_pct", 0.0) for r in reports)
    n_conformant = sum(1 for r in reports if r.get("conformant"))
    return {
        "n_events": n,
        "fields_populated_pct": round(total_pct / n, 2),
        "conformant_pct": round(100.0 * n_conformant / n, 2),
    }
