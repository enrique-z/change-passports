#!/usr/bin/env python3
"""Conceptual schematic of the change-passport record and its consumers.

CONCEPTUAL figure: it carries no measured quantity. Every label it
draws is read at run time from the reference schema module
``p6/passport.py`` (FIELD_GROUPS, REQUIRED_FIELDS, and the three enum
frozensets), so the figure cannot drift from the specification the
paper states in Section 3. Nothing is hardcoded except layout geometry
and the names of the three downstream consumer classes, which are
prose in the paper body, not data.

Output: figs/passport_schematic.pdf (vector, colorblind-safe).
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

from p6.passport import (  # noqa: E402
    ALLOWED_MECHANISMS,
    FIELD_GROUPS,
    REQUIRED_FIELDS,
)

OUT = os.path.join(HERE, "passport_schematic.pdf")

# Display names for the six field groups, keyed by the module's own
# group keys so a schema change surfaces as a KeyError rather than a
# silently stale figure.
GROUP_LABEL = {
    "Identity": "Identity",
    "Provenance": "Provenance",
    "MechanismOutcome": "Mechanism + outcome",
    "Evidence": "Evidence",
    "Risk": "Risk",
    "DependenciesRollback": "Dependencies + rollback",
}

# Consumer classes named in Section 1 of the paper (prose, not data).
CONSUMERS = ["Audit", "Incident response", "Capability registry"]

INK = "#1a1a1a"
BOX = "#dbe7f3"
BOX_EDGE = "#2c6fad"
MECH = "#f2e3cd"
MECH_EDGE = "#b07d2a"
CONS = "#dff0e4"
CONS_EDGE = "#3a8352"


def _box(ax, x, y, w, h, text, face, edge, fontsize=7.0, weight="normal"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=0.8, facecolor=face, edgecolor=edge,
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color=INK, weight=weight, linespacing=1.25)


def _arrow(ax, xy_from, xy_to):
    ax.add_patch(
        FancyArrowPatch(
            xy_from, xy_to, arrowstyle="-|>", mutation_scale=8,
            linewidth=0.8, color=INK, shrinkA=1.0, shrinkB=1.0,
        )
    )


def main():
    n_fields = len(REQUIRED_FIELDS)
    mechanisms = sorted(ALLOWED_MECHANISMS)

    fig, ax = plt.subplots(figsize=(6.6, 2.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # --- left: the promotion mechanisms that emit a passport ------------
    ax.text(0.105, 0.955, "Promotion mechanism", ha="center", va="center",
            fontsize=7.5, weight="bold", color=INK)
    mh = 0.155
    for i, m in enumerate(mechanisms):
        y = 0.70 - i * (mh + 0.035)
        _box(ax, 0.012, y, 0.186, mh, m.replace("-", "-\n"), MECH, MECH_EDGE)

    # --- centre: the passport record, six field groups ------------------
    _box(ax, 0.245, 0.135, 0.42, 0.82,
         "", "#ffffff", INK)
    ax.text(0.455, 0.895,
            f"Change passport ({n_fields} required fields)",
            ha="center", va="center", fontsize=7.5, weight="bold", color=INK)

    keys = list(FIELD_GROUPS.keys())
    gw, gh = 0.185, 0.175
    for i, key in enumerate(keys):
        col, row = i % 2, i // 2
        x = 0.263 + col * (gw + 0.017)
        y = 0.615 - row * (gh + 0.035)
        label = "%s\n(%d)" % (GROUP_LABEL[key], len(FIELD_GROUPS[key]))
        _box(ax, x, y, gw, gh, label, BOX, BOX_EDGE)

    # --- right: uniform downstream consumers ----------------------------
    ax.text(0.855, 0.955, "Uniform consumers", ha="center", va="center",
            fontsize=7.5, weight="bold", color=INK)
    ch = 0.185
    for i, c in enumerate(CONSUMERS):
        y = 0.665 - i * (ch + 0.055)
        _box(ax, 0.715, y, 0.27, ch, c, CONS, CONS_EDGE)
        _arrow(ax, (0.668, y + ch / 2), (0.712, y + ch / 2))

    for i in range(len(mechanisms)):
        y = 0.70 - i * (mh + 0.035) + mh / 2
        _arrow(ax, (0.201, y), (0.242, y))

    fig.savefig(OUT, bbox_inches="tight", pad_inches=0.02)
    print("wrote", OUT)
    print("field groups:", {k: len(v) for k, v in FIELD_GROUPS.items()})
    print("required fields:", n_fields, "| mechanisms:", mechanisms)


if __name__ == "__main__":
    main()
