"""Worked example for the paper's appendix: one reconstructed passport.

Re-maps the first policy-supersession event with the unchanged mapper
(``p6/retroactive_application.py``) and runs the reference validator on it.
The source verdict file is not shipped; it is accepted only if its SHA-256
equals the digest pinned in the frozen manifest's ``input_digests``, so the
example is the record that was actually mapped.  Absolute filesystem paths
in the output are elided to their last component (``.../name``).

Also lists, from the frozen per-event rows alone, the field status of the
least-complete event.

Usage:  python -m p6.worked_example <path/to/e4_verdicts_real.json>
Outputs ``evidence/p6_worked_example.json``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from p6 import passport as pp
from p6 import retroactive_application as ra

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "evidence" / "p6_retroactive_application.json"
OUT = REPO_ROOT / "evidence" / "p6_worked_example.json"
SOURCE_KEY = "evidence/p4_e4_verdicts/e4_verdicts_real.json"


def _elide(value):
    if isinstance(value, str) and value.startswith("/"):
        return ".../" + value.rstrip("/").rsplit("/", 1)[-1]
    if isinstance(value, list):
        return [_elide(v) for v in value]
    if isinstance(value, dict):
        return {k: _elide(v) for k, v in value.items()}
    return value


def build(source: Path) -> dict:
    manifest = json.loads(FROZEN.read_bytes())
    pinned = {d["path"]: d["sha256"] for d in manifest["input_digests"]}
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != pinned[SOURCE_KEY]:
        raise SystemExit(f"source digest {digest} != pinned {pinned[SOURCE_KEY]}")

    passport, judgment, unpopulatable = ra.load_p4_e4_events(source)[0]
    report = pp.validate(passport)
    frozen_row = next(e for e in manifest["events"] if e["passport_id"] == passport["passport_id"])
    if report["fields_populated_pct"] != frozen_row["fields_populated_pct"]:
        raise SystemExit("re-mapped event disagrees with the frozen manifest row")

    worst = min(manifest["events"], key=lambda e: e["n_populated"])
    return {
        "source_sha256": digest,
        "example": {
            "passport": _elide(passport),
            "fields_required_judgment": judgment,
            "fields_unpopulatable": unpopulatable,
            "validator": {k: report[k] for k in (
                "conformant", "fields_populated_pct", "missing_fields", "invalid_fields")},
        },
        "least_complete_event": {
            "corpus": worst["corpus"],
            "n_events_at_this_level": sum(
                e["n_populated"] == worst["n_populated"] for e in manifest["events"]),
            "n_populated": worst["n_populated"],
            "fields_populated_pct": worst["fields_populated_pct"],
            "fields_unpopulatable": worst["fields_unpopulatable"],
            "fields_required_judgment": worst["fields_required_judgment"],
            "conformant": worst["conformant"],
        },
    }


def main() -> None:
    result = build(Path(sys.argv[1]))
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
