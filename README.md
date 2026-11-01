# Change Passports

Reference implementation and evidence for

> Enrique Zueco, David Scott Lewis, Haley Yi, Karl Wang, Junhan Wang.
> **Change Passports: A Machine-Readable Standard for Auditable Artifact Promotion in
> Continually-Learning Agents.** Continual Learning for Enterprise AI Agents (CLEA)
> Workshop at NeurIPS 2026.

A change passport is a fixed, machine-readable record emitted at every artifact promotion
(memory, skill, adapter, policy, prompt) in a continually-learning agent. This repository
contains the schema and its reference validator, the two studies reported in the paper,
and the frozen manifests every reported number is checked against.

## Layout

```
p6/
  passport.py                  # ChangePassport TypedDict + reference validator
                               # (16 required fields, 3 enum-constrained, 1 self-write
                               #  cross-field constraint) — paper §3
  retroactive_application.py   # retroactive study (field-presence, judgment share,
                               #  full-schema conformance) — paper §4.1, Tables 1–2
  incident_drills.py           # deterministic sufficiency drill — paper §4.2, App. C
  sensitivity_strict.py        # strict residual_risk readings — paper App. A
  sensitivity_rollback_stub.py # strict rollback reading + empty-list fix — §4.1, App. A
  worked_example.py            # the reconstructed passport shown in App. D
  tests/                       # 24 unit tests (schema, validator, both studies)
evidence/
  p6_retroactive_application.json   # frozen manifest: 160 per-event rows + aggregates
  p6_incident_drills.json           # drill manifest (aggregate + per-scenario)
  p6_sensitivity_strict.json        # output of sensitivity_strict.py
  p6_sensitivity_rollback_stub.json # output of sensitivity_rollback_stub.py
  p6_worked_example.json            # output of worked_example.py
  p6_claim_evidence_ledger.json     # provenance rows for the paper's stamped cells
  p6_archive/                       # earlier n=8 manifest, before the corpus expansion
figs/
  passport_schematic.py        # Figure 1 (conceptual; labels read from p6/passport.py)
  retro_field_presence.py      # Figure 2 (reads the frozen manifest; aborts on drift)
```

## Reproduce

```
python3 -m pytest p6/tests -q            # 24 passed
python3 -m p6.incident_drills            # ftr 100.0 / 33.33, mttr 2.83 / 29.67, fpr 0.0 / 0.0
python3 -m p6.sensitivity_strict         # strictest residual_risk reading: 70.7 / 23.44
python3 -m p6.sensitivity_rollback_stub  # 69.14; 64.45 / 23.44; 0 conformant under the fix
```

**Retroactive study.** The reported numbers (75.39% field-presence, 18.75% judgment
share, 0/160 conformant) are in `evidence/p6_retroactive_application.json`, including one
row per event. `python3 -m p6.retroactive_application` re-runs the mapper, but it needs
the three source corpora (a policy-supersession verdict set and two claim ledgers). These
come from our companion research pipelines and are not shipped here, so run on this
repository alone the command finds no events. The manifest pins each corpus by path, byte
length, SHA-256 and row count. One corpus (the second claim ledger, pinned at 59 rows)
has since been revised and the revision was not append-only, so its pinned state cannot
be recovered from the current file. The frozen per-event rows are therefore the
authoritative record. All sensitivity scripts read only those rows.

**Worked example.** `python3 -m p6.worked_example <e4_verdicts_real.json>` needs the
policy-supersession verdict file, which is not shipped. The script accepts it only if its
SHA-256 equals the digest pinned in the manifest. Its output is
`evidence/p6_worked_example.json`, with absolute paths elided to their last component.

**Figures.** `python3 figs/passport_schematic.py` and `python3 figs/retro_field_presence.py`
(need matplotlib) regenerate Figures 1 and 2 next to the scripts; the second aborts if any
value it derives disagrees with the manifest's `ledger_rows`.

## Scope (as stated in the paper)

- The retroactive study is second-hand by construction. `prior_state_ref` is unpopulatable
  in all 160 events, so full-schema conformance is 0/160. It stays 0/160 even under the
  stated empty-list fix.
- Only the memory (152 events) and policy (8 events) classes are exercised. Skill, adapter
  and prompt coverage is a design claim.
- The incident drill is a sufficiency demonstration against an engineered lineage-only
  baseline. Both arms are constants fixed at freeze, so it is not a measured advantage.

## License

MIT (see `LICENSE`).
