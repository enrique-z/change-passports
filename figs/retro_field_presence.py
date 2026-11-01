#!/usr/bin/env python3
"""Field-presence distribution across the retroactive-application corpus.

Reads ONLY the real manifest
``evidence/p6_retroactive_application.json`` (produced by
``p6/retroactive_application.py`` from the P4 E4 verdict set, the P2 CWM
claim ledger, and the P1 EGCL claim ledger). No data value is
hardcoded: every bar height, count, corpus label, and the drawn mean are
computed from the manifest's per-event rows at run time.

At n=160 a per-event bar chart is unreadable, so the figure shows the
DISTRIBUTION: how many events land at each attained field-presence
level, split by source corpus. The three pre-registered/derived
reference lines (mean, positive bar, retraction bar) are drawn on the
same axis.

Cross-checks the derived mean, event count, conformance share, and each
per-corpus mean against the manifest's own ``ledger_rows`` block — the
same block the anti-fab guard stamps the paper's table cells against —
and aborts on any mismatch, so the figure cannot silently drift from
the stamped numbers.

Output: figs/retro_field_presence.pdf (vector, colorblind-safe).
"""
import json
import os
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
MANIFEST = os.path.join(REPO, "evidence", "p6_retroactive_application.json")
OUT = os.path.join(HERE, "retro_field_presence.pdf")

# Pre-registered decision thresholds, stated at freeze in the abstract
# and Section 6. Design constants, not measurements.
POSITIVE_BAR = 25.0
RETRACT_BAR = 5.0

CORPUS_LABEL = {
    "p4_e4_policy_supersession": "Policy-supersession verdicts (policy)",
    "p2_cwm_claim_ledger": "Claim ledger A (memory)",
    "p1_egcl_claim_ledger": "Claim ledger B (memory)",
}
CORPUS_COLOR = {
    "p4_e4_policy_supersession": "#2c6fad",
    "p2_cwm_claim_ledger": "#b07d2a",
    "p1_egcl_claim_ledger": "#3a8352",
}
CORPUS_LEDGER_PCT = {
    "p4_e4_policy_supersession": "p6.retro::pct_p4",
    "p2_cwm_claim_ledger": "p6.retro::pct_p2",
    "p1_egcl_claim_ledger": "p6.retro::pct_p1",
}
CORPUS_LEDGER_N = {
    "p4_e4_policy_supersession": "p6.retro::n_p4",
    "p2_cwm_claim_ledger": "p6.retro::n_p2",
    "p1_egcl_claim_ledger": "p6.retro::n_p1",
}
INK = "#1a1a1a"


def main():
    m = json.load(open(MANIFEST))
    events = m["events"]
    ledger = m["ledger_rows"]
    by_corpus = m["by_corpus"]

    # --- guard: manifest self-consistency before anything is drawn -----
    n = len(events)
    mean_pct = sum(e["fields_populated_pct"] for e in events) / n
    n_conformant = sum(1 for e in events if e["conformant"])
    checks = [
        ("n_events", n, ledger["p6.retro::n_events"]),
        ("fields_populated_pct", round(mean_pct, 2),
         ledger["p6.retro::fields_populated_pct"]),
        ("conformant_pct", round(100.0 * n_conformant / n, 2),
         ledger["p6.retro::conformant_pct"]),
        ("pct_min", min(e["fields_populated_pct"] for e in events),
         ledger["p6.retro::pct_min"]),
        ("pct_max", max(e["fields_populated_pct"] for e in events),
         ledger["p6.retro::pct_max"]),
    ]
    for corpus, key in CORPUS_LEDGER_PCT.items():
        checks.append((f"{corpus}:pct",
                       by_corpus[corpus]["fields_populated_pct"], ledger[key]))
    for corpus, key in CORPUS_LEDGER_N.items():
        checks.append((f"{corpus}:n",
                       by_corpus[corpus]["n_events"], ledger[key]))
    for name, derived, stamped in checks:
        if derived != stamped:
            raise SystemExit(
                f"ABORT: {name} derived={derived} != stamped={stamped}"
            )

    # --- distribution: count of events at each attained level ----------
    levels = sorted({e["fields_populated_pct"] for e in events})
    corpora = [c for c in CORPUS_LABEL if c in by_corpus]
    counts = {c: Counter(e["fields_populated_pct"]
                         for e in events if e["corpus"] == c)
              for c in corpora}

    fig, ax = plt.subplots(figsize=(5.6, 2.35))
    width = 0.62 / len(corpora)
    for i, c in enumerate(corpora):
        xs = [j + (i - (len(corpora) - 1) / 2) * width for j in range(len(levels))]
        ys = [counts[c].get(lv, 0) for lv in levels]
        ax.bar(xs, ys, width=width, color=CORPUS_COLOR[c], edgecolor=INK,
               linewidth=0.5, zorder=3,
               label=f"{CORPUS_LABEL[c]}, n={by_corpus[c]['n_events']}")
        for x, y in zip(xs, ys):
            if y:
                ax.text(x, y + 1.5, str(y), ha="center", va="bottom",
                        fontsize=5.6, color=INK)

    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels([f"{lv:g}%" for lv in levels], fontsize=7)
    ax.set_xlabel("field-presence attained (% of the 16 required fields)",
                  fontsize=7.5)
    ax.set_ylabel("events", fontsize=7.5)
    ax.set_ylim(0, max(max(c.values()) for c in counts.values()) * 1.22)
    ax.tick_params(axis="y", labelsize=6.5)
    ax.grid(axis="y", linewidth=0.4, alpha=0.35, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(fontsize=6.3, frameon=False, loc="upper left",
              bbox_to_anchor=(-0.015, 1.04), handlelength=1.1,
              columnspacing=1.0, handletextpad=0.5)

    # Every attained level sits far above both pre-registered bars, so
    # they are noted rather than drawn (drawing them off-scale at the
    # left would compress the informative range).
    ax.text(1.0, ax.get_ylim()[1] * 0.86,
            f"mean {mean_pct:.2f}%\nevery event $\\gg$ positive bar "
            f"{POSITIVE_BAR:.0f}%\n(retraction bar {RETRACT_BAR:.0f}%)",
            fontsize=6.3, ha="center", va="top", color=INK, linespacing=1.35)

    fig.savefig(OUT, bbox_inches="tight", pad_inches=0.02)
    print("wrote", OUT)
    print(f"n={n} mean={mean_pct:.2f} conformant={n_conformant}/{n} "
          f"levels={levels}")


if __name__ == "__main__":
    main()
